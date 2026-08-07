#!/bin/sh
# Real Postgres backup (P07-S01-M40-T03) — deployment_architecture.md's
# own disclosed gap: "no backup/restore tooling and no rehearsed
# restore drill." `pg_dump`'s custom format (`-Fc`) is a real,
# self-contained, `pg_restore`-compatible artifact — schema and data
# both, so a restore into a genuinely empty database rebuilds
# everything, not merely one table.
#
# AIOS_DATABASE_URL is the same real env var every other real caller
# in this codebase reads (ai_os_kernel.persistence.settings) — never a
# hardcoded host/user/password here. See restore.sh for the matching
# half of this pair.
set -e

if [ -z "$AIOS_DATABASE_URL" ]; then
  echo "backup.sh: AIOS_DATABASE_URL must be set" >&2
  exit 1
fi
if [ -z "$1" ]; then
  echo "backup.sh: usage: backup.sh <output-file>" >&2
  exit 1
fi

pg_dump --dbname="$AIOS_DATABASE_URL" --format=custom --file="$1"
