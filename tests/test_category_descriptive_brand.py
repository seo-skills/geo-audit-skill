"""A descriptive brand keeps its category question.

qrcodedynamic.com calls itself "QR Code Dynamic". The category sanitizer removed
the brand word by word, so ChatGPT's "Dynamic QR code generator" became
"generator" and was rejected, and Gemini's "QR Code Generator Software" became
"generator software": every engine was then asked for the best generator
software brands and listed AI image and text generators.
"""

from __future__ import annotations

import pytest

from geo_audit.assistants import sanitize_category


@pytest.mark.parametrize(("raw", "category"), [
    ("Dynamic QR code generator", "dynamic QR code generator"),
    ("QR Code Generator Software", "QR code generator software"),
])
def test_a_descriptive_brand_leaves_its_category_whole(raw, category):
    assert sanitize_category(raw, "QR Code Dynamic", "qrcodedynamic.com") == category


def test_the_brand_itself_is_still_removed_as_a_name():
    assert sanitize_category("QR Code Dynamic generator software", "QR Code Dynamic", "qrcodedynamic.com") == (
        "generator software"
    )
    assert sanitize_category("Acme SEO audit software", "Acme", "acme.example") == "SEO audit software"
    assert sanitize_category("popupsmart popup builder", "Popupsmart", "popupsmart.com") == "popup builder"
