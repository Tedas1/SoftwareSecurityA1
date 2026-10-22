# Secure Car Rental System

Secure-SDLC course project with three FastAPI services, each running in its own
process. Only the fleet resource service will own the SQLite database.

## Current checkpoint: Step 1

Implemented: installable service skeletons and a separately packaged text-invoice
renderer. Authentication, authorization, database, seed data, booking routes,
service-to-service calls, and CI are not implemented yet. The skeletons expose
only FastAPI's documentation and OpenAPI endpoints, not domain operations.

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

## Run

Run one command in each of three PowerShell terminals, all at the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.rental_api.main:app --host 127.0.0.1 --port 8000
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.fleet_resource_service.main:app --host 127.0.0.1 --port 8001
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.agreement_processor.main:app --host 127.0.0.1 --port 8002
```

OpenAPI documents:

- Rental API: <http://127.0.0.1:8000/openapi.json>
- Fleet resource service: <http://127.0.0.1:8001/openapi.json>
- Agreement processor: <http://127.0.0.1:8002/openapi.json>

Use Ctrl+C in each terminal to stop that service.

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
in Step 6. No tests or seed command exist at this checkpoint. Security-demonstration
tests wait for separately supplied requirements in Step 7. CI and its saved
artifacts arrive in Step 8; no CI success is claimed here.

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