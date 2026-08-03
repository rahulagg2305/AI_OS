#!/bin/sh
# One image, two entry points (ADR-0020, deployment_architecture.md §2).
# AIOS_ROLE selects which process this container runs; unset defaults to
# "api", the identical default ai_os_kernel.configuration_manager
# .bootstrap_env.BootstrapEnv.role already establishes, so this script
# can never silently disagree with what the app itself would assume.
set -e

role="${AIOS_ROLE:-api}"

case "$role" in
  api)
    exec uvicorn ai_os_kernel.entrypoints.api:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python -m ai_os_kernel.entrypoints.worker
    ;;
  *)
    echo "entrypoint.sh: unknown AIOS_ROLE '$role' (expected 'api' or 'worker')" >&2
    exit 1
    ;;
esac
