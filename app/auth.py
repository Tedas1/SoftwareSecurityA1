import os
from typing import Annotated, Literal, Self

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

TOKEN_LIFETIME_SECONDS = 900
bearer = HTTPBearer(auto_error=False)


def jwt_key() -> str:
    key = os.environ.get("JWT_SECRET")
    if not key or len(key.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 bytes")
    return key


class Claims(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    sub: str = Field(min_length=1, max_length=100)
    role: Literal["renter", "staff"]
    iat: int = Field(ge=0)
    exp: int = Field(ge=0)
    scope: Literal["user", "agreement"] = "user"
    booking_id: int | None = Field(default=None, gt=0, le=2**63 - 1)

    @model_validator(mode="after")
    def valid_authority(self) -> Self:
        if not 0 < self.exp - self.iat <= TOKEN_LIFETIME_SECONDS:
            raise ValueError("Token lifetime must be between 1 and 900 seconds")
        if (self.scope == "agreement") != (self.booking_id is not None):
            raise ValueError("Only agreement tokens must bind exactly one booking")
        return self


def authenticate(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Claims:
    """Verify signed, short-lived authority independently on every request."""
    unauthorized = HTTPException(
        status_code=401,
        detail="Missing or invalid bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            jwt_key(),
            algorithms=["HS256"],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        return Claims.model_validate(payload)
    except (jwt.InvalidTokenError, ValidationError) as exc:
        raise unauthorized from exc


Principal = Annotated[Claims, Depends(authenticate)]


def user_only(identity: Principal) -> Claims:
    """Deny booking-scoped processor tokens access to general user operations."""
    if identity.scope != "user":
        raise HTTPException(status_code=403, detail="A user token is required")
    return identity


User = Annotated[Claims, Depends(user_only)]


def staff_only(identity: User) -> Claims:
    if identity.role != "staff":
        raise HTTPException(status_code=403, detail="Staff access is required")
    return identity
