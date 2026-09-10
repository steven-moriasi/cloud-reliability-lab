#!/usr/bin/env sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_path="${repository_root}/.artifacts/reliability.dump"
restore_database="reliability_restore_check"

test -s "${backup_path}"
docker compose -f "${repository_root}/compose.yaml" exec -T db \
  dropdb --username=reliability --if-exists "${restore_database}"
docker compose -f "${repository_root}/compose.yaml" exec -T db \
  createdb --username=reliability "${restore_database}"
docker compose -f "${repository_root}/compose.yaml" exec -T db \
  pg_restore --username=reliability --dbname="${restore_database}" \
  --exit-on-error <"${backup_path}"

source_count=$(docker compose -f "${repository_root}/compose.yaml" exec -T db \
  psql --username=reliability --dbname=reliability --tuples-only --no-align \
  --command='SELECT COUNT(*) FROM orders')
restored_count=$(docker compose -f "${repository_root}/compose.yaml" exec -T db \
  psql --username=reliability --dbname="${restore_database}" --tuples-only --no-align \
  --command='SELECT COUNT(*) FROM orders')

if [ "${source_count}" != "${restored_count}" ]; then
  printf 'Restore verification failed: source=%s restored=%s\n' \
    "${source_count}" "${restored_count}" >&2
  exit 1
fi

docker compose -f "${repository_root}/compose.yaml" exec -T db \
  dropdb --username=reliability "${restore_database}"
printf 'Restore verified with %s orders\n' "${source_count}"
