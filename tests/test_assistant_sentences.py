"""The sentences a reader sees say what happened in words, not in transport codes.

The client report read "Gemini did not answer the question about Acme (HTTP 502)".
The envelope keeps the code for a program; the sentence is for a person.
"""

from __future__ import annotations

import pytest

from geo_audit.assistants import describe


def _failed(first: str | None = None, second: str | None = None) -> dict:
    return {
        "brand_question": {"status": "failed", "reason": first} if first else {"status": "answered", "recognized": True},
        "category_question": {"status": "failed", "reason": second} if second else {"status": "skipped", "reason": "x"},
    }


@pytest.mark.parametrize(("code", "words"), [
    ("HTTP 502", "the service was unavailable"),
    ("HTTP 429", "too many requests were running on the account at once"),
    ("HTTP 403", "the request was refused"),
    ("GEO_E_TIMEOUT", "it took too long to answer"),
    ("GEO_E_CONNECT", "the request did not go through"),
    ("unreadable answer", "its answer could not be read"),
    ("refused", "it declined to answer"),
])
def test_a_failure_is_said_in_words(code, words):
    about, _ = describe(_failed(first=code), "Acme")
    assert about == f"gave no usable answer about Acme: {words}."
    _, ranking = describe(_failed(second=code), "Acme")
    assert ranking == f"gave no usable answer to the category question: {words}."
    assert code not in about + ranking or code in ("refused",)


def test_an_empty_answer_does_not_repeat_the_engine_name():
    """The label comes first: "Google AI Mode showed no AI Mode answer" said it twice."""
    entry = {"brand_question": {"status": "empty"}, "category_question": {"status": "empty"}}
    assert describe(entry, "Acme") == (
        "showed no answer about Acme.",
        "showed no answer for the category question.",
    )


@pytest.mark.parametrize(("category", "read"), [
    ("E-commerce and online marketplace", "e-commerce and online marketplace"),
    ("SEO audit software", "SEO audit software"),
    ("B2B lead generation", "B2B lead generation"),
    ("Popup builder software", "popup builder software"),
])
def test_an_engine_category_is_cased_for_the_middle_of_a_sentence(category, read):
    """Trendyol's live answer read "describes Trendyol as E-commerce and online marketplace"."""
    entry = {"brand_question": {"status": "answered", "recognized": True, "category": category},
             "category_question": {"status": "skipped", "reason": "x"}}
    assert describe(entry, "Trendyol")[0] == f"describes Trendyol as {read}."
