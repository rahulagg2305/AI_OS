"""Process-role entrypoints.

Each module here is a thin launcher for one process role (ADR-0020: the
Kernel runs as `api` and `worker` roles from a single image). All actual
construction happens in :mod:`ai_os_kernel.bootstrap`; nothing is wired
here.
"""
