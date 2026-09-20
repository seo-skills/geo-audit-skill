"""The error contract. Frozen at this milestone, before any porting."""

from __future__ import annotations

import pytest

from geo_audit.errors import (
    ERRORS,
    EXIT_INTERNAL,
    EXIT_NETWORK,
    EXIT_PARTIAL,
    EXIT_STATE,
    EXIT_USAGE,
    GeoError,
)


def test_every_code_has_a_hint():
    for code, spec in ERRORS.items():
        assert spec.hint.strip(), f"{code} has no hint"
        assert len(spec.hint) > 25, f"{code}'s hint is too short to be a next action"


def test_every_code_has_a_docs_anchor():
    for code, spec in ERRORS.items():
        assert spec.docs.endswith("#" + code.lower().replace("_", "-"))


def test_every_code_maps_to_a_known_exit_class():
    allowed = {EXIT_INTERNAL, EXIT_USAGE, EXIT_NETWORK, EXIT_STATE, EXIT_PARTIAL}
    for code, spec in ERRORS.items():
        assert spec.exit_code in allowed, f"{code} exits {spec.exit_code}"


def test_codes_are_namespaced():
    for code in ERRORS:
        assert code.startswith("GEO_E_")


def test_unknown_code_is_a_programming_error():
    with pytest.raises(KeyError):
        GeoError("GEO_E_NOPE", "nope")


def test_error_dict_shape():
    error = GeoError("GEO_E_TIMEOUT", "Couldn't reach example.com.")
    payload = error.as_dict("~/.geo/logs/last-run.log")
    assert set(payload) == {"code", "message", "hint", "docs", "log"}
    assert payload["code"] == "GEO_E_TIMEOUT"
    assert "\n" not in payload["message"], "a user-facing message is one sentence"
    assert "Traceback" not in payload["message"]
