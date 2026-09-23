"""`--config` sets a default for a flag the run did not pass.

A config naming `max_pages: 2` was accepted and ignored: the crawl read fifty.
argparse had already filled its own default, so `_apply_config`'s "only when
nobody set it" test - a value of None or False - was never true for a numeric
flag. Only the booleans, which default to False, ever came through. The
numeric defaults now arrive after the config is read.

`max_redirects` sat in the accepted keys naming no flag at all, so it reached
no code either; the keys and the flags are held together here.
"""

from __future__ import annotations

import argparse
import io
import json

import pytest

from geo_audit.cli import CONFIG_KEYS, FLAG_DEFAULTS, build_parser, main
from geo_audit.lib import crawl as crawl_lib, http


def _limits(site, geo_home, *extra) -> dict:
    buffer = io.StringIO()
    main(["crawl", f"{site.url}/hub.html", "--allow-private", *extra, "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())["crawl"]


def _config(tmp_path, values: dict) -> str:
    path = tmp_path / "geo-config.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return str(path)


def test_a_config_sets_the_numeric_flags_it_names(site, geo_home, tmp_path):
    crawl = _limits(site, geo_home, "--config", _config(tmp_path, {"max_pages": 2, "rate": 50.0, "timeout": 12.5}))
    assert crawl["limits"]["max_pages"] == 2
    assert crawl["limits"]["requests_per_second"] == 50.0
    assert crawl["limits"]["timeout"] == 12.5
    assert crawl["pages_crawled"] == 2, "the cap the config set is the cap the crawl honoured"


def test_a_flag_on_the_command_line_beats_the_config(site, geo_home, tmp_path):
    config = _config(tmp_path, {"max_pages": 2, "rate": 50.0})
    assert _limits(site, geo_home, "--config", config, "--max-pages", "4")["limits"]["max_pages"] == 4


def test_the_documented_defaults_hold_when_nobody_sets_them(site, geo_home):
    limits = _limits(site, geo_home, "--rate", "50")["limits"]
    assert limits["max_pages"] == crawl_lib.MAX_PAGES
    assert limits["timeout"] == http.DEFAULT_TIMEOUT
    assert limits["concurrency"] == crawl_lib.CONCURRENCY


def test_a_boolean_key_still_comes_through(site, geo_home, tmp_path):
    config = _config(tmp_path, {"allow_private": True, "no_sitemap": True})
    buffer = io.StringIO()
    main(["crawl", f"{site.url}/hub.html", "--config", config, "--rate", "50", "--max-pages", "3",
          "--json", "--quiet"], out=buffer)
    envelope = json.loads(buffer.getvalue())
    assert envelope["ok"] is True, "allow_private came from the config, so a loopback URL was allowed"
    assert envelope["crawl"]["limits"]["sitemap_used"] is False


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_every_accepted_key_names_a_flag(key):
    """`--config` is documented as "JSON file of default flag values", so a key
    that names no flag can only ever be read and dropped."""
    parser = build_parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    dests = {action.dest for sub in subparsers.choices.values() for action in sub._actions if action.option_strings}
    assert key in dests


@pytest.mark.parametrize("key", sorted(FLAG_DEFAULTS))
def test_every_filled_default_is_the_one_the_help_promises(key):
    parser = build_parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for sub in subparsers.choices.values():
        for action in sub._actions:
            if action.dest == key and action.option_strings:
                assert action.default is None, f"{key} still carries an argparse default"
                if action.help and "default" in action.help:
                    assert f"{FLAG_DEFAULTS[key]:g}" in action.help
