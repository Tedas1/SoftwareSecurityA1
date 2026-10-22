# STRIDE analysis

Scope: three HTTP services, fleet SQLite, and the invoice renderer.
See the [threat model](threat-model.md) for boundaries and the
[access-control matrix](access-control-matrix.md) for permissions.

| Category | Threat | Controls | Gaps |
| --- | --- | --- | --- |
| Spoofing | Forged identity or role; direct fleet requests | Each service checks signature, claims, expiry, and scope through [auth](../app/auth.py); login roles are server-defined | Shared signing key; no revocation or rotation |
| Tampering | Changed ownership, prices, dates, or output paths | [Fleet](../app/fleet_resource_service/main.py) controls booking fields, parameterizes writes, and serializes booking creation; [processor](../app/agreement_processor/main.py) selects paths and validates output | Search uses SQL interpolation (CWE-89); whitespace-only vehicle names pass validation (CWE-20) |
| Repudiation | User denies creating or cancelling a booking | JWT identifies the caller; SQLite stores the booking owner | No transaction audit or cancellation-actor history |
| Information disclosure | Bob reads Alice's booking or invoice | Normal reads check owner/staff access; failed logins use a generic response | Agreement generation leaks cross-renter invoices (CWE-441); no TLS; host permissions protect SQLite and environment data |
| Denial of service | Slow services, oversized invoices, repeated logins, conflicting bookings | [HTTP timeout](../app/http.py) is 10 seconds; processor reads at most 100001 characters and rejects output over 100000; booking overlap checks are atomic | No rate limits or global request-size limit |
| Elevation of privilege | Renter uses staff authority or cancels another renter's booking | Server-defined roles; scoped tokens are bound to one booking and denied bulk routes | Agreement delegation grants staff authority (CWE-441); override cancellation skips authorization (CWE-862); any service with the shared key can mint tokens |

Tests: [authorization](../tests/test_authz.py) and
[functional](../tests/test_functional.py). [CI](../.github/workflows/ci.yml)
runs Bandit and pip-audit without finding suppressions.
