"""Unit tests for EntrypointLoader — no database, no real pack
loading (ADR-0015 does not apply; this is pure Python import
mechanics)."""

import pytest

from ai_os_kernel.workflow_engine.entrypoint_loader import EntrypointLoader
from ai_os_kernel.workflow_engine.errors import EntrypointLoadError

_THIS_MODULE = "tests.unit.kernel.workflow_engine.test_entrypoint_loader"


class _StubWithNoArgs:
    """A small local stub class — a valid entrypoint target that takes
    no constructor arguments, mirroring EchoAgent/EchoTool's own shape."""

    def __init__(self) -> None:
        self.marker = "constructed"


class _StubRequiringAnArgument:
    """A valid class, but one whose constructor cannot succeed with the
    loader's zero-argument construction — proves a raising constructor
    becomes a clear EntrypointLoadError, not a bare TypeError."""

    def __init__(self, required: str) -> None:
        self.required = required


not_a_class = 42


def test_load_constructs_a_real_object_from_a_valid_entrypoint() -> None:
    loader = EntrypointLoader()

    loaded = loader.load(f"{_THIS_MODULE}:_StubWithNoArgs")

    assert isinstance(loaded, _StubWithNoArgs)
    assert loaded.marker == "constructed"


def test_load_returns_a_fresh_instance_each_call() -> None:
    loader = EntrypointLoader()

    first = loader.load(f"{_THIS_MODULE}:_StubWithNoArgs")
    second = loader.load(f"{_THIS_MODULE}:_StubWithNoArgs")

    assert first is not second


@pytest.mark.parametrize(
    "malformed",
    [
        "no_colon_at_all",
        ":MissingModule",
        "missing.class:",
        "1module:Class",
        "module:1Class",
        "",
    ],
)
def test_load_rejects_a_malformed_entrypoint_string(malformed: str) -> None:
    loader = EntrypointLoader()

    with pytest.raises(EntrypointLoadError, match="not of the documented form"):
        loader.load(malformed)


def test_load_raises_clearly_for_an_unimportable_module() -> None:
    loader = EntrypointLoader()

    with pytest.raises(EntrypointLoadError, match="could not import module"):
        loader.load("this_module_does_not_exist_anywhere:SomeClass")


def test_load_raises_clearly_for_a_missing_attribute() -> None:
    loader = EntrypointLoader()

    with pytest.raises(EntrypointLoadError, match="has no attribute"):
        loader.load(f"{_THIS_MODULE}:ThisClassDoesNotExist")


def test_load_raises_clearly_when_the_name_is_not_a_class() -> None:
    loader = EntrypointLoader()

    with pytest.raises(EntrypointLoadError, match="is not a class"):
        loader.load(f"{_THIS_MODULE}:not_a_class")


def test_load_raises_clearly_when_construction_fails() -> None:
    loader = EntrypointLoader()

    with pytest.raises(EntrypointLoadError, match="failed to construct"):
        loader.load(f"{_THIS_MODULE}:_StubRequiringAnArgument")
