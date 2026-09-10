#!/usr/bin/env sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
artifact_directory="${repository_root}/.artifacts"
backup_path="${artifact_directory}/reliability.dump"

mkdir -p "${artifact_directory}"
docker compose -f "${repository_root}/compose.yaml" exec -T db \
  pg_dump --username=reliability --dbname=reliability --format=custom >"${backup_path}"

test -s "${backup_path}"
sha256sum "${backup_path}" >"${backup_path}.sha256"
printf 'Backup written to %s\n' "${backup_path}"
