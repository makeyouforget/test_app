set -eu

/app/scripts/wait-for-db.py

exec "$@"