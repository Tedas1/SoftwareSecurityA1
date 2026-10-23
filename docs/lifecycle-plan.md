# Secure development lifecycle plan

The initial plan was committed as `466fca9` before feature code, with formal tests
added in `b4dbb37`. This revision describes the current implementation, including
the four intentional vulnerabilities documented in the [README](../README.md).

## Scope and requirements

- Renters should create, view and cancel their own bookings, then generate and
  retrieve their agreements. Staff should manage vehicles and view or cancel any
  booking. These are the intended permissions; the exceptions are listed below.
- Alice and Bob are demo renters; Carol is staff. Passwords come from the
  environment, and the seed command adds five vehicles.
- Three HTTP services run in separate processes. Only fleet opens SQLite. The
  processor calls fleet and uses a separately installed invoice renderer.
- The [threat model](threat-model.md) records assets and trust boundaries;
  the [access-control matrix](access-control-matrix.md) records permissions;
  [STRIDE](stride-analysis.md) records threats, affected assets, impacts,
  controls and gaps.

## Implemented controls and known flaws

- Each service verifies JWTs independently using a shared environment key.
  User tokens last at most 15 minutes; booking ownership comes from the token.
- Agreement tokens are bound to one booking and cannot use bulk or user routes.
  However, the API delegates `sub="rental-api"`, `role="staff"` regardless of the
  caller's role. This lets renters generate another renter's invoice (CWE-441).
- Normal booking reads, invoice retrieval and cancellation check owner/staff
  access. Override cancellation omits role and ownership checks (CWE-862).
- New bookings default to `pending`. Fleet stores prices in integer cents and
  serializes the overlap check and insert.
- Vehicle names are length-checked but accept whitespace-only input (CWE-20).
  Vehicle search interpolates SQL instead of using parameters (CWE-89).
- The renderer writes to a server-selected temporary path. The processor checks
  the output and removes the temporary file, then saves invoice text through fleet.

## Lifecycle phases

| Phase | Work and evidence | Acceptance criteria |
| --- | --- | --- |
| 1. Requirements | Define operations, assets, permissions and trust boundaries in the linked security docs. | Intended permissions and known exceptions are explicit; threats identify controls and gaps. |
| 2. Implementation and build | Build the three services and separate renderer; pin dependencies; provide clean-install commands and CI checks. | Installation checks and Ruff pass. Bandit and pip-audit findings fail the build without suppression. The intentional SQL injection is expected to fail Bandit. |
| 3. Testing | Run functional and authorization suites against a temporary database; reproduce the four flaws using the README steps. | Tests cover normal behavior and demonstrate the intentional flaws. Passing tests do not mean the application is secure. |
| 4. Release and operation | Use actual test and scan results in the course report; document deployment and maintenance gaps. | Do not treat the demo as production-ready or a workflow definition as evidence of a successful CI run. |

## Assets, controls and evidence

Review these links when requirements or implementation change. The
[matrix](access-control-matrix.md) maps the three secure design principles to
code and tests; those tests cover specific controls, not every route.

| Asset | Control or known gap | Evidence |
| --- | --- | --- |
| Credentials and JWTs | Verified claims, server-defined login roles, booking scope; shared signing authority remains a risk | `test_login_roles_and_rejection`, `test_least_privilege`, `test_fail_safe_defaults` in [authorization tests](../tests/test_authz.py) |
| Booking ownership and invoices | Normal owner/staff checks; agreement delegation and override cancellation intentionally bypass intended permissions | `test_complete_mediation`, `test_agreement_confused_deputy_composition_demo`, `test_override_cancel_missing_authorization_demo` in [authorization tests](../tests/test_authz.py) |
| Fleet and booking data | Fixed prices and atomic overlap checks; whitespace-only names and SQL injection remain | `test_booking_price_and_availability`, `test_concurrent_overlap_rejection`, and input-validation/search demos in [functional tests](../tests/test_functional.py) |
| Invoice files | Server-selected path, bounded output and fleet write-back | [Processor implementation](../app/agreement_processor/main.py) and `test_renter_booking_and_agreement_flow` in [functional tests](../tests/test_functional.py) |
| Source and dependencies | Pinned inputs, installation checks, lint and unsuppressed scans | [Requirements](../requirements.txt), [CI workflow](../.github/workflows/ci.yml), and reports from actual runs |

## Verification and evidence

- Follow the [README](../README.md) for installation, local checks and manual
  vulnerability demonstrations. The pinned requirements include dependencies
  and build tools. Installation uses `--no-deps`, checks build requirements and
  runs `pip check`.
- CI runs on pushes and pull requests. The build job runs installation checks,
  Ruff, Bandit over `app/`, and pip-audit. pip-audit blocks all known findings;
  there is no severity filter or finding suppression.
- The independent test job runs the functional and authorization suites with a
  temporary SQLite database and generated credentials. Existing runtime data
  is untouched. Flaw demonstrations are included in these suites.
- `build-reports` contains `bandit.json` and `pip-audit.json`; `pytest-results`
  contains `pytest.xml` and `pytest.txt`. Uploads are attempted even after failed
  checks. Use actual Actions results and artifacts when reporting outcomes.
- Keep passwords, bearer tokens and signing keys out of logs and artifacts.

## Report and maintenance

Production use would require fixing the four intentional flaws and addressing
TLS, key rotation/revocation, service-specific signing authority, password
management, rate limits, audit logs, invoice retention, SQLite backups/recovery,
renderer isolation and dependency provenance checks.

Assign owners for dependency updates and operational controls before deployment.
Re-run checks after changes, and update the security docs when roles, routes,
dependencies or trust boundaries change.
