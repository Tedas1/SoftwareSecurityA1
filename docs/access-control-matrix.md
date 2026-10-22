# Access-control matrix

Every fleet domain endpoint verifies an HS256 JWT itself through `Depends`.
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
- The rental API will issue scoped tokens in a later step; never pass a general
  user token to the processor. The shared signing key is an environment secret.
  Independent signing authority is a documented production-readiness gap.
- Ownership/status cannot be supplied during booking creation: extra fields
  are rejected. The database defaults status to `pending`.
- Rental intervals are `[start_date, end_date)`. Pending reservations block
  overlaps; cancellation releases the interval. Creation captures the total
  price in integer cents and serializes the overlap check and insert.
- Cancelled bookings remain readable but cannot generate or save new invoices.
  Existing invoices remain readable by the owner or staff.
- Vehicles referenced by any booking cannot be deleted; return 409 instead.

This matrix documents Step 2 decisions, not a claim that later services or the
Step 6 functional/authorization suites are already implemented.
