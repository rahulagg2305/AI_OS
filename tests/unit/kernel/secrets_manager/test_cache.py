"""``CachingSecretProvider`` — proves a cache hit is served within TTL
without re-resolving, and that an expired or explicitly-invalidated
entry is genuinely re-resolved (never served stale), against a fake
clock rather than real sleeps. ``P01-S02-M19-T05``.
"""

from __future__ import annotations

import asyncio

import pytest

from ai_os_kernel.secrets_manager.cache import CachingSecretProvider
from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.value import SecretValue


class _FakeClock:
    """An injectable clock a test can advance deterministically —
    no ``asyncio.sleep`` or real elapsed time involved."""

    def __init__(self, *, now: float = 0.0) -> None:
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _CountingProvider:
    """A fake ``SecretProvider`` that records how many times it was
    actually asked to resolve, and can be told to start returning a
    different value — standing in for "the secret rotated at its
    source"."""

    def __init__(self) -> None:
        self.call_count = 0
        self._current_value = "first-value"

    def rotate(self, new_value: str) -> None:
        self._current_value = new_value

    async def resolve(self, reference: str) -> SecretValue:
        self.call_count += 1
        return SecretValue(self._current_value)


def test_ttl_seconds_must_be_positive() -> None:
    with pytest.raises(ValueError, match="ttl_seconds must be positive"):
        CachingSecretProvider(_CountingProvider(), ttl_seconds=0)


def test_a_cached_value_is_served_within_ttl_without_re_resolving() -> None:
    async def _run() -> None:
        clock = _FakeClock()
        provider = _CountingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=60, clock=clock)

        first = await cache.resolve("secret://env/llm-api-key")
        clock.advance(30)  # still within the 60s TTL
        second = await cache.resolve("secret://env/llm-api-key")

        assert first.reveal() == "first-value"
        assert second.reveal() == "first-value"
        assert provider.call_count == 1  # the second call was served from cache

    asyncio.run(_run())


def test_an_expired_entry_is_genuinely_re_resolved_not_served_stale() -> None:
    async def _run() -> None:
        clock = _FakeClock()
        provider = _CountingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=60, clock=clock)

        first = await cache.resolve("secret://env/llm-api-key")
        provider.rotate("rotated-value")  # the secret changed at its source
        clock.advance(61)  # past the TTL
        second = await cache.resolve("secret://env/llm-api-key")

        assert first.reveal() == "first-value"
        assert second.reveal() == "rotated-value"  # the new value, not the stale cached one
        assert provider.call_count == 2  # the second call genuinely re-resolved

    asyncio.run(_run())


def test_an_entry_exactly_at_its_expiry_boundary_is_re_resolved() -> None:
    async def _run() -> None:
        clock = _FakeClock()
        provider = _CountingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=60, clock=clock)

        await cache.resolve("secret://env/llm-api-key")
        clock.advance(60)  # exactly at expiry -- not "still live"
        await cache.resolve("secret://env/llm-api-key")

        assert provider.call_count == 2

    asyncio.run(_run())


def test_explicit_invalidate_forces_re_resolution_before_ttl_expires() -> None:
    """The rotation hook: a caller that learns of a rotation out of
    band does not have to wait out the TTL."""

    async def _run() -> None:
        clock = _FakeClock()
        provider = _CountingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=3600, clock=clock)

        first = await cache.resolve("secret://env/llm-api-key")
        provider.rotate("rotated-value")
        cache.invalidate("secret://env/llm-api-key")  # well within the TTL window
        second = await cache.resolve("secret://env/llm-api-key")

        assert first.reveal() == "first-value"
        assert second.reveal() == "rotated-value"
        assert provider.call_count == 2

    asyncio.run(_run())


def test_invalidate_of_an_uncached_reference_is_a_no_op() -> None:
    cache = CachingSecretProvider(_CountingProvider(), ttl_seconds=60)

    cache.invalidate("secret://env/never-resolved")  # must not raise


def test_invalidate_all_clears_every_cached_entry() -> None:
    async def _run() -> None:
        clock = _FakeClock()
        provider = _CountingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=3600, clock=clock)

        await cache.resolve("secret://env/one")
        await cache.resolve("secret://env/two")
        cache.invalidate_all()
        await cache.resolve("secret://env/one")
        await cache.resolve("secret://env/two")

        assert provider.call_count == 4

    asyncio.run(_run())


def test_different_references_are_cached_independently() -> None:
    async def _run() -> None:
        clock = _FakeClock()
        provider = _CountingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=60, clock=clock)

        await cache.resolve("secret://env/one")
        await cache.resolve("secret://env/two")
        await cache.resolve("secret://env/one")  # still cached
        await cache.resolve("secret://env/two")  # still cached

        assert provider.call_count == 2

    asyncio.run(_run())


def test_the_wrapped_providers_resolution_error_propagates_uncached() -> None:
    """A failed resolution must never be cached as if it were a value —
    the next call should try again, not replay the same failure or a
    stale success."""

    class _FailingThenSucceedingProvider:
        def __init__(self) -> None:
            self.call_count = 0

        async def resolve(self, reference: str) -> SecretValue:
            self.call_count += 1
            if self.call_count == 1:
                raise SecretResolutionError("not set yet")
            return SecretValue("now-set")

    async def _run() -> None:
        provider = _FailingThenSucceedingProvider()
        cache = CachingSecretProvider(provider, ttl_seconds=60)

        with pytest.raises(SecretResolutionError):
            await cache.resolve("secret://env/llm-api-key")

        value = await cache.resolve("secret://env/llm-api-key")

        assert value.reveal() == "now-set"
        assert provider.call_count == 2

    asyncio.run(_run())


def test_a_cached_secretvalue_never_prints_the_real_value() -> None:
    async def _run() -> None:
        cache = CachingSecretProvider(_CountingProvider(), ttl_seconds=60)

        value = await cache.resolve("secret://env/llm-api-key")

        assert str(value) == "***"
        assert repr(value) == "SecretValue('***')"

    asyncio.run(_run())
