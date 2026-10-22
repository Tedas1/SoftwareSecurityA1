import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Self

from fastapi import Depends, FastAPI, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth import Agreement, Principal, User, jwt_key, staff_only
from app.fleet_resource_service.db import connection, initialize

Database = Annotated[sqlite3.Connection, Depends(connection)]
PositiveId = Annotated[int, Path(gt=0, le=2**63 - 1)]


class VehicleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # CWE-20: Improper Input Validation; accepts white space car names
    name: str = Field(min_length=1, max_length=100)
    daily_rate_cents: int = Field(strict=True, gt=0, le=2**31 - 1)


class BookingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: int = Field(strict=True, gt=0, le=2**63 - 1)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class InvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=100000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    jwt_key()
    initialize()
    yield


app = FastAPI(title="Fleet Resource Service", lifespan=lifespan)


def accessible_booking(
    booking_id: PositiveId, identity: Principal, db: Database
) -> sqlite3.Row:
    """Recheck booking scope and ownership for direct and downstream callers."""
    if identity.scope == "agreement" and identity.booking_id != booking_id:
        raise HTTPException(
            status_code=403, detail="Token is scoped to another booking"
        )
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ?", (booking_id,)
    ).fetchone()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if identity.role != "staff" and booking["renter_id"] != identity.sub:
        raise HTTPException(status_code=403, detail="Booking belongs to another renter")
    return booking


Booking = Annotated[sqlite3.Row, Depends(accessible_booking)]


@app.get("/vehicles")
def list_vehicles(identity: User, db: Database) -> list[dict[str, object]]:
    return [dict(row) for row in db.execute("SELECT * FROM vehicles ORDER BY id")]


# CWE-89 SQL Injection
@app.get("/vehicles/search")
def search_vehicles(
    name: str, identity: User, db: Database
) -> list[dict[str, object]]:
    cursor = db.cursor()
    rows = cursor.execute(
        f"SELECT * FROM vehicles WHERE name LIKE '%{name}%' ORDER BY id"
    )
    return [dict(row) for row in rows]


@app.post("/vehicles", status_code=201, dependencies=[Depends(staff_only)])
def create_vehicle(vehicle: VehicleInput, db: Database) -> dict[str, object]:
    with db:
        row = db.execute(
            "INSERT INTO vehicles (name, daily_rate_cents) VALUES (?, ?) RETURNING *",
            (vehicle.name, vehicle.daily_rate_cents),
        ).fetchone()
    return dict(row)


@app.delete(
    "/vehicles/{vehicle_id}", status_code=204, dependencies=[Depends(staff_only)]
)
def delete_vehicle(vehicle_id: PositiveId, db: Database) -> Response:
    try:
        with db:
            result = db.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Vehicle not found")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="A vehicle with bookings cannot be deleted"
        ) from exc
    return Response(status_code=204)


@app.post("/bookings", status_code=201)
def create_booking(
    request: BookingInput, identity: User, db: Database
) -> dict[str, object]:
    if identity.role != "renter":
        raise HTTPException(status_code=403, detail="Only renters can create bookings")
    with db:
        db.execute("BEGIN IMMEDIATE")
        vehicle = db.execute(
            "SELECT * FROM vehicles WHERE id = ?", (request.vehicle_id,)
        ).fetchone()
        if vehicle is None:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        overlap = db.execute(
            "SELECT 1 FROM bookings WHERE vehicle_id = ? AND status = 'pending' "
            "AND start_date < ? AND end_date > ?",
            (
                request.vehicle_id,
                request.end_date.isoformat(),
                request.start_date.isoformat(),
            ),
        ).fetchone()
        if overlap is not None:
            raise HTTPException(status_code=409, detail="Vehicle is already booked")
        total = (
            vehicle["daily_rate_cents"] * (request.end_date - request.start_date).days
        )
        row = db.execute(
            "INSERT INTO bookings "
            "(renter_id, vehicle_id, start_date, end_date, total_cents) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            (
                identity.sub,
                request.vehicle_id,
                request.start_date.isoformat(),
                request.end_date.isoformat(),
                total,
            ),
        ).fetchone()
    return dict(row)


@app.get("/bookings")
def list_bookings(identity: User, db: Database) -> list[dict[str, object]]:
    rows = db.execute(
        "SELECT * FROM bookings WHERE (? = 'staff' OR renter_id = ?) ORDER BY id",
        (identity.role, identity.sub),
    )
    return [dict(row) for row in rows]


@app.get("/bookings/{booking_id}")
def get_booking(booking: Booking, identity: Principal) -> dict[str, object]:
    if identity.scope == "agreement" and booking["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Booking is cancelled")
    return dict(booking)


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking: Booking, identity: User, db: Database) -> dict[str, object]:
    with db:
        row = db.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? RETURNING *",
            (booking["id"],),
        ).fetchone()
    return dict(row)

# CWE-862 Missing Authorization / IDOR
@app.post("/bookings/{booking_id}/override-cancel")
def override_cancel_booking(
    booking_id: PositiveId, identity: User, db: Database
) -> dict[str, object]:
    with db:
        row = db.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? RETURNING *",
            (booking_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Booking not found")
    return dict(row)

@app.put("/bookings/{booking_id}/invoice")
def save_invoice(
    invoice: InvoiceInput, booking: Booking, identity: Agreement, db: Database
) -> dict[str, object]:
    with db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT status FROM bookings WHERE id = ?", (booking["id"],)
        ).fetchone()
        if current["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="Booking is cancelled")
        db.execute(
            "INSERT INTO invoices (booking_id, content) VALUES (?, ?) "
            "ON CONFLICT(booking_id) DO UPDATE SET content = excluded.content",
            (booking["id"], invoice.content),
        )
    return {"booking_id": booking["id"], "content": invoice.content}


@app.get("/bookings/{booking_id}/invoice")
def get_invoice(booking: Booking, identity: User, db: Database) -> dict[str, object]:
    invoice = db.execute(
        "SELECT * FROM invoices WHERE booking_id = ?", (booking["id"],)
    ).fetchone()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return dict(invoice)
