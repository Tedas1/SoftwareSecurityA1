# Access-control matrix

Every protected rental API endpoint and every fleet domain endpoint verifies an
HS256 JWT itself through `Depends`. The only unauthenticated domain operation
is `/login`.
Missing, expired, malformed or incorrectly signed tokens return 401. A valid
token with insufficient authority returns 403. OpenAPI/docs expose no domain data.

| Fleet operation | Renter user token | Staff user token | Agreement-scoped token |
| --- | --- | --- | --- |
| List vehicles | Allow | Allow | Deny |
| Add/update/delete vehicle | Deny | Allow | Deny |
| Create booking | Allow, owner from `sub` | Deny | Deny |
| List bookings | Own only | All | Deny |
| Read one booking | Own only | Any | Bound booking only; renter ownership still checked |
| Cancel booking | Own only | Any (override) | Deny |
| Save invoice | Deny | Deny | Bound booking only; renter ownership still checked |
| Retrieve invoice | Own only | Any | Deny |

## Token and state rules

- User JWTs require `sub`, `role`, `iat`, `exp`; `role` is `renter` or `staff`.
  Lifetime is at most 900 seconds. An absent `scope` means `user`.
- Processor JWTs retain the initiating user's subject and role, add
  `scope="agreement"` and one positive `booking_id`, and cannot use user/bulk
  operations even if the initiating role is staff.
- The rental API issues scoped tokens for agreement requests and never passes a
  general user token to the processor. Delegation cannot extend the user's expiry.
  The shared signing key is an environment secret.
  Independent signing authority is a documented production-readiness gap.
- Ownership/status cannot be supplied during booking creation: extra fields
  are rejected. The database defaults status to `pending`.
- Rental intervals are `[start_date, end_date)`. Pending reservations block
  overlaps; cancellation releases the interval. Creation captures the total
  price in integer cents and serializes the overlap check and insert.
- Cancelled bookings remain readable but cannot generate or save new invoices.
  Existing invoices remain readable by the owner or staff.
- Vehicles referenced by any booking cannot be deleted; return 409 instead.

## Rental API

- `POST /login` checks the three fixed accounts using environment-provided
  passwords hashed in memory with salted PBKDF2-HMAC-SHA256 (600,000 iterations).
  Roles come from server configuration, never login input. Failed logins return
  the same 401 message for unknown users and wrong passwords.
- Protected fleet routes forward the signed caller token unchanged; the fleet
  service independently rechecks signature, role, scope and ownership.
- `POST /bookings/{id}/agreement` sends only a booking-scoped token to the
  processor route `POST /agreements/{id}`. Staff can initiate processing, but
  even their processor token has no bulk access. The processor and fleet must
  check the bound booking and original renter's ownership.
- `GET /bookings/{id}/agreement` retrieves the stored invoice through fleet
  authorization. No public rental API route writes invoice content directly.
- No registration, password database, account-management API or refresh tokens
  are added. These are demo accounts, not a production identity system.

## Agreement processor

- Only `POST /agreements/{id}` is a domain endpoint. It requires a verified
  agreement-scoped JWT bound to that exact ID. General user tokens are denied.
- It fetches only that booking and writes only that booking's invoice through
  fleet HTTP endpoints. Both calls carry the scoped token, not a general token.
- It validates fleet data before rendering. The separately installed renderer
  receives a dictionary and a server-selected temporary path; no caller path
  is accepted or used. Empty/oversized output fails without saving an invoice.
- The temporary file is removed after reading. Fleet SQLite stores the canonical
  text invoice; the processor never opens the database.
- Fleet rechecks ownership and current booking status when saving. Cancellation
  during rendering returns 409 rather than saving an invoice for a cancelled
  booking. No failed upstream/rendering operation is reported as success.

This matrix documents implemented Step 2-4 decisions. The complete three-service
checkpoint and Step 6 formal functional/authorization suites remain pending.
