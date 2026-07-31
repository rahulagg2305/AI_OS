"""Configuration Manager — the single source of runtime configuration.

Layered precedence: built-in defaults -> pack defaults -> platform
config -> environment config -> runtime overrides -> experiment
overrides -> secrets (docs/03_architecture/kernel/configuration_manager.md
§4). Layers 1, 2, 3, and 4 are implemented at this stage.

**Layer 2, pack-level defaults** (added 2026-07-31, ``P01-S02-M01-T03``):
:func:`extract_pack_defaults` reads the ``default`` values declared in a
pack manifest's own ``configSchema``; :meth:`ConfigurationManager.load`'s
``pack_manifests`` argument merges them in ahead of the platform and
environment files, so either can still override a pack's suggestion.

No component should read a configuration file directly — everything
goes through :class:`ConfigurationManager` and the resulting
:class:`PlatformConfig`.

**The config change-audit trail** (added 2026-07-31, ``P01-S02-M01-T08``)
writes ``governance.config_changes`` rows: :class:`SqlConfigChangeWriter`
records a digest of the old/new value (never the value itself, so a
secret reference change never leaks it — data_model.md §9.2), and
:func:`verify_config_change` recomputes a digest from a known real value
to confirm it matches what's stored. See
:mod:`ai_os_kernel.configuration_manager.audit`.

See docs/03_architecture/kernel/configuration_manager.md.
"""

from ai_os_kernel.configuration_manager.audit import (
    ConfigChangeRecord,
    ConfigChangeVerificationResult,
    ConfigChangeWriter,
    SqlConfigChangeWriter,
    compute_value_digest,
    verify_config_change,
)
from ai_os_kernel.configuration_manager.bootstrap_env import BootstrapEnv
from ai_os_kernel.configuration_manager.errors import ConfigChangeAuditError, ConfigurationError
from ai_os_kernel.configuration_manager.loader import ConfigurationManager, extract_pack_defaults
from ai_os_kernel.configuration_manager.models import PlatformConfig

__all__ = [
    "BootstrapEnv",
    "ConfigChangeAuditError",
    "ConfigChangeRecord",
    "ConfigChangeVerificationResult",
    "ConfigChangeWriter",
    "ConfigurationError",
    "ConfigurationManager",
    "PlatformConfig",
    "SqlConfigChangeWriter",
    "compute_value_digest",
    "extract_pack_defaults",
    "verify_config_change",
]
