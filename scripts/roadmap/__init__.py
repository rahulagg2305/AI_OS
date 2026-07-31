"""Roadmap ticket parsing, validation, and rollup generation (Phase R2).

`scripts/` is a regular package (`scripts/__init__.py`), so this
subpackage carries its own marker rather than relying on PEP 420
namespace-package fallback — the fallback happened to work locally but
is not a property worth depending on for the code that enforces the
roadmap's own structural invariants.
"""
