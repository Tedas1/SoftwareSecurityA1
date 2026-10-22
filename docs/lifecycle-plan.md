# Secure development lifecycle plan

The initial plan was committed as `466fca9` before feature code. This later
revision records the four course phases and implemented decisions; it does not
replace or backdate the original. Steps 1-6 were committed incrementally, ending
with formal tests in `b4dbb37`.

## Requirements baseline

- Operations: authenticate; renters create, view and cancel their own bookings,
  generate agreements and retrieve them; staff list all bookings, manage the
  fleet and override-cancel any booking.
- Seed identities: alice and bob are renters; carol is staff; approximately five
  vehicles. The processor receives booking-scoped authority, not a staff role.
- Asset register: credentials and JWT signing key; identity and authorization
  claims; fleet records; bookings and ownership/status; invoices and output
  files; source, dependencies, build artefacts and CI evidence.
- Components and trust boundaries: client to rental API; rental API to fleet
  resource service or agreement processor; processor to fleet resource service;
  fleet service to its SQLite database; processor to the separately installed
  renderer and output filesystem. Only the fleet service owns the database.
- Design records: [access-control matrix](access-control-matrix.md),
  [STRIDE analysis](stride-analysis.md), and
  [asset register/trust boundaries](threat-model.md).

## Authorization and implementation decisions

- Identity comes from verified JWTs, never body user IDs; the key is an
  environment secret. Each service verifies JWTs independently.
- Least privilege: the processor gets one booking-scoped token, never bulk
  authority, even for a staff-initiated request.
- Complete mediation: fleet checks scope and ownership on every call.
- Fail-safe defaults: missing/bad tokens deny; the database defaults new bookings
  to `pending`, and callers cannot choose status.
- The editable renderer writes a server-selected temporary file; fleet stores
  the invoice text. See the matrix for code and one test per principle.

## Four phases: required deliverables and gates

| Phase | Required deliverables | Gate decision |
| --- | --- | --- |
| 1. Requirements | Scope/operations, asset register, component/trust boundaries, access-control matrix and STRIDE analysis | Review that the architecture meets scope, authorities are defined and relevant threats have controls. |
| 2. Implementation and build | Three components, separate editable renderer, pinned dependency/build inputs and exact clean-install commands | Reject unexpected/unapproved artefacts and unlisted dependencies; require lint and scanner gates. |
| 3. Testing | Functional/authorization suites; investigation, fixes and reruns; later PoCs only when specified | Required functional/security tests pass; malformed artefacts are rejected. The initial security gate is authorization only. |
| 4. Release, deploy and operation | Report discussion of production release and operational needs, using real implementation/evidence | No course deployment gate; document gaps rather than claim production readiness. |

## Asset-to-gate traceability

Use the previous threat-modelling and DevSecOps exercise's chain:
asset -> threat -> requirement/control -> lifecycle activity -> test/evidence ->
gate decision.

| Asset | Threat | Requirement/control | Lifecycle activity | Test/evidence | Gate decision |
| --- | --- | --- | --- | --- | --- |
| Identity, bookings and invoices | Forged identity, cross-renter access or processor enumeration | Verified JWTs, own-record rules, one-booking scope | Requirements: review authorities; implementation/testing: enforce and exercise them | Matrix and `test_least_privilege` / `test_complete_mediation` | Defined authorities; required authorization tests pass. |
| Booking integrity | Unsafe defaults, overlap or price tampering | Deny invalid credentials; `pending`; atomic overlap check; price snapshot | Implementation/testing: validate state and investigate failures | `test_fail_safe_defaults`; functional price/concurrency tests | Reject unsafe requests; required tests pass. |
| Booking/invoice artefacts | Malformed input or rendered output is persisted | Pydantic validation, bounded UTF-8 output, server-selected path | Implementation/testing: validate before writes | Processor code; functional validation cases and saved pytest output | Reject malformed artefacts; no failed operation reports success. |
| Packages and build outputs | Unexpected dependencies or known vulnerabilities | Pinned manifest; clean install without automatic dependency additions; build/dependency checks | Implementation and build: install, lint, Bandit and pip-audit | Install logs; actual uploaded Bandit/pip-audit reports | Reject unlisted/missing requirements; lint and native scanner exits must pass. |
| Release evidence and operational data | Fabricated claims, unsafe deployment or data loss | Preserve history and real CI uploads; discuss remaining controls | Release, deploy and operation: assess readiness and write report last | Real commits/tests/Actions artifacts; eventual report | No fabricated evidence or production-readiness claim. |

## Build sequence and checkpoints

Steps 1-6 are implemented and tested. The owner deferred Step 7 until the PoC
requirements are supplied and approved doing documentation/CI from Step 8 now.
Keep incremental history and confirm major changes. Do not invent PoCs or add
them to the initial CI gate. The 2,000-2,500-word report remains last, after the
remaining implementation and real CI evidence. The owner writes the AI-use
declaration.

## Verification policy and evidence handling

- [Requirements](../requirements.txt) pin direct, transitive and build tools.
  Fresh environments use `--no-deps`, check build requirements and run `pip check`;
  missing/unlisted dependencies are not silently downloaded.
- [CI](../.github/workflows/ci.yml) runs on push/PR. Build runs Ruff, Bandit over
  `app/` and pip-audit; test runs only the two fresh-DB functional/authz suites.
- Scanner failures are not suppressed. Native pip-audit currently blocks every
  known finding, including high/critical; custom severity filtering is deferred.
- `actions/upload-artifact` saves actual scanner and pytest output, even on
  failure. A workflow definition or local output is not proof of a real CI run.
- Keep passwords, bearer tokens and signing keys out of logs and artifacts.

## Release limitations and maintenance handoff

Before production use, assess TLS, key rotation and service-specific signing
authority, password lifecycle and abuse controls, audit logging, invoice access
and retention, SQLite concurrency/backups, and dependency update ownership.
These are readiness gaps to document, not permission to add extra project
features. Re-run gates after changes and revise the threat model when roles,
routes, dependencies, or trust boundaries change.
