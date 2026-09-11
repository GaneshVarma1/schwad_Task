# Submission map

This prototype is a URL shortener. The assignment is an engineering-execution exercise, so
this page maps each requirement to the artifact that satisfies it. Every claim below is
traceable to a file in this repository.

## Start here

| If you have | Read or run |
|---|---|
| Two minutes | The dashboard screenshots in [README.md](README.md), then [docs/engineering-execution.md](docs/engineering-execution.md) |
| Ten minutes | Add [docs/architecture.md](docs/architecture.md) and `app/main.py`, `app/store.py`, `app/models.py` |
| A terminal | `python scripts/run_dashboard.py` after the setup steps in [README.md](README.md); no container runtime required |

## Core requirements

| # | Requirement | Where it is satisfied |
|---|---|---|
| 1 | Requirement understanding | `engineering-execution.md` → Requirement normalization. Six provisional product semantics fixed; workload, availability, retention, tenancy, destination policy, and recovery objectives named as unresolved production decisions rather than invented |
| 2 | Task decomposition | `engineering-execution.md` → Execution plan. Seven stages with explicit dependencies, sequenced contracts → persistence → behavior → reliability → interface → validation → review |
| 3 | Codebase reasoning (brownfield) | Scenario 2 traces idempotency across headers, store transaction, schema migration, OpenAPI, and concurrency tests. Scenario 4 separates a deployment defect from application logic under a live failure |
| 4 | AI-assisted execution | [docs/ai-execution.md](docs/ai-execution.md) → per-task records with intent, constraints, acceptance criteria, and what was accepted, edited, or rejected; plus the secure-usage and sign-off controls applied. Summarized per area in `engineering-execution.md` → AI-assistance record |
| 5 | Engineering output | `app/` service and dashboard, `app/schema.sql` and `app/migration_002.sql`, `docs/openapi.json` generated and drift-checked, 82 Python and 12 JavaScript/DOM tests |
| 6 | Validation and risk control | `engineering-execution.md` → Quality gates and Risk and release ownership. Scenario 4 carries measured before/after evidence |
| 7 | Controlled oversight | Rejected-proposal list and the release-ownership statement. Automated gates are treated as supporting evidence, not approval |
| 8 | Final engineering summary | `engineering-execution.md` → Final engineering summary: plan, artifacts, risks, assumptions, limitations |

## Deliverables

| Deliverable | Location |
|---|---|
| Working prototype, runnable end to end | `python scripts/run_dashboard.py` after four setup commands, or the container image. Nothing is hosted; the primary path needs no container runtime |
| Architecture overview | [docs/architecture.md](docs/architecture.md) and the Architecture section of [README.md](README.md) |
| Greenfield scenario | `engineering-execution.md` → Scenario 1: service, contracts, and transactional resolve |
| Brownfield scenarios | Scenario 2: idempotent creation under lost responses. Scenarios 4 and 5: two defects found by validation against a running instance, measured, and closed |
| Ambiguous scenario | Scenario 3: click definition, analytics durability, and retention resolved with stated reasoning |
| Setup instructions | [README.md](README.md) → Run the dashboard, Run the persistent service, Deploy the hosted demo |
| Testing approach, limitations, trade-offs | README → Verification and Production boundaries; `engineering-execution.md` → Quality gates and Final engineering summary |

## What this submission does not claim

The prototype is not production-approved. It has no identity model, ownership authorization,
centralized rate limiting, destination screening, retention policy, defined SLOs, or exercised
restore objectives. The hosted demo bypasses operator authentication by design, contains
synthetic data, and must not be connected to real data. Coverage figures and passing gates are
evidence, not release approval.

Scenario 4 is included deliberately. A risk recorded before implementation later materialized in
the hosted environment; it is documented with the measurements that exposed it and the
correction that closed it, rather than removed from the record.
