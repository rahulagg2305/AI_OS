#!/bin/sh
# The matching restore half of backup.sh (P07-S01-M40-T03).
# `--clean --if-exists` drops any existing objects first, so this is
# safe to run against a target that already has an older schema, not
# only a genuinely empty one; `--no-owner --no-privileges` avoids a
# real, common restore failure when the target's own role name differs
# from whichever role produced the backup.
set -e

if [ -z "$AIOS_DATABASE_URL" ]; then
  echo "restore.sh: AIOS_DATABASE_URL must be set" >&2
  exit 1
fi
if [ -z "$1" ]; then
  echo "restore.sh: usage: restore.sh <input-file>" >&2
  exit 1
fi

pg_restore --dbname="$AIOS_DATABASE_URL" --clean --if-exists --no-owner --no-privileges "$1"
