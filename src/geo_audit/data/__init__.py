"""Versioned data: weights, thresholds, tiers, crawler tokens, finding copy.

Loaded once and cached. Everything here carries `data_version`, which appears
in every envelope so a score can be traced to the constants that produced it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    with resources.files(__package__).joinpath(f"{name}.json").open(
        "r", encoding="utf-8"
    ) as handle:
        return json.load(handle)


def data_version() -> str:
    return load("meta")["data_version"]


def tiers() -> list[dict]:
    return load("tiers")["tiers"]


def tier_for(score: int) -> dict:
    for tier in tiers():
        if score >= tier["min"]:
            return tier
    return tiers()[-1]


def weights() -> dict:
    return load("weights")["categories"]


def thresholds(section: str) -> dict:
    return load("thresholds")[section]


def crawlers() -> list[dict]:
    return load("ai_crawlers")["crawlers"]


def crawler_tokens() -> list[str]:
    return [c["token"] for c in crawlers()]


def finding_template(kind: str, key: str) -> dict:
    return load("findings")[kind][key]
