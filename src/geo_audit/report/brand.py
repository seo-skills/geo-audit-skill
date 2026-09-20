"""Brand tokens and the contrast rule.

A white-label report that renders the agency's brand colour as a background
with unreadable text on it is worse than one that ignores the brand: the
agency sends it to a client without looking, because it has their logo on it.

So the rule here is not "use the brand colour". It is "use the brand colour if
the text on it clears WCAG AA, and otherwise fall back loudly" - a warning on
stderr and an annotation in the operator view, never a silent substitution.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from geo_audit.errors import GeoError

MIN_CONTRAST = 4.5
DEFAULT_PRIMARY = "#1F3A5F"
DEFAULT_ACCENT = "#0E7C66"
DEFAULT_INK = "#14181F"
DEFAULT_MUTED = "#5A6472"
DEFAULT_PAPER = "#FFFFFF"
MAX_LOGO_HEIGHT_PX = 48

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex(value: str) -> tuple[int, int, int]:
    if not HEX.match(value or ""):
        raise ValueError(f"{value!r} is not a hex colour")
    digits = value.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _channel(value: int) -> float:
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(colour: str) -> float:
    """WCAG 2.x relative luminance."""
    red, green, blue = parse_hex(colour)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(first: str, second: str) -> float:
    a, b = relative_luminance(first), relative_luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def readable_on(background: str) -> str:
    """Black or white, whichever reads better on this background."""
    return (
        "#FFFFFF"
        if contrast_ratio(background, "#FFFFFF") >= contrast_ratio(background, "#000000")
        else "#000000"
    )


@dataclass
class Brand:
    name: str | None = None
    logo: str | None = None
    primary: str = DEFAULT_PRIMARY
    accent: str = DEFAULT_ACCENT
    ink: str = DEFAULT_INK
    muted: str = DEFAULT_MUTED
    paper: str = DEFAULT_PAPER
    on_primary: str = "#FFFFFF"
    attribution: bool = True
    warnings: list[str] = field(default_factory=list)
    source: str | None = None

    @property
    def customised(self) -> bool:
        return self.primary != DEFAULT_PRIMARY or bool(self.name) or bool(self.logo)

    def contrast_report(self) -> list[dict]:
        """Every pairing the template relies on, with its measured ratio."""
        pairs = [
            ("body text on paper", self.ink, self.paper),
            ("muted text on paper", self.muted, self.paper),
            ("header text on primary", self.on_primary, self.primary),
            ("accent text on paper", self.accent, self.paper),
        ]
        return [
            {
                "pair": label,
                "foreground": foreground,
                "background": background,
                "ratio": contrast_ratio(foreground, background),
                "passes_aa": contrast_ratio(foreground, background) >= MIN_CONTRAST,
            }
            for label, foreground, background in pairs
        ]


def load(path: str | Path | None) -> Brand:
    """Read brand.json, validate it, and keep every substitution visible."""
    if path is None:
        return Brand()

    target = Path(path).expanduser()
    if not target.exists():
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"No brand file at {target}. Omit --brand-config to use the default palette.",
        )
    try:
        values = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GeoError("GEO_E_BAD_ARGS", f"{target} is not valid JSON: {exc.msg}.") from exc
    if not isinstance(values, dict):
        raise GeoError("GEO_E_BAD_ARGS", f"{target} must contain a JSON object.")

    brand = Brand(source=str(target))
    brand.name = values.get("name") or None
    brand.logo = values.get("logo") or None
    brand.attribution = bool(values.get("attribution", True))

    for field_name, default in (("primary", DEFAULT_PRIMARY), ("accent", DEFAULT_ACCENT)):
        supplied = values.get(field_name)
        if supplied is None:
            continue
        try:
            parse_hex(supplied)
        except ValueError:
            brand.warnings.append(
                f"{field_name} {supplied!r} is not a hex colour; using the default {default}."
            )
            continue
        setattr(brand, field_name, supplied)

    # Header text is chosen automatically, and that choice always clears AA:
    # the worst case of best-of-black-or-white over the entire sRGB cube is
    # 4.58:1. So there is no fallback here and pretending to check for one
    # would be theatre. An explicitly supplied `on_primary` is a different
    # matter, because a brand can hand us an unreadable pair on purpose.
    brand.on_primary = readable_on(brand.primary)
    supplied_on_primary = values.get("on_primary")
    if supplied_on_primary is not None:
        try:
            parse_hex(supplied_on_primary)
            ratio = contrast_ratio(supplied_on_primary, brand.primary)
            if ratio < MIN_CONTRAST:
                brand.warnings.append(
                    f"on_primary {supplied_on_primary} on {brand.primary} is "
                    f"{ratio}:1, below the {MIN_CONTRAST}:1 AA minimum; using "
                    f"{brand.on_primary} instead."
                )
            else:
                brand.on_primary = supplied_on_primary
        except ValueError:
            brand.warnings.append(
                f"on_primary {supplied_on_primary!r} is not a hex colour; ignored."
            )

    # The accent carries links and small emphasis on the paper background, and
    # this is where brand palettes genuinely fail. A yellow accent on white is
    # 1.27:1. It is unreadable, it looks deliberate, and nobody notices until a
    # client does.
    accent_ratio = contrast_ratio(brand.accent, brand.paper)
    if accent_ratio < MIN_CONTRAST:
        brand.warnings.append(
            f"accent {brand.accent} on {brand.paper} is {accent_ratio}:1, below "
            f"the {MIN_CONTRAST}:1 AA minimum for small text; using the default "
            f"{DEFAULT_ACCENT}."
        )
        brand.accent = DEFAULT_ACCENT

    unknown = sorted(
        set(values) - {"name", "logo", "primary", "accent", "on_primary", "attribution"}
    )
    if unknown:
        brand.warnings.append(f"ignored unknown brand key(s): {', '.join(unknown)}")
    return brand
