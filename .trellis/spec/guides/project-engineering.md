# Project Engineering Baseline

Status: source-backed engineering rules, extracted 2026-10-21. Scope: local development, dependency/configuration boundaries, database safety and validation evidence.

## Architecture and authority

One repository contains a React/TypeScript/Vite frontend and FastAPI/SQLAlchemy/SQLite backend. Browser playback uses YouTube IFrame; Python owns persistent business data and import processing. Current import execution is a lifespan-owned serial consumer, not a persistent external worker service. See [frontend](../frontend/index.md) and [backend](../backend/index.md) for source-backed boundaries.

These specs own current engineering conventions. Product behavior and terms are maintained in [product specs](../product/index.md); API/data formats and player technical contracts live in [technical specs](../contracts/index.md). Root README is the installation/startup entry. [Scope and evidence](../product/scope-and-acceptance.md) records future boundaries and unresolved limitations without requiring historical documents. Project thinking guides provide source-backed review questions; they do not replace the owning product/technical contracts.

## WSL and dependencies

Run project operations in this WSL checkout. Load WSL nvm before npm (`source "$HOME/.nvm/nvm.sh"` and `nvm use`); node/npm paths must resolve under the Linux home nvm installation, not /mnt/... Windows installations. `.nvmrc` and `frontend/package.json` define the Node/npm requirements; `backend/pyproject.toml` defines Python. Keep `backend/uv.lock` and `frontend/package-lock.json` as resolved dependency authorities. Install with `uv sync --locked` in backend/ and `npm ci` in frontend/; do not update lockfiles as a side effect of documenting conventions.

## Configuration and startup

`backend/app/core/config.py` defines Settings and `backend/tests/test_config.py` checks resolution. Root `.env.example` is the copyable example. Settings load repository-root .env independent of cwd; priority is constructor values, environment, .env, defaults. Unknown fields are ignored. Relative data/database/model paths resolve against the repository root; an explicit DATABASE_URL is independent of DATA_DIR. Only file-based SQLite URLs are accepted, not :memory:, another driver or query/fragment. Retired cloud variables do not enable cloud processing.

App startup creates DATA_DIR, but table creation/upgrades require explicit Alembic execution (`backend/migrations/env.py`, `backend/tests/test_health.py`). STT uses a predownloaded local model; setup/readonly preflight commands remain in README. Startup/health success is not a model or network acceptance test.

`frontend/vite.config.ts` sets development host/port to 127.0.0.1:5173 with strictPort and preview to 4173. `frontend/src/api/client.ts` owns the localhost:8000/api client and default timeout; collection preview overrides timeout in api/collections.ts. Backend CORS comes from Settings. A manually chosen local port must be allowed by CORS; a historical local 3000 deployment does not replace the standard dev configuration. The frontend does not automatically consume the root backend .env.

## Database and runtime safety

Runtime data is under data/; source-owned stores (`backend/app/services/processing/caption_store.py`, audio_store.py) manage internal video-ID paths. `.gitignore` excludes data, .env secrets, databases, logs, caches and work/. Preserve unknown media/store files according to the store contract instead of using broad directory deletion.

For migration verification, use a fresh temporary directory and explicitly bind DATABASE_URL (and DATA_DIR for app startup) for the entire command. Example from repository root:

```bash
migration_check_dir=$(mktemp -d)
(
  export DATABASE_URL="sqlite:///$migration_check_dir/app.db"
  export DATA_DIR="$migration_check_dir/data"
  cd backend
  uv run --locked alembic upgrade head
  uv run --locked alembic current
  uv run --locked alembic check
)
```

This demonstrates isolated fresh-schema validation, not populated migration preservation; use representative fixture/copy tests for that. Never substitute the daily database merely to make a check pass. Daily writes/upgrades require their own authorized scope, consistent backup and preservation checks. Documentation work does not authorize daily data changes.

## Validation evidence

Distinguish documentation consistency, pure/sample tests, isolated FastAPI/SQLite integration, daily service reads and real YouTube/AI/STT/browser acceptance. State what ran and its limits. A stubbed player cannot verify Chrome native controls or real fullscreen. Historical evidence remains valid only for its recorded version/scope; untested external links remain explicitly unverified.

Frontend verification is npm test / npm run build; backend verification is uv run --locked pytest -q, with relevant persistence checks. See layer quality specs for seams. No lint scripts or automatic format hooks are currently configured in the app manifests. Avoid adding tests that simply restate a reversible Markdown edit; use documentation checks for documentation-only changes.
