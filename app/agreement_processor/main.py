import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal, Self

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi import Path as ApiPath
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from rental_invoice_render import render_invoice

from app.auth import Agreement, jwt_key
from app.http import forward

logger = logging.getLogger(__name__)
PositiveId = Annotated[int, ApiPath(gt=0, le=2**63 - 1)]


class BookingData(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: int = Field(gt=0, le=2**63 - 1)
    renter_id: str = Field(min_length=1, max_length=100)
    vehicle_id: int = Field(gt=0, le=2**63 - 1)
    start_date: date
    end_date: date
    total_cents: int = Field(gt=0, le=2**63 - 1)
    status: Literal["pending"]

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("Booking end_date must be after start_date")
        return self


@asynccontextmanager
async def lifespan(_: FastAPI):
    jwt_key()
    yield


app = FastAPI(title="Agreement Processor", lifespan=lifespan)


@app.post("/agreements/{booking_id}")
def generate_agreement(
    booking_id: PositiveId, identity: Agreement, request: Request
) -> Response:
    if identity.booking_id != booking_id:
        raise HTTPException(
            status_code=403, detail="Token is scoped to another booking"
        )
    authorization = request.headers["authorization"]
    fetched = forward("fleet", "GET", f"/bookings/{booking_id}", authorization)
    if fetched.status_code != 200:
        return fetched
    try:
        booking = BookingData.model_validate_json(bytes(fetched.body))
    except ValidationError as exc:
        logger.warning("Fleet returned invalid booking data")
        raise HTTPException(
            status_code=502, detail="Invalid booking data from fleet"
        ) from exc
    if booking.id != booking_id or (
        identity.role == "renter" and booking.renter_id != identity.sub
    ):
        logger.warning("Fleet returned booking data outside the requested authority")
        raise HTTPException(
            status_code=502, detail="Mismatched booking data from fleet"
        )
    invoice = {
        "booking_id": booking.id,
        "renter_id": booking.renter_id,
        "vehicle_id": booking.vehicle_id,
        "start_date": booking.start_date.isoformat(),
        "end_date": booking.end_date.isoformat(),
        "total_cents": booking.total_cents,
    }
    try:
        with TemporaryDirectory(prefix="rental-invoice-") as directory:
            output = Path(directory) / "invoice.txt"
            render_invoice(invoice, output)
            with output.open(encoding="utf-8") as rendered:
                content = rendered.read(100001)
    except (OSError, UnicodeError) as exc:
        logger.exception("Invoice rendering failed")
        raise HTTPException(status_code=500, detail="Invoice rendering failed") from exc
    if not content.strip() or len(content) > 100000:
        logger.error("Invoice renderer returned empty or oversized output")
        raise HTTPException(status_code=500, detail="Invalid rendered invoice")
    return forward(
        "fleet",
        "PUT",
        f"/bookings/{booking_id}/invoice",
        authorization,
        {"content": content},
    )
