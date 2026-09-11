# AI execution records

`engineering-execution.md` records what AI contributed per area and what the engineer decided.
This file records the working loop itself for individual tasks: how the task was specified, what
the assistant produced, and what was accepted, edited, or rejected.

Records 1 to 3 cover the defect investigation and deployment decisions described in Scenarios 4
and 5. Each was executed in an assisted session with the engineer directing and deciding.

## Controls applied to assisted work

**Secure usage.** No credential, token, customer record, or internal system detail was placed in
a prompt. The service generates its demo API key at runtime, so no working secret exists in the
repository to leak. Generated dependency suggestions were accepted only if already present in the
pinned lock files. Assisted sessions ran against synthetic data and a local database; no assisted
process was pointed at real data.

**Sign-off.** The following are treated as high-impact and were not accepted from generated
output without deliberate line-by-line review: authentication and credential comparison, the
transaction boundaries in `app/store.py`, schema and migration files, anything affecting redirect
eligibility or click accounting, and request validation in `app/models.py`. Formatting,
documentation, test scaffolding, and dashboard presentation were treated as low-impact and
reviewed normally.

**Ownership.** Passing gates were used as evidence, never as approval. The engineer is
accountable for every line in this repository regardless of how it was drafted.

## Record 1: Diagnose intermittent creation failure

**Intent:** Establish the cause of a `404` returned by the dashboard immediately after a create
that had returned `201`, on the hosted demo.

**Constraints:** Diagnose from observable behavior before changing code. Do not alter application
logic on suspicion. Any claimed cause must be reproducible on demand.

**Acceptance criteria:** A stated mechanism, a reproduction that fails and succeeds predictably,
and identification of the specific module or configuration responsible.

**Technical context:** FastAPI service, single-writer SQLite with WAL, deployed as a serverless
function; the defect appeared only after creation and not for seeded links.

**Assisted output and engineer response:** The first hypothesis was input validation, on the
theory that a rejected URL or alias produced the error. This was tested against twelve input
classes — unicode hosts, underscores in hosts, single-label hosts, loopback, private IP literals,
embedded spaces, short and reserved aliases, past and naive expirations — and every result matched
the documented contract. **The hypothesis was rejected on evidence rather than refined.**

The second hypothesis was that the failure depended on request concurrency rather than request
content, because seeded links resolved correctly from every request while created links did not.
This was tested by issuing fifteen concurrent reads of one newly created code: five succeeded and
ten returned `404`. Ten sequential reads of the same code all succeeded.

**Result:** Cause identified in `server.py`, not in application logic: the database path resolved
to the function's temporary directory, which is private to one instance. Recorded as Scenario 4.

**Rejected:** The initial validation hypothesis, and a proposal to add retry logic to the
dashboard, which would have hidden a storage defect behind client behavior.

## Record 2: Select a correction for split hosted state

**Intent:** Choose and justify a correction, given that single-writer SQLite cannot serve
consistent state behind an autoscaled platform.

**Constraints:** Preserve the existing transaction design if possible. Prefer a correction whose
effect can be measured locally. No paid infrastructure.

**Acceptance criteria:** A correction whose validation is reproducible, and a written rationale
for the options not taken.

**Assisted output and engineer response:** Four options were generated: a single container on a
mounted volume, a hosted libSQL service, a PostgreSQL migration, and degrading the dashboard to
tolerate the inconsistency.

- **PostgreSQL — rejected as disproportionate.** It removes the constraint entirely but replaces
  `instr()` search, `PRAGMA user_version` migrations, and `BEGIN IMMEDIATE` semantics without
  changing any behavior a reviewer can observe. Retained as the documented multi-instance path.
- **Hosted libSQL — rejected.** Same SQL dialect but a different client model, requiring a
  rewrite of `app/store.py` plus an external credential, for a demo.
- **Degrade the dashboard — rejected.** It would have concealed the defect in the create flow
  while links still vanished on refresh and returned `404` to other visitors.
- **Single container on a volume — accepted**, then constrained further.

The container correction was first configured for a platform requiring a payment method. **The
engineer rejected that on cost.** Free single-instance hosts were then evaluated and also
rejected: their storage does not survive idle shutdown, which would have contradicted the stated
reason for withdrawing the original demo.

**Result:** The hosted demo was withdrawn. The correction is single-instance execution, satisfied
by the local launcher and by the provided container configuration, verified locally.

**Edited:** The first draft of Scenario 4 claimed the demo "was moved to a single container on a
mounted volume." No such environment was published, so the claim was corrected to describe the
withdrawal and the verified-but-unhosted configuration.

## Record 3: Correct a secure-context dependency

**Intent:** Restore link creation from origins that are neither HTTPS nor loopback, after
automated capture of the creation flow failed with `crypto.randomUUID is not a function`.

**Constraints:** The generated key must satisfy the server's existing `Idempotency-Key` contract:
pattern `^[A-Za-z0-9._:-]+$`, length 8 to 128. Do not weaken the server contract to accommodate
the client. Do not introduce a dependency.

**Acceptance criteria:** Creation succeeds from a plain-HTTP non-loopback origin; the dashboard
suite passes without supplying the missing API to the environment.

**Assisted output and engineer response:** A `requestKey` helper was proposed, preferring
`crypto.randomUUID`, falling back to `crypto.getRandomValues`, which carries no secure-context
restriction, and finally to `Math.random`. The engineer accepted the weaker fallback on the
explicit ground that an idempotency key requires uniqueness rather than unpredictability, and
required that reasoning to appear at the call site rather than in a commit message.

The helper was placed in `dashboard-core.mjs` rather than inline so it could be unit tested, which
also required updating the DOM harness that injects that module.

**Rejected:** Retaining `window.crypto.randomUUID = randomUUID` in the DOM test. That assignment
supplied the exact capability whose absence was the defect, so the test was asserting against a
condition that cannot occur in a browser. It was deleted, and the suite now runs against the same
missing-API condition the defect required.

**Result:** Recorded as Scenario 5. Three unit tests cover the preferred path, the fallback
encoding, and conformance to the server contract.
