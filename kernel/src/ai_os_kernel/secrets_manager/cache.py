"""Bounded-lifetime caching for resolved secrets (``P01-S02-M19-T05``,
closing the module's own long-named gap: "TTL caching with rotation
invalidation" — see :mod:`ai_os_kernel.secrets_manager`'s "Not yet
implemented" list).

**Design.** :class:`CachingSecretProvider` wraps any
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider` — the
same "swappable implementation behind a ``Protocol``" seam every other
backend in this module already uses, so it composes with
:class:`~ai_os_kernel.secrets_manager.env_provider.EnvSecretProvider`,
:class:`~ai_os_kernel.secrets_manager.file_provider.FileSecretProvider`,
or a future Vault-backed provider without any of them changing.

**Two distinct staleness controls, because a rotation is not always
knowable in advance.** A ``ttl_seconds`` bound guarantees a cached
value is never served for longer than that window, so an
out-of-band rotation the cache has no way to observe (the ``env`` and
``file`` backends emit no rotation event) is still bounded — this is
the "expiry" half of the ticket's Goal. :meth:`invalidate` is the
"rotation" half: an explicit hook for a caller that *does* learn a
secret was rotated (a future Vault webhook, an admin action) to evict
it immediately rather than wait out the TTL.

**``ttl_seconds`` has no default.** A silently-applied default would
be exactly the hardcoded value this codebase's standing rules forbid
(no doc names a canonical TTL) — every caller must state the bound
that fits its own risk tolerance, the same reasoning
:class:`~ai_os_kernel.secrets_manager.file_provider.FileSecretProvider`
already applies to ``root``.

**Never logs or exposes a resolved value.** A cache entry holds the
:class:`~ai_os_kernel.secrets_manager.value.SecretValue` itself, not
its revealed string — the wrapper's own ``__str__``/``__repr__``
masking (ADR-0024 rule 2) already covers whatever this module does
with it, exactly as it does for every other holder of a
``SecretValue`` in this codebase.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.secrets_manager.value import SecretValue


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: SecretValue
    expires_at: float


class CachingSecretProvider:
    """A :class:`SecretProvider` that serves a wrapped provider's
    resolutions from a per-reference, bounded-lifetime cache.

    ``clock`` defaults to :func:`time.monotonic` (immune to wall-clock
    adjustments, the same reasoning a lease or lock timeout would use)
    but is injectable so tests can advance time deterministically
    instead of sleeping — mirrors every other injected-dependency seam
    in this codebase (ADR-0004).
    """

    def __init__(
        self,
        provider: SecretProvider,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._provider = provider
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _CacheEntry] = {}

    async def resolve(self, reference: str) -> SecretValue:
        """Serves ``reference`` from cache if a live entry exists;
        otherwise resolves through the wrapped provider and caches the
        result for ``ttl_seconds``."""
        now = self._clock()
        entry = self._entries.get(reference)
        if entry is not None and entry.expires_at > now:
            return entry.value

        value = await self._provider.resolve(reference)
        self._entries[reference] = _CacheEntry(value=value, expires_at=now + self._ttl_seconds)
        return value

    def invalidate(self, reference: str) -> None:
        """Evicts any cached entry for ``reference`` — the rotation
        hook: a caller that learns ``reference`` was rotated at its
        source calls this so the *next* :meth:`resolve` re-resolves
        instead of waiting out the TTL. A no-op if nothing is cached."""
        self._entries.pop(reference, None)

    def invalidate_all(self) -> None:
        """Evicts every cached entry — for a caller that learns of a
        rotation but cannot name which reference(s) it affected."""
        self._entries.clear()
