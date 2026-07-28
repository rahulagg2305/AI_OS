"""Resolves an ``entrypoint`` string of the documented form
``module.path:ClassName`` (``platform_sdk/schemas/manifest.schema.json``'s
own ``agents[].entrypoint``/``tools[].entrypoint`` pattern,
``^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$``, "Python import
path") to a real, constructed Python object.

This is the smallest possible "load a class from a string and
instantiate it" mechanism — not a plugin framework. Deliberately
excluded, all explicitly out of scope for this step:

- No pack install/activate lifecycle, no dependency resolution, no
  version pinning — this loads exactly the one string it is given,
  once, synchronously.
- No permissions system — the loaded code runs with the same privileges
  as the process that imports it. A real permissions/sandboxing story
  is Security Manager and ADR-0016 territory (Stage C), not this.
- No network or code download — ``importlib.import_module`` only ever
  resolves modules already importable on this process's own
  ``sys.path`` (installed packages, the repository itself). Nothing
  here fetches code from anywhere.
- No constructor arguments — the loaded class is instantiated with no
  arguments (``cls()``), the same "zero-configuration" shape every
  trivial ``Agent``/``Tool`` implementation in this codebase already
  has (:class:`~ai_os_kernel.workflow_engine.agent.EchoAgent`,
  :class:`~ai_os_kernel.workflow_engine.tool.EchoTool`). Passing
  manifest-declared configuration into an entrypoint's constructor is
  real Capability Manager design work, not attempted here.

Every failure mode — a malformed string, an unimportable module, a
missing attribute, a name that isn't a class, or a constructor that
raises — becomes one clear :class:`~ai_os_kernel.workflow_engine.errors.
EntrypointLoadError`, never a bare ``ImportError``/``AttributeError``/
stack trace.

Deliberately **not** a ``Protocol``: there is exactly one way to load a
Python entrypoint string (``importlib``), and no second implementation
is real or imminent (ADR-0004) — a fake test double for "how you import
a module" is not a capability this codebase has any reason to swap.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

from ai_os_kernel.workflow_engine.errors import EntrypointLoadError

# Mirrors platform_sdk/schemas/manifest.schema.json's own
# agents[].entrypoint / tools[].entrypoint pattern exactly — the
# authoritative shape, not invented here.
_ENTRYPOINT_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$")


class EntrypointLoader:
    """Loads and constructs one object from an ``entrypoint`` string.

    Synchronous by design: ``importlib.import_module`` performs
    blocking file I/O on first import. Callers on the asyncio event
    loop (:mod:`ai_os_kernel.workflow_engine.registry`) are responsible
    for running :meth:`load` off-thread (``asyncio.to_thread``) —
    keeping this class itself synchronous makes it trivial to unit test
    without any async ceremony.
    """

    def load(self, entrypoint: str) -> Any:
        if not _ENTRYPOINT_PATTERN.match(entrypoint):
            raise EntrypointLoadError(
                f"entrypoint {entrypoint!r} is not of the documented form "
                "'module.path:ClassName' (platform_sdk/schemas/manifest.schema.json)"
            )

        module_path, _, class_name = entrypoint.partition(":")

        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise EntrypointLoadError(
                f"entrypoint {entrypoint!r}: could not import module {module_path!r}: {exc}"
            ) from exc

        try:
            cls = getattr(module, class_name)
        except AttributeError as exc:
            raise EntrypointLoadError(
                f"entrypoint {entrypoint!r}: module {module_path!r} has no attribute {class_name!r}"
            ) from exc

        if not isinstance(cls, type):
            raise EntrypointLoadError(
                f"entrypoint {entrypoint!r}: {class_name!r} in {module_path!r} is not a class"
            )

        try:
            return cls()
        except Exception as exc:
            raise EntrypointLoadError(
                f"entrypoint {entrypoint!r}: failed to construct {class_name!r}: {exc}"
            ) from exc
