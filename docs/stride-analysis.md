# STRIDE analysis

Scope: the three HTTP processes, fleet SQLite and the installed invoice package.
This is a loopback course demo, not a production deployment. Boundaries and assets
are in the [threat model](threat-model.md); permissions are in the
[access-control matrix](access-control-matrix.md).

| Category | Concrete threat | Implemented control / evidence | Remaining limitation |
| --- | --- | --- | --- |
| Spoofing | Caller forges identity/role or bypasses the API with a direct fleet request | Every service verifies HS256, required claims, expiry and scope through [auth dependencies](../app/auth.py); fixed server-side login roles; `test_fail_safe_defaults` | Shared signing secret; no token revocation or key rotation |
| Tampering | Caller changes ownership/status/price, overlaps a booking, or supplies an output path | [Fleet](../app/fleet_resource_service/main.py) rejects extra fields, uses parameterized SQL, server defaults, captured prices and a serialized check/insert; [processor](../app/agreement_processor/main.py) chooses the temporary path and validates data/output | Version pins are not package hash/provenance verification; editable source still requires review |
| Repudiation | User/staff denies creating or cancelling a booking | JWT subject establishes request identity; persisted booking owner and [Git history/CI](../.github/workflows/ci.yml) support development traceability | No durable transaction audit or cancellation-actor history; development logs are not non-repudiation |
| Information disclosure | Bob reads Alice's booking/invoice; credentials enter output | Owner/staff checks on each fleet call; scoped processing; generic failed-login response; test secrets are random and omitted from fixture repr; `test_renter_boundaries` and `test_complete_mediation` | HTTP has no TLS; SQLite/environment data depend on host permissions; no retention policy |
| Denial of service | Slow downstream, excessive rendering output, repeated login attempts or conflicting writes | [HTTP helper](../app/http.py) has a 10-second timeout; processor reads at most 100001 characters and rejects output over 100000; atomic overlap rejection is functionally tested | No rate limits, capacity/load guarantee, global request-size limit or SQLite high-availability design |
| Elevation of privilege | Renter acts as staff, or processor uses staff authority to enumerate bookings | Roles come from configuration; staff dependencies; `scope="agreement"` binds one ID and cannot use bulk/user operations; `test_login_roles_and_rejection` and `test_least_privilege` | A compromised HS256 verifier holding the shared secret can mint claims; scoped request handling is not OS-level isolation |

The evidence tests are in [the authorization suite](../tests/test_authz.py) and
[the functional suite](../tests/test_functional.py). They demonstrate the stated
functional/access-control rules, not resistance to every STRIDE threat.

Known dependency findings are scanned without ignore lists. The initial local
audit identified the bundled pip 25.2; the installation manifest now pins a fixed
pip version. Actual CI scanner artifacts, not this statement, establish a run's
audit result. Separately assigned security-demonstration PoCs remain pending.
