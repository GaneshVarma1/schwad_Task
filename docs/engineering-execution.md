# Engineering execution and AI traceability

## Requirement normalization

The requirement was normalized into a single-operator URL management service with public redirects and protected management APIs. The implementation defines the following provisional product semantics:

- Only syntactically valid HTTP and HTTPS destinations are accepted.
- A click means an eligible `GET` request whose analytics transaction commits.
- Repeat requests and bots are counted; `HEAD` requests are not.
- Expired and disabled links return `410` and do not increment analytics.
- Links cannot be edited, deleted, or reused under the same alias.
- Analytics store lifetime totals and UTC daily aggregates without visitor identifiers.

Unspecified workload, availability target, retention policy, tenant model, destination policy, and recovery objectives remain production decisions.

## Execution plan

| Stage | Outcome | Dependency |
|---|---|---|
| Contracts | API behavior, validation, errors, and trust boundary | Normalized requirements |
| Persistence | Versioned schema and transactional repository | Contracts |
| Core service | Create, resolve, inspect, disable, and analytics | Persistence |
| Reliability | Idempotency, limits, rollback behavior, readiness, backup | Core service |
| Dashboard | Same-origin management interface and synthetic sandbox | Management APIs |
| Validation | Tests, linting, security scan, dependency audit, HTTP verification | All implementation stages |
| Hosted correction | Withdrawal of the split-state demo; single-instance deployment defined | Validation evidence |
| Review | Risks, limitations, and production gates | Validation evidence |

## Scenario 1: Greenfield service

**Intent:** A trusted operator creates a durable short link, a public caller follows it, and the operator can inspect its activity.

**Implementation:** FastAPI owns the HTTP boundary, Pydantic owns typed contracts, and a dedicated store owns SQL and transactions. Codes contain 48 random bits and remain protected by a database uniqueness constraint. The resolve transaction checks eligibility, increments the lifetime total, upserts the UTC daily bucket, and commits before returning `302`.

**Validation:** Tests cover malformed and unsafe URL forms, authentication, alias collisions, exact expiration, status codes, `HEAD` behavior, concurrent creation, concurrent counting, rollback, lock contention, and sanitized logs.

## Scenario 2: Brownfield retry safety

**Problem:** A successful create response can be lost. Retrying without request identity can create a duplicate random link or return a conflict for an already-created custom alias.

**Impact analysis:** The change affected request headers, creation responses, the store transaction, schema migration, request fingerprinting, OpenAPI, and concurrency tests. Redirect behavior and analytics tables remained compatible.

**Implementation:** An optional bounded `Idempotency-Key` is SHA-256 hashed before storage. A canonical request fingerprint binds the key to the validated URL, alias, and UTC-second expiration. The mapping and link are created atomically. An identical replay returns the original link; a changed request returns `409`.

**Validation:** Tests cover parallel retries, changed payloads, restart persistence, failed attempts, migration from schema v1, repeated startup, and replay after a link becomes expired or disabled.

## Scenario 3: Ambiguous analytics and reliability

**Ambiguity considered:** Whether clicks mean unique visitors, requests, human interactions, or completed destination loads; whether redirect availability should take priority over analytics durability; and what visitor data should be retained.

**Decision:** Count committed eligible redirect decisions and store only aggregate counters. The service performs no destination fetch and collects no IP, referrer, user-agent, or visitor identifier. Synchronous counting provides clear consistency but makes storage availability part of redirect availability.

**Validation:** UTC rollover, exact expiry, excluded requests, concurrent increments, transaction rollback, busy-timeout behavior, log redaction, and real HTTP traffic are covered. The local burst measurement is diagnostic evidence rather than a capacity or SLO claim.

## Scenario 4: Brownfield defect in hosted state

**Problem:** Creating a link on the hosted demo returned `201`, after which the dashboard's own follow-up read of that link returned `404` and the created link was absent from the list. Seeded links behaved correctly, so the failure presented as a defect in creation.

**Evidence:** Ten sequential reads of a newly created code succeeded. Fifteen concurrent reads of the same code, issued seconds later, returned five successes and ten `404` responses. Seeded aliases resolved from every instance. The failure therefore depended on request concurrency and instance count rather than on request content.

**Impact analysis:** The defect was located in deployment configuration, not in application logic. `server.py` placed the database under the function's temporary directory, which is private to one serverless instance, so each instance initialized and seeded a separate database. Validation, transactions, idempotency, and analytics were unaffected. The local launcher never exposed the defect because it runs one process against one database, and neither test suite could observe it because both execute in a single process.

**Decision:** The hosted deployment was withdrawn rather than repaired in place. The defect is a property of running single-writer SQLite behind an autoscaled platform, so the correction is to serve the demo from one process against one database. The local launcher already satisfies that, and a single-instance container configuration is provided for any host that can mount a disk. Publishing a demo whose state splits under concurrency was judged worse than publishing none. Migrating the store to PostgreSQL would remove the constraint entirely but was rejected for this prototype because it would replace `instr()` search, `PRAGMA user_version` migrations, and `BEGIN IMMEDIATE` semantics without changing any reviewable behavior; it remains the documented path for multi-instance operation.

**Implementation:** `server.py` reads `SHORTENER_DATABASE` and `SHORTENER_BASE_URL` and retains its previous defaults. The container entry point prepares the mounted volume and drops to the unprivileged service account before serving traffic. The image default remains the authenticated service; the seeded demo runs by overriding that command. Any host for it must bind one instance to one volume.

**Validation:** Against the built container image running locally, fifteen concurrent reads and fifteen concurrent redirects of a newly created code returned `200` and `302` with no failures. The link survived a container restart. The dashboard creation sequence completed with no `404` and no console error, and short links now carry the origin being browsed. The Python suite, lint, format, and security scan were rerun unchanged.

**Ownership:** This risk was recorded before the defect appeared and was accepted for a labeled sandbox. Accepting a known-unsafe hosted mode without first establishing where it would fail was the engineering error. The original record is retained rather than rewritten.

## Scenario 5: Brownfield secure-context defect

**Problem:** Automated capture of the creation flow, driven against the container over plain HTTP from a non-loopback host, failed at submission with `crypto.randomUUID is not a function`. Link creation was impossible from that origin.

**Impact analysis:** `crypto.randomUUID` is restricted to secure contexts. The dashboard called it to mint an `Idempotency-Key`, so creation worked over HTTPS and over loopback and failed everywhere else, including a reviewer opening the local service on a LAN address. Every earlier check missed it: the browser checks used loopback, and the DOM test assigned `window.crypto.randomUUID` itself, so the suite supplied the very capability whose absence was the defect.

**Decision:** A `requestKey` helper was added to the shared core module and covered by unit tests. It prefers `crypto.randomUUID`, falls back to `crypto.getRandomValues`, which carries no secure-context restriction, and falls back again to `Math.random`. An idempotency key requires uniqueness rather than unpredictability, so the weaker source is acceptable and is documented at the call site.

**Validation:** Three unit tests cover the preferred path, the fallback encoding, and conformance to the server's `Idempotency-Key` pattern and length bounds. The polyfill was deleted from the DOM test, which now exercises the same missing-API condition the defect required and passes without it. The recapture of the creation flow succeeded from the same non-loopback origin.

## AI-assistance record

Per-task records of the working loop, including the controls applied to assisted work, are in
[ai-execution.md](ai-execution.md). This section summarizes the contribution by area.

| Area | AI contribution | Engineer control and result |
|---|---|---|
| Requirements | Identified ambiguity and proposed explicit semantics | Retained bounded single-operator scope and documented unresolved product decisions |
| Architecture | Proposed FastAPI, SQLite WAL, and layered modules | Retained for a runnable prototype; documented PostgreSQL as the multi-instance path |
| Implementation | Generated handlers, models, SQL, dashboard code, and scripts | Edited for transaction boundaries, log privacy, request bounds, and deployment behavior |
| Debugging | Interpreted failing redirect, ASGI body-frame, origin, and responsive-layout checks | Corrected behavior and reran the relevant quality gates. The defects in Scenarios 4 and 5 were found by validation against a deployed instance, not by the suite |
| Tests | Generated API, store, concurrency, migration, UI, and recovery cases | Retained behavior-focused tests; rejected tests that only mirrored implementation |
| Security | Proposed validation, bearer auth, CSP, redaction, and scanning | Retained as prototype controls without claiming malware, SSRF, or production security coverage |
| Deployment | Proposed direct FastAPI deployment on Vercel | Accepted as a labeled sandbox, then withdrawn after the split-state defect in Scenario 4. No hosted environment is published; a verified single-instance container configuration is provided instead |

Rejected or constrained proposals included permanent cached redirects, visitor-level analytics, destination fetching, silent demo authentication in normal startup, multi-worker SQLite operation, and temporary serverless state presented as durable storage.

## Quality gates

- 82 Python tests and 12 JavaScript/DOM tests pass. Six are property-based checks over generated input, asserting that validation always terminates with a typed outcome, preserves accepted values, and never admits a non-global host.
- Combined Python statement/branch coverage is 98.99%.
- Ruff lint and format checks pass.
- Bandit reports no application findings.
- Runtime dependency audit reports no known vulnerabilities in the tested lock snapshot.
- OpenAPI drift verification passes.
- Real HTTP verification covers create, idempotent replay, redirect, analytics persistence, disable, readiness, and a bounded concurrency burst: 250 requests at concurrency 8, zero failures, 935 requests per second, p50 2.9 ms and p95 41.0 ms over loopback. This is a local smoke measurement on one machine, not a capacity or SLO claim.
- Hosted Chromium checks cover desktop and mobile document widths, hidden table scrollbars, and internal table scrolling.
- Concurrent read and redirect verification against the built container image confirms that one database serves every request.
- The dashboard suite runs without patching browser APIs into the environment, so a capability the application requires cannot be supplied by the test.

## Risk and release ownership

| Risk | Prototype control | Production requirement |
|---|---|---|
| Phishing or redirect abuse | Protected creation, validation, disable | Destination policy, screening, reporting, and takedown |
| Unauthorized management | Constant-time bearer comparison | Identity, ownership predicates, roles, and rotation workflow |
| Data loss or inconsistent hosted demo state | Hosted demo withdrawn; single-instance execution required and verified in Scenario 4 | Durable PostgreSQL, migrations, backups, and restore objectives |
| Write contention | WAL, short transactions, bounded busy timeout | Workload-driven database and scaling design |
| Counter availability trade-off | Atomic synchronous counting | Approved availability and analytics-loss contract |
| AI-generated defects | Automated gates and explicit limitations | Independent engineer review and release sign-off |

The candidate owns the final assessment of correctness, maintainability, security, and readiness. Passing automated checks is supporting evidence, not release approval.

## Final engineering summary

**Plan and rationale.** The requirement was normalized into a single-operator service with public redirects and protected management APIs, then executed in the staged order above: contracts before persistence, persistence before behavior, reliability before interface, and validation before review. SQLite with WAL was selected so the prototype runs end to end without infrastructure setup, with PostgreSQL documented as the multi-instance path rather than implemented speculatively.

**Artifacts.** Service and dashboard sources under `app/`; versioned schema and migration; 82 Python tests and 12 JavaScript/DOM tests; the generated contract at `docs/openapi.json`; the architecture and decision record at `docs/architecture.md`; this execution and traceability record; the per-task AI execution records at `docs/ai-execution.md`; container and single-instance deployment configuration; dashboard screenshots under `docs/screenshots/`; and scripts for the demo launcher, backup, OpenAPI export, and HTTP verification.

**Risks, trade-offs, and validation.** Recorded in the risk table above and in `docs/architecture.md`. The two principal accepted trade-offs are synchronous click accounting, which makes storage availability part of redirect availability, and single-writer SQLite, which bounds the prototype to one instance. Both were validated by test and by measurement rather than asserted. Scenario 4 records a risk that was accepted, materialized in the hosted environment, and then closed.

**Assumptions.** One trusted operator; no tenant model or per-link ownership; destinations validated but never fetched or screened; UTC throughout; a single serving instance; synthetic demo data.

**Limitations.** This prototype is not production-approved. It has no identity model, ownership authorization, centralized rate limiting, destination screening, retention policy, defined SLOs, or exercised restore objectives. The hosted demo bypasses operator authentication by design and must not be connected to real data. Coverage figures and passing gates are supporting evidence, not release approval.

