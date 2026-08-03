"""Docker HEALTHCHECK for the AI_OS Kernel image.

A no-op (always healthy) for the worker role, which has no HTTP server
to probe -- deployment_architecture.md §3 documents this HEALTHCHECK
for the api role specifically. /health/live never depends on an
external service (health.py's own docstring), so this check is
meaningful even before Postgres is reachable.
"""

import os
import sys
import urllib.request

if os.environ.get("AIOS_ROLE", "api") != "api":
    sys.exit(0)

try:
    urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health/live", timeout=3)
except Exception:
    sys.exit(1)
