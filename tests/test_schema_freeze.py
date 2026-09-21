"""The envelope contract, enforced rather than described.

`schema_version` is a promise that the shape does not change without notice.
A promise nobody checks is a comment, so this file checks it three ways: every
command's output validates against a published JSON Schema, the top-level key
set matches a frozen list, and a run that fails validates too.
"""

from __future__ import annotations

import io
import json
from importlib import resources
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from geo_audit._version import SCHEMA_VERSION
from geo_audit.cli import COMMANDS, build_parser, main
from geo_audit.commands import scan as scan_cmd
from tests.fixture_server import Reply

ROOT = Path(__file__).resolve().parent.parent

# The freeze. Adding a line here is a deliberate act with a schema_version
# decision attached; it is not something that happens by writing a feature.
FROZEN_KEYS = {
    "schema_version", "command", "ok", "cli_version", "scoring_version",
    "data_version", "normalizer_version", "run_id", "observed_at", "evidence",
    "completeness", "scores", "signals", "findings", "error",
}
COMMAND_BLOCKS = {
    "page", "crawl", "compare", "schema", "llmstxt", "scan", "report",
    "prune", "checks", "rescore", "note", "site", "url",
}


def schema() -> dict:
    return json.loads(
        resources.files("geo_audit.assets").joinpath("envelope.schema.json").read_text("utf-8")
    )


@pytest.fixture(scope="module")
def validator():
    document = schema()
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def run(args) -> dict:
    buffer = io.StringIO()
    main(args + ["--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


@pytest.fixture(scope="module")
def every_envelope(site, tmp_path_factory):
    """One envelope per command, from a real run, built once for this module.

    Module-scoped on purpose: eleven commands times eleven parametrized cases
    is the same audit run over a hundred times, which is thirty seconds of CI
    per matrix cell for no extra coverage.
    """
    import os

    home = tmp_path_factory.mktemp("schema-home")
    previous = os.environ.get("GEO_HOME")
    os.environ["GEO_HOME"] = str(home)
    original_platforms = scan_cmd._platforms
    scan_cmd._platforms = lambda: {
        "wikipedia": {
            "label": "Wikipedia",
            "url": f"{site.url}/not-html?q={{query}}",
            "docs": "https://example.test",
            "needs_key": None,
        }
    }
    try:
        yield _build_envelopes(site)
    finally:
        scan_cmd._platforms = original_platforms
        if previous is None:
            os.environ.pop("GEO_HOME", None)
        else:
            os.environ["GEO_HOME"] = previous


def _build_envelopes(site) -> dict:
    page = ["--allow-private"]
    crawl = ["--allow-private", "--rate", "50", "--max-pages", "8"]

    envelopes = {
        "fetch": run(["fetch", f"{site.url}/ssr-rich.html", *page]),
        "crawl": run(["crawl", f"{site.url}/hub.html", *crawl]),
        "audit": run(["audit", f"{site.url}/hub.html", *crawl]),
        "score": run(["score", f"{site.url}/ssr-rich.html", "--no-render", *page]),
        "validate": run(["validate", f"{site.url}/schema-none.html", "--suggest", *page]),
        "llmstxt": run(["llmstxt", f"{site.url}/hub.html", "--generate", *crawl]),
        "scan": run(["scan", "Acme", "--allow-private"]),
        "prune": run(["prune", "--dry-run"]),
        "doctor": run(["doctor"]),
    }
    run(["audit", f"{site.url}/hub.html", *crawl])
    envelopes["compare"] = run(["compare", f"{site.url}/hub.html"])
    envelopes["report"] = run(["report", f"{site.url}/hub.html"])
    return envelopes


def test_the_schema_is_itself_valid():
    Draft202012Validator.check_schema(schema())


def test_the_schema_declares_the_version_the_code_emits():
    assert schema()["properties"]["schema_version"]["const"] == SCHEMA_VERSION


def test_every_command_has_an_envelope_in_the_fixture(every_envelope):
    """If a command is added and this fails, it has no schema coverage."""
    assert set(every_envelope) == set(COMMANDS)


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_each_command_validates_against_the_schema(every_envelope, validator, command):
    errors = sorted(validator.iter_errors(every_envelope[command]), key=lambda e: e.json_path)
    assert not errors, "\n".join(f"{e.json_path}: {e.message}" for e in errors[:5])


def test_a_failing_run_validates_too(geo_home, validator):
    envelope = run(["score", "not-a-url"])
    assert envelope["ok"] is False
    errors = list(validator.iter_errors(envelope))
    assert not errors, [e.message for e in errors[:3]]


def test_the_top_level_key_set_is_frozen(every_envelope):
    """A new top-level key is a schema_version decision, not a feature."""
    for command, envelope in every_envelope.items():
        extra = set(envelope) - FROZEN_KEYS - COMMAND_BLOCKS
        assert not extra, f"{command} emits unfrozen key(s): {sorted(extra)}"
        missing = FROZEN_KEYS - set(envelope)
        assert not missing, f"{command} is missing frozen key(s): {sorted(missing)}"


def test_the_schema_allows_exactly_the_frozen_keys():
    properties = set(schema()["properties"])
    assert properties == FROZEN_KEYS | COMMAND_BLOCKS
    assert schema()["additionalProperties"] is False, "the freeze depends on this"


def test_every_declared_command_is_in_the_schema_enum():
    parser = build_parser()
    subparsers = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    assert set(schema()["properties"]["command"]["enum"]) == set(subparsers.choices)


def test_an_added_key_would_be_rejected(every_envelope, validator):
    """Proof the freeze bites, rather than being a schema nobody validates."""
    envelope = dict(every_envelope["score"])
    envelope["helpful_extra"] = 1
    errors = list(validator.iter_errors(envelope))
    assert errors, "additionalProperties: false is not doing anything"


def test_a_null_signal_value_is_legal_and_a_string_is_not(every_envelope, validator):
    envelope = json.loads(json.dumps(every_envelope["audit"]))
    envelope["signals"][0]["value"] = None
    assert not list(validator.iter_errors(envelope))
    envelope["signals"][0]["value"] = "not measured"
    assert list(validator.iter_errors(envelope)), "a value must be a number or null"


def test_an_error_without_a_hint_is_rejected(validator, geo_home):
    envelope = run(["score", "not-a-url"])
    envelope["error"]["hint"] = ""
    assert list(validator.iter_errors(envelope)), "every error must carry a hint"


# The goldens blank out whatever differs per run. The schema still has an
# opinion about those fields - `run_id` is a ULID, `observed_at` is an instant -
# so put a representative value back rather than loosening the schema.
ULID = "01M315PVWZGG3V6XH5E9YJMBW5"
INSTANT = "2026-09-21T00:00:00Z"
REHYDRATE = {
    "run_id": ULID,
    "from_run": ULID,
    "observed_at": INSTANT,
    "oldest_kept": INSTANT,
}


def _stand_in(key: str):
    """A value of the same *type* the field really carries.

    Substituting a string everywhere would pass today only because the schema
    does not yet reach into these blocks, and would quietly go on passing when
    it does.
    """
    if key in REHYDRATE:
        return REHYDRATE[key]
    if "bytes" in key or key.endswith("_ms"):
        return 1234
    return "/tmp/scrubbed"


def rehydrate(node):
    if isinstance(node, dict):
        return {
            key: _stand_in(key) if value == "<volatile>" else rehydrate(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [rehydrate(item) for item in node]
    return node


@pytest.mark.parametrize(
    "golden", sorted((ROOT / "tests" / "goldens").glob("*.json")), ids=lambda p: p.stem
)
def test_every_golden_validates_against_the_schema(validator, golden):
    """The freeze above only sees runs that went well.

    The goldens are where the awkward states live - a refused start URL, a
    PARTIAL crawl, an envelope with `ok: false` - and those are exactly the
    states a caller hits when something is wrong. A schema that holds for the
    happy path and not for the rest is worse than no schema, because the
    caller only finds out on the day it matters.
    """
    envelope = rehydrate(json.loads(golden.read_text(encoding="utf-8")))
    errors = sorted(validator.iter_errors(envelope), key=lambda e: e.json_path)
    assert not errors, "\n".join(f"{e.json_path}: {e.message}" for e in errors[:5])


def test_the_schema_is_shipped_in_the_wheel():
    """Consumers validate against the version they installed, not against main."""
    assert resources.files("geo_audit.assets").joinpath("envelope.schema.json").is_file()
