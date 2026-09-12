#!/usr/bin/env sh
set -eu

mkdir -p "$(dirname "${LUNELLE_DB_PATH:-/data/period_tracker.db}")"

python - <<'PY'
import app
for name in ("init_db", "migrate_db"):
    fn = getattr(app, name, None)
    if callable(fn):
        fn()
PY

exec gunicorn \
  --workers "${WEB_CONCURRENCY:-2}" \
  --bind "0.0.0.0:${PORT:-5055}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  app:app
