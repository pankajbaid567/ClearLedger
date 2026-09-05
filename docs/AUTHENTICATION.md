# Access modes and authentication

ClearLedger has two explicit access modes. Direct API startup defaults to `shared`.
Without configured bearer identities, shared data endpoints return `503 AUTH_NOT_CONFIGURED`;
an omitted or invalid bearer returns `401` once identities are configured. There is no
anonymous fallback to a demo identity. `/health`, `/ready` and `/api/auth/config` are public
operational/discovery endpoints and expose no run data.

## Local synthetic demo

`make dev-api`, the checked-in local Compose recipe, and `.env.example` explicitly select
`APP_MODE=local_demo`. The browser displays the fixed synthetic identity
`demo.finance.operator`. Demo requests require a loopback Host and, when present, a loopback
Origin. Development API and all published Compose ports bind to `127.0.0.1`.

Use this mode only for synthetic data on your own computer. Host/Origin checks are additional
browser protections, not a substitute for socket/network isolation. Never expose the demo
mode through a tunnel, LAN binding or public reverse proxy. Choose shared mode for that.
The demo identity has all three permissions so the judging loop can be exercised locally.

```sh
cp .env.example .env
make install db-up migrate generate-demo
make dev
```

For the self-contained container demo, `docker compose up --build` explicitly builds the
`demo` image target. That target generates new synthetic CSVs and an evaluation oracle from
the documented seed. It does not copy an existing private directory from the developer's
computer. AI is disabled by default; `AI_PROVIDER=mock` is an explicitly offline demonstration,
and its outputs must not be described as live model performance.

## Shared operator access

The implemented mechanism is a configured high-entropy bearer token per identity. It is
appropriate for a small hackathon/operator pilot; it does not claim SSO, MFA, managed sessions,
or enterprise identity lifecycle management. Keep the service behind HTTPS and use a dedicated
database and upload volume. Do not reuse the development database password.

Generate a token locally without writing the credential into a shell command or log:

```sh
uv run python -m scripts.create_auth_token --subject alice --role admin
```

This creates `~/.config/clearledger/alice/access.bearer-token` and `auth-tokens.json`, both with
mode `0600`. The bearer file contains the secret to enter in the browser's access screen;
the identity JSON contains only its SHA-256 digest, subject and role. Keep both outside the
repository. The helper refuses to overwrite an existing identity directory's output files.

Set `APP_MODE=shared` and set `AUTH_TOKENS` to the contents of the identity JSON through your
deployment environment. To start a local authenticated API for testing:

```sh
export APP_MODE=shared
export AUTH_TOKENS="$(cat "$HOME/.config/clearledger/alice/auth-tokens.json")"
make dev-api
```

For multiple people, concatenate their identity objects into one JSON array. Each person's
`subject` must identify the actual operator. Never put the raw bearer in `AUTH_TOKENS`, a URL,
committed config, a shared screenshot, or a CI artifact. The browser keeps the bearer in memory
and sends it in the `Authorization: Bearer …` header; a refresh/sign-out clears browser access.
There are no authentication cookies, so cookie-based CSRF tokens are not part of this API.

The API derives every user-initiated audit actor and every review actor from the authenticated
subject; autonomous processing stages are attributed to `SYSTEM` or `AI_SUGGESTION`.
Client-supplied `actor` fields cannot impersonate another operator. Invalid and missing credentials return
the same public error. Digests are compared with a constant-time comparison. AI credentials
use a redacted secret type in configuration.

| Role | Read own runs | Create/upload/reconcile/analyze | Review actions |
|---|---:|---:|---:|
| viewer | Yes | No | No |
| operator | Yes | Yes | No |
| reviewer | Yes | No | Yes |
| admin | Yes | Yes | Yes |

Grounded run questions are read-only and are available with the read permission. A case
analysis that creates a stored suggestion requires the create permission.

Every run has an `owner_subject`; run, case, evidence, audit and export access is scoped to that
subject. Admin grants actions, **not access to another person's runs**. Unknown and foreign runs
both return `404`; ownerless historical runs are denied in shared mode. Idempotency records
are scoped to the same subject. Canonical case URLs include the run ID, because a synthetic
case identifier may occur in many runs. This is per-person isolation, not a multi-tenant
organization sharing or maker/checker approval system. An admin can create and review their
own run. Add explicit tenant membership and independent approver rules before claiming those
capabilities.

To revoke or rotate access, remove/replace the digest in deployment configuration and restart
the API. Tokens do not have automatic expiry in this version; rotation and revocation are
operator-managed. `/api/auth/me` returns the authenticated subject, role, demo flag and
permissions so the browser can reflect server authority.

## Container boundary for shared hosting

The default Docker build target, `runtime`, contains application code and versioned prompts.
It contains neither `/app/evaluator_private` nor `/app/data/demo`. Synthetic demo creation is
disabled for shared identities. Evaluation is a separate explicit workflow with a generated
oracle, not a hidden production dependency.

`docker-compose.shared.yml` overlays the local recipe with `runtime`, `APP_MODE=shared`, and
required deployment settings. Supply `AUTH_TOKENS`, `POSTGRES_PASSWORD`, `DATABASE_DIRECT_URL`,
the restricted runtime `DATABASE_URL`, `WEB_ORIGIN` and `NEXT_PUBLIC_API_BASE_URL`; the web/API URLs should be HTTPS origins exposed
by your reverse proxy. The database URL must address the dedicated database with the matching
new password (URL-encode special password characters). Use a new volume/environment instead
of pointing this at an existing demo database: changing `POSTGRES_PASSWORD` does not rotate
credentials in an initialized PostgreSQL volume.

```sh
docker compose -f docker-compose.yml -f docker-compose.shared.yml up --build
```

The override keeps service ports on loopback for a local reverse proxy. Configure that proxy
to terminate TLS and forward only to these private ports. External AI calls remain disabled
in this recipe; enabling a live compatible provider is a separate explicit configuration.

The shared image starts the API without running Alembic. The Compose override runs migrations
as a separate one-shot service using the schema-owner `DATABASE_DIRECT_URL`. Apply
[`deploy/postgres/runtime_role.sql`](../deploy/postgres/runtime_role.sql) as the schema owner,
create a separate login, grant it membership in `clearledger_runtime`, and grant that login
`CONNECT` on the deployment database. The API login must not own the database, schema, tables,
or migration functions. This keeps DDL authority out of the public API process while permitting
the listed inserts, projection updates, and idempotency-claim cleanup.

When upgrading a database created before run-scoped follow-up tasks, migration
`d9c7e21a4f10` stops if any old task cannot be assigned safely. Inspect candidates:

```sql
SELECT task.id AS task_id, task.case_id,
       array_agg(case_row.reconciliation_run_id ORDER BY case_row.created_at) AS candidate_runs
FROM follow_up_tasks AS task
LEFT JOIN reconciliation_cases AS case_row ON case_row.case_id = task.case_id
WHERE task.reconciliation_run_id IS NULL
GROUP BY task.id, task.case_id;
```

For each row, check the source decision and audit timestamp, then record the chosen run:

```sql
UPDATE follow_up_tasks
SET reconciliation_run_id = '<reviewed-run-uuid>'
WHERE id = '<task-uuid>' AND reconciliation_run_id IS NULL;
```

Record the mapping in the deployment change log and rerun Alembic. The migration does not guess
among repeated case IDs and makes the run reference non-null after remediation.

## Verification

`tests/unit/test_auth.py` exercises default denial, header-only credentials, the role matrix on
both case URL forms, server identity, demo host/origin restrictions, redaction, and foreign or
ownerless run rejection even for admins. Database-backed API tests additionally exercise the
actual scoped routes and persisted review actor. CI runs these with a fresh PostgreSQL service,
checks migrations against model metadata, and verifies the runtime/demo image separation.

CI uses frozen Python/frontend installs, complete Ruff checks, a strict type gate for domain
money/enums, authentication, evaluator and policy modules, full Python tests, explicit
adversarial financial gates, browser smoke, dependency advisories and secret scans. The wider
service layer is not yet a clean whole-project strict-mypy target; `make typecheck-core` names
the gated scope. CI evidence is synthetic and is retained for 14 days.
