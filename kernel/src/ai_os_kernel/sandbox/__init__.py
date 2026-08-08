"""Sandbox — Tier 1 untrusted execution (ADR-0016).

Runs generated/untrusted commands (compiling, testing, dependency
installation, anything touching ingested-repository content) behind a
pluggable :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor`
Protocol, so the isolation *mechanism* can be swapped without changing
any caller.

See docs/18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md,
docs/09_security/security_architecture.md §5.1.

**Naming note, now cross-referenced rather than left as an unreconciled
discrepancy (2026-07-28)**: ADR-0016 and security_architecture.md §5.1
both name this seam ``SandboxRuntime``; this package uses
``SandboxExecutor`` instead, per this pack's own original approved
framing. Both documents now carry an explicit note recording that
mapping (ADR-0016's own "Implementation naming note," added the same
day this docstring was updated) — the two names are not silently
reconciled into one (that would mean editing an Accepted ADR's own
decision text, which this codebase's ADR process does not permit
in place), but a reader of either document is no longer left to
discover the mismatch on their own.

**Two backends now exist.**
:class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox` is a
real, working backend, but **not** a full ADR-0016 Tier 1
implementation (no network or filesystem containment; see its own
docstring) — real for development/fast tests, never for genuinely
untrusted content. :class:`~ai_os_kernel.sandbox.docker_executor.
DockerSandbox` is the real Tier 1 implementation: an ephemeral OCI
container per call, network disabled, a read-only root with exactly one
writable bind mount, dropped capabilities, a non-root user, and real
resource limits — see that class's own docstring for the full
guarantee-by-guarantee reasoning, and each backend's ``guarantees``
property for a checkable, honest matrix of what it actually enforces.

**`DockerSandbox` is now the real default (2026-07-28).**
:mod:`ai_os_kernel.sandbox.default_executor` resolves which backend a
caller gets from the `AIOS_SANDBOX_BACKEND` environment variable
(`"docker"`, the default, or `"local"`) — see that module's own
docstring for the full reasoning. Each backend also now declares its
own :attr:`~ai_os_kernel.sandbox.executor.SandboxExecutor.python_command`
— the portable way to invoke a Python interpreter *inside whatever that
backend actually runs commands in* — closing the real gap that
previously blocked `DockerSandbox` from being usable by the Software
Engineering pack's own agents, which had hardcoded the host's own
`sys.executable`.

**The ADR-0016 hardening path is now a real configuration line
(`P03-S01-M20-T05`), not just documented intent.** `DockerSandbox`
accepts a `runtime` parameter (`AIOS_SANDBOX_RUNTIME`, unset by
default) passed straight through to the Docker Engine's own
`containers.create(..., runtime=...)` — exactly the "drop-in
`SandboxRuntime` configuration ... a configuration change, not a
redesign" ADR-0016 itself names for gVisor. **Disclosed, not silently
assumed:** this environment's own Docker installs no gVisor/Firecracker
runtime (`docker info` here registers only
`io.containerd.runc.v2`/`nvidia`/`runc`), so what is actually proven
end to end is the configuration plumbing itself — a valid runtime name
reaches the real Docker Engine and executes correctly, and a
genuinely-unknown one is refused by the real Engine — not observed
hardened isolation. See `docker_executor.py`'s own docstring for the
full reasoning.
"""
