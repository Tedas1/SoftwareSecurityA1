# Secure Car Rental System

Secure-SDLC course project with three FastAPI services, each running in its own
process. Only the fleet resource service owns the SQLite database.

## Current checkpoint: Steps 1-6 complete; documentation and CI from Step 8

Implemented: fleet SQLite schema, five-vehicle seed support, independently
verified JWTs, role/ownership/scoped authorization, fleet management, dated
bookings/cancellation and invoice persistence. The three services share the root
installation; the renderer remains a separately packaged editable dependency.

The rental API now authenticates three demo accounts, issues 15-minute JWTs,
verifies callers, forwards fleet operations over HTTP and delegates agreement
requests with booking-scoped tokens. It never opens the fleet database.

The agreement processor now verifies scoped JWTs, fetches one booking over HTTP,
renders through the installed external package, and saves the invoice through
fleet. The complete login, booking, generation and retrieval flow has been
verified with three independent Uvicorn processes and a fresh seeded SQLite
database, including cross-renter denials and staff operations. Formal functional
and authorization pytest suites cover the required behavior. Step 7 is deferred
until its PoC requirements are supplied; the final report remains last.

The [lifecycle plan](docs/lifecycle-plan.md) was committed separately before
feature code in commit `466fca9`.

## Install (PowerShell, from the repository root)

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation --check-build-dependencies -e . -e .\external\rental_invoice_render
.\.venv\Scripts\python.exe -m pip check
```

The pinned [requirements](requirements.txt) include direct/transitive packages
and build/CI tools. `--no-deps` prevents silently installing unlisted packages;
build-requirement checks and `pip check` reject missing/incompatible inputs.
The root project installs all three services.
The renderer has its own [project metadata](external/rental_invoice_render/pyproject.toml)
and is installed editable, not copied into a service.

## Seed and run the fleet service (PowerShell)

From the repository root:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generate that shared key once and retain it privately outside the repository.
Enter the same value at all three service prompts; never include it in
commits or captured logs:

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Shared JWT secret: '))"
$env:FLEET_DB_PATH = Join-Path (Get-Location) "runtime\fleet.sqlite3"
.\.venv\Scripts\python.exe -m app.fleet_resource_service.db
.\.venv\Scripts\python.exe -m uvicorn app.fleet_resource_service.main:app --host 127.0.0.1 --port 8001
```

Startup creates the schema but does not seed automatically. The seed command
inserts five vehicles with fixed IDs and does not overwrite existing IDs.
`FLEET_DB_PATH` defaults to `runtime\fleet.sqlite3`; only the fleet service opens
this database. Data and invoice content persist across restarts.

Fleet startup fails if `JWT_SECRET` is missing or shorter than 32 UTF-8 bytes.
Keep the generated key private and never commit it. All three services receive
the same key, not independently generated keys.

## Run the rental API (PowerShell)

In another terminal at the repository root, configure the **same** `JWT_SECRET`
used by fleet. Supply three private demo passwords (8-1024 characters); these
commands prompt without echo and do not put passwords in command history:

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Shared JWT secret: '))"
$env:ALICE_PASSWORD = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Alice password: '))"
$env:BOB_PASSWORD = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Bob password: '))"
$env:CAROL_PASSWORD = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Carol password: '))"
$env:FLEET_SERVICE_URL = "http://127.0.0.1:8001"
$env:AGREEMENT_SERVICE_URL = "http://127.0.0.1:8002"
```

Both service URLs default to the values shown. Rental API startup fails for a
missing/short signing key or missing/invalid demo passwords. Alice and Bob are
renters; Carol is staff. Passwords are salted PBKDF2 hashes in memory only; fixed
accounts are recreated at startup from the environment, not stored in SQLite.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.rental_api.main:app --host 127.0.0.1 --port 8000
```

## Run the agreement processor

In a third terminal at the repository root:

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Shared JWT secret: '))"
$env:FLEET_SERVICE_URL = "http://127.0.0.1:8001"
.\.venv\Scripts\python.exe -m uvicorn app.agreement_processor.main:app --host 127.0.0.1 --port 8002
```

Use the same shared key. The processor needs no demo passwords or database path.
Startup fails without a valid key. Its only domain route is
`POST /agreements/{booking_id}`, and normal user JWTs are denied: only the rental
API should delegate an agreement-scoped JWT for a specific booking.

OpenAPI documents:

- Rental API: <http://127.0.0.1:8000/openapi.json>
- Fleet resource service: <http://127.0.0.1:8001/openapi.json>
- Agreement processor: <http://127.0.0.1:8002/openapi.json>

Use Ctrl+C in each terminal to stop that service.

## Login and book through the rental API

See the [access-control matrix](docs/access-control-matrix.md) for operations and
permissions. The rental API and fleet domain routes require a bearer JWT.
In a client terminal, authenticate without placing a password in command history:

```powershell
$password = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Alice password: '))"
$credentials = @{ username = "alice"; password = $password } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/login -ContentType "application/json" -Body $credentials
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Uri http://127.0.0.1:8000/vehicles -Headers $headers
$body = @{ vehicle_id = 1; start_date = "2030-06-01"; end_date = "2030-06-03" } | ConvertTo-Json
$booking = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/bookings -Headers $headers -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8000/bookings/$($booking.id)" -Headers $headers
```

### Generate and retrieve the agreement

With all three services running and the variables from the previous example:

```powershell
$agreementUri = "http://127.0.0.1:8000/bookings/$($booking.id)/agreement"
$generated = Invoke-RestMethod -Method Post -Uri $agreementUri -Headers $headers
$saved = Invoke-RestMethod -Uri $agreementUri -Headers $headers
$saved.content
```

Generation follows rental API -> agreement processor -> fleet fetch -> external
renderer -> fleet invoice save. Retrieval follows rental API -> fleet. The
processor receives only a JWT bound to this booking, never the general user JWT.
The returned JSON has `booking_id` and `content`; both calls return the same
stored text.

To cancel the booking as its owner:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/bookings/$($booking.id)/cancel" -Headers $headers
```

Run the example against an available interval: repeating creation for the same
vehicle/dates while a pending booking exists returns 409.

The token's subject establishes ownership; neither ownership nor initial status
is accepted in a booking request. New bookings default to `pending`. Rental
dates use an exclusive return date. Overlapping pending bookings return 409,
including concurrent requests. Cancellation releases the interval. The total
price is captured in integer cents and survives later fleet price changes.

Normal user tokens cannot write invoices. Only `scope="agreement"` tokens bound
to one `booking_id` can fetch that booking and write its text invoice; they cannot
list bookings, access the fleet, cancel bookings or retrieve invoices.

The rental API mirrors the fleet vehicle/booking/cancellation routes. Staff
authenticate as Carol to manage the fleet and see/cancel any booking.
`POST /bookings/{id}/agreement` delegates a scoped JWT to the processor, while
`GET /bookings/{id}/agreement` retrieves an existing invoice through fleet.
All three services participate in the verified generation flow. The API
propagates downstream errors rather than pretending an agreement exists.
Unreachable downstream services return 502; timeouts return 504. Fleet status
codes and authorization errors are preserved.

## External renderer

`rental_invoice_render.render_invoice(invoice, output_path)` accepts a dictionary
and a `pathlib.Path`, writes a UTF-8 text invoice, and returns that path. The
agreement processor chooses the output path; HTTP callers must never choose
filesystem paths. Rendering and filesystem errors propagate to the caller.

The processor imports the installed package directly. It renders to a unique
temporary `invoice.txt`, reads bounded UTF-8 text, removes the temporary file,
and writes the text back to fleet. SQLite is the persisted invoice copy, so no
separate processor file-retention system is needed. Invalid upstream booking
data returns 502; rendering failures or empty/oversized output return 500 without
saving. Cancellation before write-back returns fleet's 409.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m bandit -r app
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off
.\.venv\Scripts\python.exe -m pytest -q tests\test_functional.py tests\test_authz.py
```

The suites create a fresh temporary SQLite database, seed it through the fleet
module, generate private test credentials, and run three real service processes
on temporary loopback ports. No manually running services or environment setup
are needed for tests. Each test uses its own vehicle/booking records; cleanup
stops only the processes started by the fixture. Existing runtime data is not
touched.

The fleet module command above is the idempotent seed script; no duplicate
wrapper is needed. The rental API creates the three fixed demo accounts from
its configured environment passwords at startup.

The [authorization suite](tests/test_authz.py) includes one named evidence test
for each principle: `test_least_privilege`, `test_complete_mediation`, and
`test_fail_safe_defaults`. The [functional suite](tests/test_functional.py)
covers seeding, the complete agreement workflow, staff fleet/booking operations,
price snapshots, date availability and concurrent overlap rejection.

Security-demonstration tests wait for separately supplied requirements in
Step 7 and are not part of the initial CI gate.

## CI and actual evidence

The [workflow](.github/workflows/ci.yml) runs on push and pull requests using
read-only repository permissions and pinned official actions. Each job installs
the approved inputs in a clean virtual environment.

- Build: editable services/renderer, `pip check`, Ruff, Bandit over `app/`, and
  pip-audit. Findings are not globally suppressed. Native pip-audit blocks all
  known findings, including high/critical; custom severity filtering is deferred.
- Test: the two functional/authorization suites against fresh temporary SQLite.
  `pipefail` preserves pytest's failure status while saving its console output.
- Actual `actions/upload-artifact` outputs: `build-reports` contains
  `bandit.json` and `pip-audit.json`; `pytest-results` contains `pytest.xml` and
  `pytest.txt`. Uploads run even when checks fail.

Use [Actions](https://github.com/Tedas1/SoftwareSecurityA1/actions/workflows/ci.yml)
to inspect the run's commit, result and downloadable artifacts. A workflow
definition or local scan is not proof of a successful Actions run. Artifact
contents must come from actual uploads, never hand-written replacements.

Version pins are not wheel hash/provenance verification. TLS, independent
signing authority, password lifecycle, abuse controls, durable audit logging,
database/invoice retention and recovery remain production-readiness gaps.

## Design documentation and remaining submission work

- [Lifecycle plan](docs/lifecycle-plan.md), originally committed before features.
- [Access-control matrix and principle evidence](docs/access-control-matrix.md).
- [STRIDE analysis](docs/stride-analysis.md).
- [Threat model, asset register and trust boundaries](docs/threat-model.md).

Step 7 remains pending owner requirements. Write the 2,000-2,500-word report only
after that implementation and real CI verification, citing actual commits,
tests and logs. The project owner drafts the AI-use declaration.

## Build checkpoints

1. Skeleton and external package.
2. Fleet schema, seed support, and authorization dependencies.
3. Rental authentication, JWT issuance, and routing.
4. Agreement processor using fleet HTTP calls and the external renderer.
5. Complete three-service flow.
6. Seed script and functional/authorization suites.
7. Separately specified security-demonstration tests.
8. Final documentation, actual CI verification, and submission report written last.

Each major step is confirmed before proceeding and committed incrementally.
The project owner writes the university AI-use declaration.