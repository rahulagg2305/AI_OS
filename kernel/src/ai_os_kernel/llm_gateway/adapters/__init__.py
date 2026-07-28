"""Provider Adapters — the *only* place a provider SDK may be imported
(llm_gateway.md §2: "Provider SDKs may be imported only inside
kernel/llm_gateway/adapters/. This is enforced by an import-boundary
check in CI, not by convention."). The CI check itself
(``scripts/check_import_boundaries.py``) does not exist yet — see
``.github/workflows/ci.yml``'s own "Import boundary check" step, already
gated on that script's existence — so this boundary is honoured by this
module's placement today, not yet mechanically enforced. Nothing outside
this package imports :mod:`anthropic`.

:class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.
AnthropicAdapter` is the one adapter implemented so far — a second
provider adapter (llm_gateway.md §14: "Adding a Provider") is real,
later work, not attempted here.
"""
