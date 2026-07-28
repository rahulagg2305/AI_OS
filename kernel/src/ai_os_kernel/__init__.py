"""AI_OS Platform Kernel.

The domain-agnostic runtime core of AI_OS. See
docs/03_architecture/kernel/kernel_architecture.md.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ai-os-kernel")
except PackageNotFoundError:  # pragma: no cover - only if run without an install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
