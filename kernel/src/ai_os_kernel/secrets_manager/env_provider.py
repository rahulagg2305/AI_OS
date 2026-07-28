"""The environment-variable secret backend — ADR-0024: "Environment
variables | Local development only." No rotation, no audit trail
beyond what the caller does with the result, and visible to child
processes, which is exactly why ADR-0024 scopes this backend to local
development and never production.

Only this one backend exists at this stage. Vault, the encrypted-file
backend, and cloud secret managers are not yet implemented — nothing
here assumes they will look like this one.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.reference import parse_secret_reference
from ai_os_kernel.secrets_manager.value import SecretValue

_PROVIDER_NAME = "env"

# Every resolvable env var is namespaced under this prefix — never a
# bare, unprefixed name — so this backend can only ever read a variable
# it was clearly meant to read, not collide with an unrelated one
# (PATH, HOME, ...) that happens to share a name.
_ENV_VAR_PREFIX = "AIOS_SECRET_"

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _env_var_name(secret_name: str) -> str:
    """Map a reference's ``<name>`` (a path-like identifier, e.g.
    ``llm/anthropic-api-key``) onto an environment variable name, e.g.
    ``AIOS_SECRET_LLM_ANTHROPIC_API_KEY``."""
    normalized = _NON_ALNUM.sub("_", secret_name.upper()).strip("_")
    return f"{_ENV_VAR_PREFIX}{normalized}"


class EnvSecretProvider:
    """The only :class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`
    implementation at this stage.

    ``env`` defaults to the real process environment
    (:data:`os.environ`) but is injectable so tests never have to
    mutate real process state to exercise this class (ADR-0004; mirrors
    every other injected-dependency seam in this codebase).
    """

    def __init__(self, *, env: Mapping[str, str] | None = None) -> None:
        self._env: Mapping[str, str] = os.environ if env is None else env

    async def resolve(self, reference: str) -> SecretValue:
        parsed = parse_secret_reference(reference)

        if parsed.provider != _PROVIDER_NAME:
            raise SecretResolutionError(
                f"'{reference}' names provider '{parsed.provider}', not "
                f"'{_PROVIDER_NAME}' — EnvSecretProvider only resolves "
                f"'{_PROVIDER_NAME}://' references"
            )
        if parsed.version is not None:
            raise SecretResolutionError(
                f"'{reference}' requests version '{parsed.version}', but the "
                f"'{_PROVIDER_NAME}' backend has no versioning — a plain "
                "environment variable is always exactly one current value"
            )

        env_var_name = _env_var_name(parsed.name)
        value = self._env.get(env_var_name)
        if value is None:
            raise SecretResolutionError(
                f"'{reference}' resolves to environment variable '{env_var_name}', which is not set"
            )
        return SecretValue(value)
