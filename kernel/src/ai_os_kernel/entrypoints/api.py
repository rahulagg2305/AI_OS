"""API process-role entrypoint.

Started as::

    uvicorn ai_os_kernel.entrypoints.api:app

See docs/11_deployment/deployment_architecture.md §2.
"""

from ai_os_kernel.bootstrap import build_app

app = build_app()
