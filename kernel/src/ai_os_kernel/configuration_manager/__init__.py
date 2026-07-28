"""Configuration Manager — the single source of runtime configuration.

Layered precedence: built-in defaults -> pack defaults -> platform
config -> environment config -> runtime overrides -> experiment
overrides -> secrets (docs/03_architecture/kernel/configuration_manager.md
§4). Only layers 1, 3, and 4 are implemented at this stage.

No component should read a configuration file directly — everything
goes through :class:`ConfigurationManager` and the resulting
:class:`PlatformConfig`.

See docs/03_architecture/kernel/configuration_manager.md.
"""

from ai_os_kernel.configuration_manager.bootstrap_env import BootstrapEnv
from ai_os_kernel.configuration_manager.errors import ConfigurationError
from ai_os_kernel.configuration_manager.loader import ConfigurationManager
from ai_os_kernel.configuration_manager.models import PlatformConfig

__all__ = ["BootstrapEnv", "ConfigurationError", "ConfigurationManager", "PlatformConfig"]
