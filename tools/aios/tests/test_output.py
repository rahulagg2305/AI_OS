"""Unit tests for ``ai_os_cli.output`` — pure logic, no server, no
filesystem."""

from __future__ import annotations

import json

import pytest

from ai_os_cli.output import render, resolve_output_format


def test_an_explicit_output_flag_always_wins() -> None:
    assert resolve_output_format("json") == "json"
    assert resolve_output_format("human") == "human"


def test_json_is_rendered_as_real_parseable_json(capsys: pytest.CaptureFixture[str]) -> None:
    render({"status": "live"}, output_format="json")
    out = capsys.readouterr().out
    assert json.loads(out) == {"status": "live"}


def test_human_renders_a_list_of_dicts_as_a_table_with_every_real_column(
    capsys: pytest.CaptureFixture[str],
) -> None:
    render([{"a": 1, "b": 2}, {"a": 3, "c": 4}], output_format="human")
    out = capsys.readouterr().out
    # Real column union, not just the first row's own keys.
    assert "a" in out
    assert "b" in out
    assert "c" in out


def test_human_renders_an_empty_list_honestly() -> None:
    # Must not raise — an empty result set is real, valid data.
    render([], output_format="human")


def test_human_renders_a_single_dict_as_a_one_row_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    render({"status": "live"}, output_format="human")
    out = capsys.readouterr().out
    assert "status" in out
    assert "live" in out
