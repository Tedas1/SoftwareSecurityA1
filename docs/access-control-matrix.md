# Access-control matrix

Each service verifies HS256 JWTs through `Depends`. `/login` is the only public domain operation.
Missing or invalid tokens return 401; insufficient permissions return 403.
OpenAPI/docs contain no domain data.

| Fleet operation | Renter user token | Staff user token | Agreement-scoped token |
| --- | --- | --- | --- |
| List/search vehicles | Allow | Allow | Deny |
| Add/delete vehicle | Deny | Allow | Deny |
| Create booking | Allow, owner from `sub` | Deny | Deny |
| List bookings | Own only | All | Deny |
| Read one booking | Own only | Any | Bound booking; owner or staff |
| Cancel booking | Own only | Any | Deny |
| Override-cancel booking (CWE-862) | Any | Any | Deny |
| Save invoice | Deny | Deny | Bound booking; owner or staff |
| Retrieve invoice | Own only | Any | Deny |

## Intentional flaws

- **CWE-20:** `POST /vehicles` accepts whitespace-only names. It checks length
  (1-100), but does not trim. Staff authorization and other field checks remain.
- **CWE-89:** `GET /vehicles/search` inserts `name` into SQL with an f-string.
  The API URL-encodes the parameter, which does not prevent SQL injection.
- **CWE-862 / IDOR:** `POST /bookings/{id}/override-cancel` lets any authenticated
  renter or staff user cancel any booking. Normal `/cancel` checks ownership.
- **CWE-441:** Agreement generation delegates `sub="rental-api"`, `role="staff"`
  regardless of the caller's role. Renters can generate another renter's invoice
  even though direct reads are denied.

Vehicle creation, search, and override cancellation are exposed by both services.
`PUT /vehicles/{id}` is removed; invoice-saving PUT remains.

## Token and state rules

- User JWTs require `sub`, `role`, `iat`, and `exp`. Roles are `renter` or `staff`;
  lifetime is at most 900 seconds. Missing `scope` means `user`.
- Processor tokens require `scope="agreement"` and one positive `booking_id`.
  They cannot use user or bulk operations, or outlive the caller's token.
  The signing key is shared through the environment.
- New bookings take ownership from `sub` and default to `pending`.
  Requests cannot set ownership or status.
- Dates use `[start_date, end_date)`. Booking creation serializes the overlap
  check and insert, and captures the price in integer cents.
- Pending bookings block overlapping dates; cancellation frees them.
  Cancelled bookings and existing invoices remain readable, but new invoices
  cannot be generated or saved.
- Deleting a vehicle referenced by any booking returns 409.

## Rental API

- `POST /login` checks three fixed accounts. Environment passwords are hashed
  in memory with salted PBKDF2-HMAC-SHA256 (600,000 iterations). Roles are
  server-defined; unknown users and wrong passwords get the same 401 message.
- Fleet requests forward the caller's token unchanged for fleet to verify.
- `POST /bookings/{id}/agreement` sends a scoped token to the processor.
  `GET` retrieves the saved invoice through fleet's owner/staff checks.
  Clients cannot submit invoice content directly.
- No registration, password database, account management, or refresh tokens.

## Agreement processor

- `POST /agreements/{id}` requires an agreement token bound to that ID.
  User tokens are denied.
- Fetches the booking and saves its invoice through fleet using the scoped token.
- Validates fleet data, then passes a dictionary and server-selected temporary
  path to the renderer. Empty or oversized output fails without saving.
- Removes the temporary file after reading; fleet SQLite stores the invoice.
  The processor never opens the database.
- Fleet rechecks access and booking status on save. Cancellation during rendering
  returns 409; upstream and rendering failures are returned as errors.

## Secure Design Principle evidence

| Principle | Implementation | Test |
| --- | --- | --- |
| Least privilege | [`agreement_only` and `user_only`](../app/auth.py) restrict token use; the [processor](../app/agreement_processor/main.py) enforces the booking ID | [`test_least_privilege`](../tests/test_authz.py): scoped tokens cannot access bulk routes |
| Complete mediation | [Fleet](../app/fleet_resource_service/main.py) checks booking access; [auth](../app/auth.py) verifies each request | [`test_complete_mediation`](../tests/test_authz.py): direct cross-owner requests are denied |
| Fail-safe defaults | [Auth](../app/auth.py) rejects invalid tokens; the [schema](../app/fleet_resource_service/db.py) defaults bookings to `pending` | [`test_fail_safe_defaults`](../tests/test_authz.py): authentication and default status |
