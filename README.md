# Secure Car Rental System

Secure-SDLC course project with three FastAPI services, each running in its own
process. Only the fleet resource service will own the SQLite database.

## Current checkpoint: Step 2

Implemented: fleet SQLite schema, five-vehicle seed support, independently
verified JWTs, role/ownership/scoped authorization, fleet management, dated
bookings/cancellation and invoice persistence. The three services share the root
installation; the renderer remains a separately packaged editable dependency.

Login/JWT issuance, seeded user accounts, agreement rendering over HTTP,
cross-service routing, formal test suites and CI are not implemented yet. The
rental API and agreement processor still expose only documentation/OpenAPI.

The [lifecycle plan](docs/lifecycle-plan.md) was committed separately before
feature code in commit `466fca9`.

## Install (PowerShell, from the repository root)

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -e .\external\rental_invoice_render
```

The root project installs all three services and the dependencies listed in
[requirements.txt](requirements.txt), including the course's test and CI tools.
The renderer has its own [project metadata](external/rental_invoice_render/pyproject.toml)
and is installed editable, not copied into a service.

## Seed and run the fleet service (PowerShell)

From the repository root:

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:FLEET_DB_PATH = Join-Path (Get-Location) "runtime\fleet.sqlite3"
.\.venv\Scripts\python.exe -m app.fleet_resource_service.db
.\.venv\Scripts\python.exe -m uvicorn app.fleet_resource_service.main:app --host 127.0.0.1 --port 8001
```

Startup creates the schema but does not seed automatically. The seed command
inserts five vehicles with fixed IDs and does not overwrite existing IDs.
`FLEET_DB_PATH` defaults to `runtime\fleet.sqlite3`; only the fleet service opens
this database. Data and invoice content persist across restarts.

Fleet startup fails if `JWT_SECRET` is missing or shorter than 32 UTF-8 bytes.
Keep the generated key private and never commit it. Once the other services are
implemented, they must receive the same key, not independently generated keys.

## Run the other skeletons

Run these commands in separate terminals at the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.rental_api.main:app --host 127.0.0.1 --port 8000
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.agreement_processor.main:app --host 127.0.0.1 --port 8002
```

OpenAPI documents:

- Rental API: <http://127.0.0.1:8000/openapi.json>
- Fleet resource service: <http://127.0.0.1:8001/openapi.json>
- Agreement processor: <http://127.0.0.1:8002/openapi.json>

Use Ctrl+C in each terminal to stop that service.

## Fleet API contract

See the [access-control matrix](docs/access-control-matrix.md) for operations and
permissions. All fleet domain routes require a bearer JWT. Until Step 3 adds
login, a developer who controls `JWT_SECRET` can mint a temporary user token in
another terminal configured with the same key:

```powershell
$token = .\.venv\Scripts\python.exe -c "import os,time,jwt; now=int(time.time()); print(jwt.encode({'sub':'alice','role':'renter','iat':now,'exp':now+900}, os.environ['JWT_SECRET'], algorithm='HS256'))"
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri http://127.0.0.1:8001/vehicles -Headers $headers
$body = @{ vehicle_id = 1; start_date = "2030-06-01"; end_date = "2030-06-03" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/bookings -Headers $headers -ContentType "application/json" -Body $body
```

The token's subject establishes ownership; neither ownership nor initial status
is accepted in a booking request. New bookings default to `pending`. Rental
dates use an exclusive return date. Overlapping pending bookings return 409,
including concurrent requests. Cancellation releases the interval. The total
price is captured in integer cents and survives later fleet price changes.

Normal user tokens cannot write invoices. Only `scope="agreement"` tokens bound
to one `booking_id` can fetch that booking and write its text invoice; they cannot
list bookings, access the fleet, cancel bookings or retrieve invoices. The rental
API will issue these tokens when agreement processing is implemented.

## External renderer

`rental_invoice_render.render_invoice(invoice, output_path)` accepts a dictionary
and a `pathlib.Path`, writes a UTF-8 text invoice, and returns that path. The
agreement processor will choose the output path; HTTP callers must never choose
filesystem paths. Rendering and filesystem errors propagate to the caller.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m bandit -r app
```

Functional and authorization suites, with exact pytest and seed commands, arrive
in Step 6; the fleet-only seed command is available above. No formal test files
exist at this checkpoint. Security-demonstration tests wait for separately
supplied requirements in Step 7. CI and its saved artifacts arrive in Step 8;
no CI success is claimed here.

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