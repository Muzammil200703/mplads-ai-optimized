#!/usr/bin/env sh
# Production entry point. The SQLite dataset is stored via Git LFS because it
# is too large for ordinary Git. Refuse to serve a schema-only LFS pointer as
# an empty, apparently valid audit database.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DB_PATH="${DATABASE_PATH:-$SCRIPT_DIR/mplads.db}"
MIN_DATASET_BYTES=1048576

if [ ! -f "$DB_PATH" ] || [ "$(wc -c < "$DB_PATH")" -lt "$MIN_DATASET_BYTES" ]; then
  echo "MPLADS dataset is missing or incomplete: $DB_PATH" >&2
  echo "Fetch Git LFS before starting the API (git lfs pull). Refusing to serve an empty audit dataset." >&2
  exit 1
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
