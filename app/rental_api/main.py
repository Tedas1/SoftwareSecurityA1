import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth import Role, User, issue_token, jwt_key, staff_only, user_only
from app.http import forward

PositiveId = Annotated[int, Path(gt=0, le=2**63 - 1)]
DEMO_ROLES: dict[str, Role] = {
    "alice": "renter",
    "bob": "renter",
    "carol": "staff",
}


@dataclass(frozen=True)
class Account:
    role: Role
    salt: bytes
    password_hash: bytes


accounts: dict[str, Account] = {}


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = Field(default="bearer")


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    jwt_key()
    prepared: dict[str, Account] = {}
    for username, role in DEMO_ROLES.items():
        variable = f"{username.upper()}_PASSWORD"
        password = os.environ.get(variable)
        if password is None or not 8 <= len(password) <= 1024:
            raise RuntimeError(f"{variable} must contain between 8 and 1024 characters")
        salt = secrets.token_bytes(16)
        prepared[username] = Account(role, salt, password_digest(password, salt))
    accounts.update(prepared)
    try:
        yield
    finally:
        accounts.clear()


app = FastAPI(title="Rental API", lifespan=lifespan)
protected = APIRouter(dependencies=[Depends(user_only)])


@app.post("/login")
def login(credentials: LoginInput, response: Response) -> TokenResponse:
    account = accounts.get(credentials.username)
    stored = account if account is not None else accounts["alice"]
    valid = secrets.compare_digest(
        password_digest(credentials.password, stored.salt), stored.password_hash
    )
    if account is None or not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=issue_token(credentials.username, account.role))


@protected.get("/vehicles")
def list_vehicles(request: Request) -> Response:
    return forward("fleet", "GET", "/vehicles", request.headers["authorization"])


@protected.get("/vehicles/search")
def search_vehicles(name: str, request: Request) -> Response:
    path = "/vehicles/search?" + urlencode({"name": name})
    return forward("fleet", "GET", path, request.headers["authorization"])


@protected.post("/vehicles", status_code=201, dependencies=[Depends(staff_only)])
def create_vehicle(body: dict[str, object], request: Request) -> Response:
    return forward("fleet", "POST", "/vehicles", request.headers["authorization"], body)


@protected.delete(
    "/vehicles/{vehicle_id}", status_code=204, dependencies=[Depends(staff_only)]
)
def delete_vehicle(vehicle_id: PositiveId, request: Request) -> Response:
    return forward(
        "fleet", "DELETE", f"/vehicles/{vehicle_id}", request.headers["authorization"]
    )


@protected.post("/bookings", status_code=201)
def create_booking(
    body: dict[str, object], request: Request, identity: User
) -> Response:
    if identity.role != "renter":
        raise HTTPException(status_code=403, detail="Only renters can create bookings")
    return forward("fleet", "POST", "/bookings", request.headers["authorization"], body)


@protected.get("/bookings")
def list_bookings(request: Request) -> Response:
    return forward("fleet", "GET", "/bookings", request.headers["authorization"])


@protected.get("/bookings/{booking_id}")
def get_booking(booking_id: PositiveId, request: Request) -> Response:
    return forward(
        "fleet", "GET", f"/bookings/{booking_id}", request.headers["authorization"]
    )


@protected.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: PositiveId, request: Request) -> Response:
    return forward(
        "fleet",
        "POST",
        f"/bookings/{booking_id}/cancel",
        request.headers["authorization"],
    )


@protected.post("/bookings/{booking_id}/override-cancel")
def override_cancel_booking(booking_id: PositiveId, request: Request) -> Response:
    return forward(
        "fleet",
        "POST",
        f"/bookings/{booking_id}/override-cancel",
        request.headers["authorization"],
    )


@protected.post("/bookings/{booking_id}/agreement")
def generate_agreement(booking_id: PositiveId, identity: User) -> Response:
    # CWE-441: Unintended Proxy or Intermediary; intentionally delegate staff authority regardless of the caller's role.
    scoped = issue_token(
        "rental-api", "staff", booking_id=booking_id, expires_at=identity.exp
    )
    return forward("agreement", "POST", f"/agreements/{booking_id}", f"Bearer {scoped}")


@protected.get("/bookings/{booking_id}/agreement")
def get_agreement(booking_id: PositiveId, request: Request) -> Response:
    return forward(
        "fleet",
        "GET",
        f"/bookings/{booking_id}/invoice",
        request.headers["authorization"],
    )


app.include_router(protected)
