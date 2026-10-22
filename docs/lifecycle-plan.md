# Secure development lifecycle plan

This plan is committed before feature implementation. Evidence named below is
planned, not a claim that tests, controls, or CI runs already exist. Update the
evidence links as each build step is completed; retain the original Git history.

## Scope and decisions

- Three separately running HTTP services: rental API, fleet resource service,
  and agreement processor. Only the fleet service owns the SQLite database.
- The rental API authenticates users. Each downstream service verifies signed,
  short-lived JWTs through FastAPI dependencies and enforces its own authority
  checks. Request-body user identifiers never establish authority.
- Renters access only their bookings; staff manage the fleet and all bookings.
- Least privilege: processing uses booking-scoped authority, not a general
  bulk-booking credential. The processor must not be able to list all bookings,
  including when a staff user initiated a request.
- Complete mediation: fleet authorization applies to every request, including
  direct requests and calls from the processor.
- Fail-safe defaults: missing or invalid credentials deny access; newly created
  bookings start as `pending`, regardless of caller-supplied status.
- The invoice renderer is a separately packaged, editable dependency. The
  processor chooses server-controlled output paths; callers cannot select paths.

## Four phases and release gates

| Phase / lifecycle activity | Asset | Threat | Control / decision | Planned test or evidence | Gate |
| --- | --- | --- | --- | --- | --- |
| 1. Requirements and planning: define ownership and role rules | Booking and invoice confidentiality | A renter reads another renter's records | Own-booking access for renters; explicit staff exceptions | Access-control matrix; alice/bob/carol functional and authorization cases | Approve role rules before implementing fleet routes |
| 1. Requirements and planning: record safe defaults | Booking integrity | Unauthenticated or prematurely approved bookings | Deny missing/bad tokens; server assigns `pending` | Fail-safe-defaults authorization test | Required test passes before release |
| 2. Design: map HTTP and package trust boundaries | Identity and authorization context | Forged identity or confused-deputy access | Every service verifies JWTs; no body identity authority | Threat model, STRIDE analysis, direct fleet-call authorization test | Review boundaries before wiring the full flow |
| 2. Design: constrain processor authority | All bookings | Processor uses a broad caller token to enumerate records | Booking-scoped processing authority; no bulk access | Least-privilege test rejecting processor bulk access | Scoped access works and bulk access is denied |
| 2. Design: mediate resource operations | Booking ownership and status | Trusted-service bypass of ownership checks | Fleet rechecks caller authority on every operation | Complete-mediation test rejecting a cross-owner downstream call | Required authorization suite passes |
| 3. Implementation: package and review dependencies | Application and invoice output | Dependency substitution or known vulnerable packages | Separate renderer project; explicit editable installation; dependency audit | Install logs, lint results, saved Bandit and pip-audit outputs | Lint passes; no high/critical audited dependency finding |
| 3. Implementation: protect database and credentials | SQLite records and JWT signing key | SQL injection, leaked keys, or unsafe file writes | Parameterized SQL; environment-supplied key; server-selected invoice paths; exclude runtime files from Git | Code review and Bandit output; configuration and authorization checks in the planned suites | No embedded key; assess findings without global suppression |
| 4. Verification and release: exercise user workflows | Booking and invoice availability/integrity | Broken booking, cancellation, or three-service agreement flow | Fresh test database; functional and authorization suites | Saved pytest results, including three-service flow and three principle tests | Any functional or authorization failure blocks release |
| 4. Verification and release: preserve reproducible evidence | Submission and release evidence | Fabricated logs or untraceable decisions | Incremental commits; actual CI artifact uploads; report written last | Commit IDs, real Actions run URL, uploaded pytest/Bandit/pip-audit artifacts | No claim of CI success without an actual successful run |

## Build sequence and checkpoints

0. Commit this plan separately before feature code.
1. Skeleton and external package.
2. Fleet schema, seed support, and authorization dependencies.
3. Rental authentication, JWT issuance, and HTTP routing.
4. Agreement processor using HTTP and the installed renderer.
5. Complete three-service flow.
6. Seed script and functional/authorization tests, including one evidence test
   for each of the three principles.
7. Security-demonstration tests only after their requirements are supplied.
8. Final documentation, real CI verification, and then the submission report.

Confirm with the project owner between major steps and commit incrementally.
The initial CI test gate includes only functional and authorization suites.
Do not invent security-demonstration tests or make them part of that gate yet.

## Verification policy and evidence handling

- Build job: install the application services and editable external package;
  run Ruff, Bandit over `app/`, and pip-audit. Retain scanner output even on
  failure. Do not globally suppress findings.
- Dependency gate: fail for high/critical pip-audit findings. Select and document
  a reliable severity source during CI implementation; unknown severity must
  not silently be treated as low risk.
- Test job: use a fresh SQLite database and run functional/authorization tests.
  Upload actual pytest, Bandit, and pip-audit output through Actions artifacts.
- Keep logs free of passwords, bearer tokens, and signing keys.
- Report 2,000–2,500 words, excluding the specified ancillary material, only
  after implementation; cite real commits, tests, and logs.
- The project owner writes the university AI-use declaration.

## Release limitations and maintenance handoff

Before production use, assess TLS, key rotation and service-specific signing
authority, password lifecycle and abuse controls, audit logging, invoice access
and retention, SQLite concurrency/backups, and dependency update ownership.
These are readiness gaps to document, not permission to add extra project
features. Re-run gates after changes and revise the threat model when roles,
routes, dependencies, or trust boundaries change.
