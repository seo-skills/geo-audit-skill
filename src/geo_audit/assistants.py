"""What AI assistants say about a brand, asked through the user's own scrape.do key.

PRD §3.10.1. Two questions per engine - what the brand is, and the best brands in
its category - sent to ChatGPT, Gemini and Google AI Mode through scrape.do's
plugin endpoints and paid for by the key in `GEO_SCRAPEDO_TOKEN`.

The answers are observations, never scores. One sampled output of a
non-deterministic model is not a measurement of a stable state, and the
invariant this package serves is that no number depends on model output. So an
answer is recorded as observed, under `scan.assistants`, and nothing here builds
a `Signal`.

The key is a credential to the user's paid account and is treated as one. It is
read from the environment only, never from a flag. scrape.do takes it in the
query string, so no vendor URL is ever returned, and a transport failure is
reported by its error code alone: `http.fetch` names the URL in some messages.

The engine table lives here rather than in `data/` on purpose. `data/` holds the
constants a score is computed from, and every change there bumps `data_version`,
which `compare` refuses to cross. Nothing below reaches a score.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from geo_audit import envelope
from geo_audit.errors import GeoError
from geo_audit.lib import http
from geo_audit.lib.extract import excerpt
from geo_audit.lib.slug import host_of

TOKEN_ENV = "GEO_SCRAPEDO_TOKEN"
BASE = "https://api.scrape.do"
PROVIDER = "scrape.do"
LOCALE = "en-US"
MAX_BYTES = 1_000_000
# Waits before each retry of a transient 502. Gemini's "no warm session" came back
# twice within three seconds on a live run, so a second, longer wait is worth it;
# a 502 is uncharged, so a retry costs time, never credits.
RETRY_DELAYS = (3.0, 6.0)
INFO_TIMEOUT = 15.0

MAX_CITED = 8
MAX_LISTED = 12
MAX_COMPETITORS = 8


@dataclass(frozen=True)
class Engine:
    id: str
    label: str
    path: str
    credits: int
    timeout: float
    # How the question goes out: `prompt` for a chat engine, `query` for a search.
    kind: str
    params: dict = field(default_factory=dict)


# Credits per successful call and timeouts from scrape.do's documentation, read
# 2026-09-25. ChatGPT's upstream gives up at 60 seconds and Gemini's at 45.
ENGINES: dict[str, Engine] = {
    "chatgpt": Engine("chatgpt", "ChatGPT", "/plugin/chatgpt/chat", 25, 75.0, "prompt",
                      {"model": "auto", "geoCode": "us"}),
    "gemini": Engine("gemini", "Gemini", "/plugin/gemini/chat", 25, 60.0, "prompt"),
    "ai-mode": Engine("ai-mode", "Google AI Mode", "/plugin/google/search/ai-mode", 10, 45.0, "query",
                      {"hl": "en", "gl": "us", "google_domain": "google.com", "device": "desktop"}),
}
QUESTIONS = 2
# Statuses scrape.do documents as transient and uncharged on all three endpoints.
RETRYABLE = frozenset({502})
# The engines whose first answer names a category, in the order it is taken.
CATEGORY_SOURCES = ("chatgpt", "gemini")


def parse_engines(value: str) -> list[str]:
    """`all`, or a comma list of engine ids, in the order the table lists them."""
    wanted = {part.strip().lower() for part in value.split(",") if part.strip()}
    if not wanted:
        raise GeoError("GEO_E_BAD_ARGS", "--assistants needs `all` or a list such as `chatgpt,gemini`.")
    if "all" in wanted:
        return list(ENGINES)
    unknown = sorted(wanted - set(ENGINES))
    if unknown:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"Unknown assistant {', '.join(unknown)}. Choose from all, {', '.join(ENGINES)}.",
        )
    return [engine for engine in ENGINES if engine in wanted]


def max_credits(engines: list[str]) -> int:
    return sum(ENGINES[engine].credits * QUESTIONS for engine in engines)


# --- the brand and its host -------------------------------------------------

# Two-label public suffixes in common use, so `brand.co.uk` yields `brand` and
# not `co`. A short list instead of a public-suffix dependency: a miss costs a
# less specific label, never a wrong host.
_MULTI_PART_SUFFIXES = frozenset(
    "co.uk org.uk ac.uk gov.uk me.uk com.tr org.tr net.tr gen.tr com.au net.au org.au "
    "com.br net.br org.br co.jp ne.jp or.jp co.nz org.nz co.za org.za com.mx org.mx "
    "com.ar co.in net.in org.in co.kr or.kr com.cn net.cn com.sg com.hk co.il com.pl "
    "com.ua co.id com.my com.ph com.vn com.tw co.th com.eg com.sa com.pk com.ng co.ke".split()
)


def domain_label(host: str) -> str:
    """The registrable label of a host: `app.brand.io` -> `brand`, `brand.co.uk` -> `brand`."""
    parts = [part for part in host.lower().removeprefix("www.").split(".") if part]
    if len(parts) < 2:
        return parts[0] if parts else "site"
    if ".".join(parts[-2:]) in _MULTI_PART_SUFFIXES and len(parts) >= 3:
        return parts[-3]
    return parts[-2]


def own_host(host: str | None, site: str | None) -> bool | None:
    """Equal to the audited host or a subdomain of it. A parent never counts.

    None when there is no site to compare with: whose page it is cannot be said.
    """
    if not site:
        return None
    if not host:
        return False
    host, site = host.lower().removeprefix("www."), site.lower().removeprefix("www.")
    return host == site or host.endswith("." + site)


# Words that turn a name or a category into an instruction to the model.
_INSTRUCTION = re.compile(
    r"(?<![^\W_])(?:ignore|instructions?|answer|respond|reply|prompt|system|assistant|"
    r"disregard|previous|override)(?![^\W_])",
    re.IGNORECASE,
)


def sanitize_brand(name: str, site: str | None) -> str:
    """The brand as it may enter a question.

    Letters, digits, spaces and `&.'+-`, at most five words and 40 characters.
    The name is page-controlled when it comes from an audit, so one that reads as
    an instruction is replaced by the domain label rather than cleaned.
    """
    fallback = domain_label(site) if site else ""
    cleaned = re.sub(r"[^\w &.'+-]|_", " ", name)
    cleaned = " ".join(cleaned.split()[:5])[:40].strip()
    if not re.search(r"[^\W_]", cleaned) or _INSTRUCTION.search(cleaned):
        return fallback or cleaned
    return cleaned


def sanitize_category(raw: str, brand: str, site: str | None) -> str | None:
    """The category for the unbranded question, or None when nothing usable is left.

    The brand's own words are removed so the question stays unbranded; two to six
    words, 60 characters, lowercased except acronyms.
    """
    own = {word for word in re.split(r"[\W_]+", brand.lower()) if len(word) > 1}
    if site:
        own.add(domain_label(site))
    words = [
        word if re.fullmatch(r"[A-Z]{2,}", word) else word.lower()
        for word in re.sub(r"[^\w &/+-]|_", " ", raw).split()
        if (word == "&" or re.search(r"[^\W_]", word)) and word.lower() not in own
    ][:6]
    while len(" ".join(words)) > 60:
        words.pop()
    category = " ".join(words)
    if len(words) < 2 or _INSTRUCTION.search(category):
        return None
    return category


# --- the questions ----------------------------------------------------------


def brand_question(engine: str, brand: str, site: str | None) -> str:
    if ENGINES[engine].kind == "query":
        return f"what is {brand} {site}" if site else f"what is {brand}"
    who = f'"{brand}" ({site})' if site else f'"{brand}"'
    return (
        "Answer in exactly three lines and nothing else. CATEGORY: the product or "
        f"service category of {who} in 2 to 5 words. OFFERS: one sentence on what it "
        "offers. COMPETITORS: its five closest competitors as comma-separated brand "
        "names only."
    )


def category_question(engine: str, category: str) -> str:
    if ENGINES[engine].kind == "query":
        return f"best {category} brands"
    return f"What are the best {category} brands? List the top 10, one line each."


# --- one answer, whichever engine gave it -----------------------------------


@dataclass
class ListItem:
    name: str
    url: str | None


@dataclass
class Answer:
    """An engine's reply reduced to what the readers below use."""

    text: str
    cited: list[str]
    searched: bool
    search_queries: list[str] = field(default_factory=list)
    model: str | None = None
    # AI Mode sends its lists as structure, every usable one in order of preference
    # (ranked, then longest); the chat engines send theirs as Markdown in `text`.
    lists: list[tuple[bool, list[ListItem]]] | None = None
    empty: bool = False


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _str(value) -> str | None:
    return value if isinstance(value, str) else None


_FLAT_LINK = re.compile(r"(?<![\w/])url(?=\S)(.+?)(https?://[^\s)\]]+)")


def from_chatgpt(payload: dict) -> Answer | None:
    """chatgpt.com's streaming envelope, assembled by scrape.do.

    Undocumented and free to change, so every field is optional. The brand names
    survive only as link text in `output.markdown`; cited pages are the
    `grouped_webpages` references, never the flat `sources` list, which mixes
    citations with the brands' own homepages.
    """
    text = _str(_dict(payload.get("output")).get("markdown"))
    if not text:
        return None
    # ChatGPT's entity links sometimes arrive flattened to "urlApollo.iohttps://www.apollo.io".
    text = _FLAT_LINK.sub(lambda m: f"[{m.group(1).strip()}]({m.group(2)})", text)
    meta = _dict(_dict(_dict(payload.get("data")).get("message")).get("metadata"))
    cited = [
        _str(item.get("url"))
        for ref in _list(meta.get("content_references"))
        if _dict(ref).get("type") == "grouped_webpages"
        for item in map(_dict, _list(_dict(ref).get("items")))
        if _str(item.get("url"))
    ]
    queries = [q for q in _list(_dict(payload.get("tool_data")).get("search_queries")) if _str(q)]
    return Answer(text=text, cited=cited, searched=bool(queries), search_queries=queries,
                  model=_str(meta.get("model_slug")))


def from_gemini(payload: dict) -> Answer | None:
    """`{prompt, output.text, sources?, model?}`; `sources` only when grounded on the web."""
    text = _str(_dict(payload.get("output")).get("text"))
    if not text:
        return None
    sources = [url for url in _list(payload.get("sources")) if _str(url)]
    return Answer(text=text, cited=sources, searched=bool(sources), model=_str(payload.get("model")))


def from_ai_mode(payload: dict) -> Answer | None:
    """AI Mode's ordered blocks. No blocks means Google showed no AI Mode answer."""
    if "text_blocks" not in payload:
        return None
    blocks = [_dict(block) for block in _list(payload.get("text_blocks"))]
    cited = [_str(_dict(ref).get("link")) for ref in _list(payload.get("references"))]
    cited = [url for url in cited if url]
    if not blocks:
        return Answer(text="", cited=[], searched=False, empty=True)
    lines: list[str] = []
    # Every list the answer contains, each as (ranked, items, the entries' own text).
    candidates: list[tuple[bool, list[ListItem], list[str]]] = []
    numbered: list[tuple[ListItem, str]] = []
    for block in blocks:
        kind = block.get("type")
        if kind in ("list", "ordered_list"):
            entries = [_dict(entry) for entry in _list(block.get("list"))]
            texts = [_str(entry.get("snippet")) or "" for entry in entries]
            lines.extend(texts)
            if entries:
                candidates.append((kind == "ordered_list", [_ai_mode_item(entry) for entry in entries], texts))
        else:
            snippet = _str(block.get("snippet")) or ""
            lines.append(snippet)
            # A ranking written as numbered paragraphs: "1. OptinMonster — Best overall".
            match = _NUMBERED.match(snippet)
            if match and int(match.group(1)) == len(numbered) + 1:
                name = re.split(r"\s+[—–-]\s+|:\s", match.group(2), maxsplit=1)[0]
                numbered.append((ListItem(name=_plain(name).strip(" .:*"), url=None), snippet))
    if numbered:
        candidates.append((True, [item for item, _ in numbered], [text for _, text in numbered]))
    return Answer(text="\n".join(line for line in lines if line), cited=cited, searched=bool(cited),
                  lists=_answer_lists(candidates))


# Labels an answer lists under a brand ("Pros: ...", "Cons: ..."), never brands.
_GENERIC_LABELS = frozenset(
    "pros cons pricing price features verdict summary note tip tips drawbacks benefits "
    "downsides considerations limitations strengths weaknesses".split()
)


def _answer_lists(candidates: list[tuple[bool, list[ListItem], list[str]]]) -> list[tuple[bool, list[ListItem]]]:
    """An answer's lists that could be the one it gave as an answer, best first.

    AI Mode lays the same kind of answer out differently from one call to the next:
    brands as bullets followed by numbered follow-up questions, or brands as
    numbered paragraphs each followed by a pros-and-cons list. Lists of questions
    and lists of labels are set aside; of the rest, a ranked list comes first, then
    the longest.
    """
    usable = [
        (ranked, items)
        for ranked, items, texts in candidates
        if len(items) >= 2
        and sum("?" in text for text in texts) * 2 < len(texts)
        and sum(item.name.strip(" :").lower() in _GENERIC_LABELS for item in items) * 2 < len(items)
    ]
    return sorted(usable, key=lambda pair: (pair[0], len(pair[1])), reverse=True)


def _ai_mode_item(entry: dict) -> ListItem:
    """One entry of AI Mode's list: its name and, when linked, its page.

    An entry with sub-points carries them twice: nested under `list`, and joined
    onto its own snippet after the name ("OptinMonster Targeting Depth: ..."). The
    name is what comes before the first sub-point.
    """
    link = _dict((_list(entry.get("snippet_links")) or [None])[0])
    snippet = _str(entry.get("snippet")) or ""
    nested = [_str(_dict(sub).get("snippet")) for sub in _list(entry.get("list"))]
    first = next((text for text in nested if text), None)
    if first and first in snippet and snippet.index(first) > 0:
        name = snippet[: snippet.index(first)]
    else:
        name = _str(link.get("text")) or re.split(r"\s+[—–-]\s+|:\s", snippet, maxsplit=1)[0]
    # "OptinMonster: Pros: ..." leaves the name's own colon behind.
    return ListItem(name=_plain(name).strip(" .:;*—–-"), url=_str(link.get("link")))


ADAPTERS = {"chatgpt": from_chatgpt, "gemini": from_gemini, "ai-mode": from_ai_mode}


# --- reading an answer ------------------------------------------------------

_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")
# A parenthesized run of Markdown links: the inline citation marker after a claim.
_CITATION_MARKER = re.compile(r"\s*\((?:\s*\[[^\]]*\]\([^)\s]*\)\s*,?)+\s*\)")
_EMPHASIS = re.compile(r"[*_`]+")
_NUMBERED = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(\d{1,2})[.)]\s+(.*)$")
# A top-level bullet. Indented bullets are sub-points of the one above.
_BULLET = re.compile(r"^[*•-]\s+(.*)$")
_REFUSAL = re.compile(
    r"\b(?:I can(?:not|'t|’t) (?:browse|help|assist|provide|answer)|"
    r"I(?:'m|’m| am) (?:unable|not able) to (?:help|assist|browse|provide|answer)|"
    r"I (?:can(?:not|'t|’t)|won(?:'t|’t)) comply)",
    re.IGNORECASE,
)
_NOT_FOUND = re.compile(
    r"\b(?:(?:I(?:'m|’m| am)|I was) not (?:familiar|aware)|"
    r"(?:could not|couldn(?:'t|’t)|can(?:not|'t|’t)|unable to) find (?:any )?"
    r"(?:information|reliable information|details|a (?:company|brand|product))|"
    r"no (?:reliable )?(?:information|details) (?:is |was )?(?:available )?(?:about|on)|"
    r"(?:is not|isn(?:'t|’t)) a (?:known|widely known|recognized) (?:brand|company|product))",
    re.IGNORECASE,
)
# Labels too short or too common to find a brand by name; its host still finds it.
_LABEL_STOPLIST = frozenset(
    "app get try use my the best top shop store home web site online official go hq join hello".split()
)


def unwrap(url: str) -> str | None:
    """A cited URL without tracking parameters, and Google's redirect unwrapped.

    None for anything that is not an absolute http(s) URL after unwrapping.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.hostname and parts.hostname.endswith("google.com") and parts.path in ("/url", "/goto"):
        target = (parse_qs(parts.query).get("url") or parse_qs(parts.query).get("q") or [""])[0]
        return unwrap(target) if target and target != url else None
    # A single-label host is a truncated reference (AI Mode has returned `https://www`).
    if parts.scheme not in ("http", "https") or "." not in (parts.hostname or ""):
        return None
    query = [(k, v) for k, v in parse_qs(parts.query, keep_blank_values=True).items() if not k.lower().startswith("utm_")]
    flat = urlencode([(k, value) for k, values in query for value in values])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, flat, ""))


def _pages(urls: list[str], site: str | None) -> list[dict]:
    seen: set[str] = set()
    pages: list[dict] = []
    for raw in urls:
        url = unwrap(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        host = host_of(url)
        pages.append({"url": excerpt(url, 280), "host": host, "own": own_host(host, site)})
        if len(pages) == MAX_CITED:
            break
    return pages


def _whole_word(term: str, text: str, ignore_case: bool = True) -> bool:
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![^\W_]){re.escape(term)}(?![^\W_])", text, flags) is not None


def _name_terms(brand: str, site: str | None) -> list[str]:
    """The brand, and its domain label when the site is the registrable domain itself.

    On a hosted subdomain such as `brand.substack.com` the label names the
    platform, not the brand, so it is not used.
    """
    terms = [brand] if brand else []
    if site:
        label = domain_label(site)
        if site.lower().removeprefix("www.").split(".")[0] == label and len(label) >= 4 \
                and label not in _LABEL_STOPLIST:
            terms.append(label)
    return terms


def _plain(text: str) -> str:
    return _EMPHASIS.sub("", _LINK.sub(r"\1", _CITATION_MARKER.sub("", text)))


def read_brand(answer: Answer, engine: str, brand: str, site: str | None) -> dict:
    """The first question: does the engine recognize the brand, and how does it describe it."""
    cited = _pages(answer.cited, site)
    if ENGINES[engine].kind == "query":
        mentioned = any(_whole_word(term, answer.text) for term in _name_terms(brand, site)) or bool(
            site and site.lower() in answer.text.lower()
        )
        first = next((line for line in answer.text.split("\n") if line.strip()), "")
        return {
            "status": "answered",
            "recognized": mentioned and not _NOT_FOUND.search(answer.text),
            "description": excerpt(first, 280) if first else None,
            "cited": cited,
            "searched": answer.searched,
        }
    lines = [_plain(line).strip().lstrip("#-> ").strip() for line in answer.text.split("\n")]

    def label(name: str) -> str | None:
        for line in lines:
            match = re.match(rf"{name}\s*:\s*(.+)$", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    category, offers, competitors = label("CATEGORY"), label("OFFERS"), label("COMPETITORS")
    if not (category or offers or competitors):
        category, offers, competitors = _unlabelled(lines)
    not_found = bool(_NOT_FOUND.search(answer.text))
    if not (category and offers) and not not_found:
        return {"status": "failed", "reason": "refused" if _REFUSAL.search(answer.text) else "unreadable answer"}
    names = [excerpt(name.strip().rstrip(".;:"), 60) for name in re.split(r",|\band\b", competitors or "")]
    return {
        "status": "answered",
        "recognized": bool(category and offers) and not not_found,
        "category": excerpt(category, 60) if category else None,
        "offers": excerpt(offers, 280) if offers else None,
        "competitors": [name for name in names if name][:MAX_COMPETITORS],
        "cited": cited,
        "searched": answer.searched,
    }


def _unlabelled(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """The three asked-for lines when ChatGPT answered in order but dropped the labels.

    Read by position only when the shape leaves no doubt: exactly three lines, a
    short category, then a sentence, then a comma list.
    """
    kept = [line for line in lines if line]
    if len(kept) != 3:
        return None, None, None
    category, offers, competitors = kept
    if len(category.split()) <= 8 and competitors.count(",") >= 2 and len(offers.split()) >= 4:
        return category, offers, competitors
    return None, None, None


def _chat_items(text: str) -> tuple[list[tuple[int, ListItem]], bool] | None:
    """The list in a chat answer and whether it is ranked, or None when there is none.

    Numbered lines are a ranking, and numbering that restarts is unreadable rather
    than read as "not named". Asked for a top ten, Gemini has answered with bullets
    instead: that is a list in the order written, not a stated ranking.
    """
    lines = _CITATION_MARKER.sub("", text).split("\n")
    numbered = [(int(m.group(1)), m.group(2)) for m in map(_NUMBERED.match, lines) if m]
    if numbered:
        if any(number != index + 1 for index, (number, _) in enumerate(numbered)):
            return None
        ranked = True
    else:
        numbered = [(index + 1, m.group(1)) for index, m in enumerate(m for m in map(_BULLET.match, lines) if m)]
        if len(numbered) < 2:
            return None
        ranked = False
    items = []
    for number, line in numbered[:MAX_LISTED]:
        link = _LINK.search(line)
        bold = re.search(r"\*\*([^*]+)\*\*", line)
        if link and link.group(1):
            name, url = link.group(1), link.group(2)
        elif bold:
            name, url = bold.group(1), None
        else:
            name, url = re.split(r"\s+[—–-]\s+|:\s", line, maxsplit=1)[0], None
        items.append((number, ListItem(name=_plain(name).strip(" .:*"), url=url)))
    return items, ranked


def _brands_in_prose(text: str, known: list[str]) -> list[ListItem]:
    """Known brand names an answer mentions, in the order it first mentions them."""
    plain = _plain(text)
    first: dict[str, int] = {}
    for name in known:
        match = re.search(rf"(?<![^\W_]){re.escape(name)}(?![^\W_])", plain, re.IGNORECASE)
        if match and name.lower() not in {seen.lower() for seen in first}:
            first[name] = match.start()
    return [ListItem(name=name, url=None) for name in sorted(first, key=first.get)]


def _search_list(answer: Answer, brand: str, known: list[str]) -> tuple[list[ListItem], bool] | None:
    """AI Mode's list of brands, checked against brands the other engines named.

    AI Mode lays the same answer out differently on every call, and four live runs
    produced four layouts: bullets, numbered paragraphs, "Name: Pros: ..." entries,
    and once only advice headings, with the brands named in a sentence above them.
    A list is taken as the answer only when at least half its entries are brands the
    chat engines named, or linked; otherwise the brands it names in prose are read in
    the order written. Neither means there is no list to read, never "not named".
    """
    vocabulary = [name for name in dict.fromkeys([*known, brand]) if name]

    def is_brand(item: ListItem) -> bool:
        linked = bool(item.url and "google." not in (host_of(unwrap(item.url) or "") or "google."))
        return linked or any(_whole_word(name, item.name) or _whole_word(item.name, name) for name in vocabulary)

    for ranked, items in answer.lists or []:
        if sum(is_brand(item) for item in items) * 2 >= len(items):
            return items, ranked
    in_prose = _brands_in_prose(answer.text, vocabulary)
    return (in_prose, False) if in_prose else None


def read_category(answer: Answer, brand: str, site: str | None, known: list[str] | None = None) -> dict:
    """The second question: is the brand among the best in its category, and where.

    `known` is what the other engines called brands, which a search answer's list is
    checked against; a chat answer's list is its own evidence.
    """
    if answer.lists is not None:
        found_list = _search_list(answer, brand, known or [])
        if found_list is None:
            return {"status": "failed", "reason": "no list of brands in the answer"}
        items, ranked = found_list
        numbered = [(index + 1, item) for index, item in enumerate(items[:MAX_LISTED])]
    else:
        if _REFUSAL.search(answer.text) and not _NUMBERED.search(answer.text):
            return {"status": "failed", "reason": "refused"}
        found_list = _chat_items(answer.text)
        if found_list is None:
            return {"status": "failed", "reason": "unreadable answer"}
        numbered, ranked = found_list
    terms = _name_terms(brand, site)
    listed, seen = [], set()
    for position, item in numbered:
        url = unwrap(item.url) if item.url else None
        host = host_of(url) if url else None
        name = excerpt(item.name, 60)
        key = host or name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        own = own_host(host, site) if host else (False if site else None)
        listed.append({"position": position if ranked else None, "name": name, "host": host, "own": own})
    found = next((item for item in listed if item["own"]), None) or next(
        (item for item in listed if any(_whole_word(term, item["name"]) for term in terms)), None
    )
    listed_names = {item["name"] for item in listed}
    outside = "\n".join(
        line for line in answer.text.split("\n")
        if not _NUMBERED.match(line) and not _BULLET.match(line) and _plain(line).strip() not in listed_names
    )
    return {
        "status": "answered",
        "named": found is not None,
        "position": found["position"] if found else None,
        "ranked": ranked,
        # Outside the list the brand counts only in its written case, so a brand
        # that is also a common word is not found in ordinary prose.
        "named_outside_list": found is None and bool(brand) and _whole_word(brand, _plain(outside), False),
        "listed": listed,
        "cited": _pages(answer.cited, site),
        "searched": answer.searched,
        "search_queries": [excerpt(q, 120) for q in answer.search_queries[:3]],
    }


# --- asking -----------------------------------------------------------------


@dataclass
class Call:
    status: int | None
    payload: dict | None
    credits: int | None
    remaining: int | None
    elapsed_ms: int
    reason: str | None


def _url(path: str, params: dict) -> str:
    return f"{BASE}{path}?{urlencode(params)}"


def _int_header(headers: dict, name: str) -> int | None:
    try:
        return int(headers.get(name, ""))
    except ValueError:
        return None


def _get(path: str, params: dict, timeout: float, allow_private: bool) -> http.FetchResult | str:
    """One vendor request, or the reason it failed. The URL carries the key and is never returned."""
    try:
        return http.fetch(_url(path, params), allow_private=allow_private, timeout=timeout,
                          max_bytes=MAX_BYTES, max_redirects=0, accept_types=None)
    except GeoError as error:
        return error.code


def _call(engine: Engine, question: str, token: str, allow_private: bool) -> Call:
    """One question, retried on a documented transient, uncharged status."""
    params = {"token": token, "q": question, **engine.params}
    started = time.monotonic()
    for attempt in range(len(RETRY_DELAYS) + 1):
        result = _get(engine.path, params, engine.timeout, allow_private)
        elapsed = int((time.monotonic() - started) * 1000)
        if isinstance(result, str):
            return Call(None, None, None, None, elapsed, result)
        if result.status in RETRYABLE and attempt < len(RETRY_DELAYS):
            time.sleep(RETRY_DELAYS[attempt])
            continue
        remaining = _int_header(result.headers, "scrape.do-remaining-credits")
        if not result.ok:
            return Call(result.status, None, 0, remaining, elapsed, f"HTTP {result.status}")
        credits = _int_header(result.headers, "scrape.do-request-cost")
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError:
            return Call(result.status, None, credits, remaining, elapsed, "not JSON")
        if not isinstance(payload, dict):
            return Call(result.status, None, credits, remaining, elapsed, "not JSON")
        return Call(result.status, payload, credits, remaining, elapsed, None)
    raise AssertionError("unreachable")


def check_key(token: str, needed: int, allow_private: bool) -> str | None:
    """Why nothing should be asked, or None to go ahead. `/info` is free.

    A rejected key or an account without the credits for this run stops the run
    before anything is spent. A rate-limited or unreachable `/info` does not: the
    questions themselves will fail cleanly if the key is bad.
    """
    result = _get("/info", {"token": token}, INFO_TIMEOUT, allow_private)
    if isinstance(result, str):
        return None
    if result.status in (401, 403):
        return f"scrape.do did not accept the key in {TOKEN_ENV}"
    if not result.ok:
        return None
    try:
        info = json.loads(result.body)
    except json.JSONDecodeError:
        return None
    if not isinstance(info, dict):
        return None
    if info.get("IsActive") is False:
        return "the scrape.do account behind this key is not active"
    remaining = info.get("RemainingMonthlyRequest")
    if isinstance(remaining, int) and remaining < needed:
        return f"the scrape.do account has {remaining} credits left and this run needs up to {needed}"
    return None


def _probe(engine: Engine, question: str, token: str, allow_private: bool) -> tuple[dict, Answer | None, Call]:
    observed = envelope.now_iso()
    call = _call(engine, question, token, allow_private)
    base = {"question": excerpt(question, 280), "observed_at": observed, "http_status": call.status,
            "credits": call.credits, "elapsed_ms": call.elapsed_ms}
    if call.reason:
        return {**base, "status": "failed", "reason": call.reason}, None, call
    answer = ADAPTERS[engine.id](call.payload or {})
    if answer is None:
        return {**base, "status": "failed", "reason": "unreadable answer"}, None, call
    if answer.empty:
        # Documented as not charged: Google simply showed no AI Mode answer.
        return {**base, "status": "empty", "credits": call.credits or 0}, answer, call
    return base, answer, call


def not_asked(requested: list[str], brand: str, site: str | None, reason: str) -> dict:
    return {
        "asked": False,
        "reason": reason,
        "provider": PROVIDER,
        "requested": requested,
        "brand": brand,
        "site": site,
        "engines": [],
    }


def ask(brand: str, site_url: str | None, requested: list[str], *, allow_private: bool = False,
        say=None) -> dict:
    """Ask each requested engine both questions and record what came back.

    The only entry point that touches the network. Everything it returns is safe
    to print and to store: capped, escaped, and free of the key.
    """
    site = host_of(site_url) if site_url else None
    name = sanitize_brand(brand, site)
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return not_asked(requested, name, site, f"no API key: set {TOKEN_ENV} to ask AI assistants")
    needed = max_credits(requested)
    refusal = check_key(token, needed, allow_private)
    if refusal:
        return not_asked(requested, name, site, refusal)
    if say:
        labels = [ENGINES[engine].label for engine in requested]
        say(", ".join(labels[:-1]) + (" and " if len(labels) > 1 else "") + labels[-1], needed)

    engines = {engine: ENGINES[engine] for engine in requested}
    results: dict[str, dict] = {
        engine: {"engine": engine, "label": spec.label, "model": None} for engine, spec in engines.items()
    }
    calls: list[Call] = []

    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        first = {
            engine: pool.submit(_probe, spec, brand_question(engine, name, site), token, allow_private)
            for engine, spec in engines.items()
        }
        for engine, future in first.items():
            record, answer, call = future.result()
            calls.append(call)
            if answer is not None and record.get("status") != "empty":
                record.update(read_brand(answer, engine, name, site))
                results[engine]["model"] = excerpt(answer.model, 40) if answer.model else None
            results[engine]["brand_question"] = record

        category, source = None, None
        for engine in CATEGORY_SOURCES:
            raw = (results.get(engine, {}).get("brand_question") or {}).get("category")
            category = sanitize_category(raw, name, site) if raw else None
            if category:
                source = engine
                break

        if category:
            second = {
                engine: pool.submit(_probe, spec, category_question(engine, category), token, allow_private)
                for engine, spec in engines.items()
            }
            answered = {engine: future.result() for engine, future in second.items()}
            # Chat engines first: what they call brands is what a search answer's list
            # is checked against.
            known = [
                competitor
                for entry in results.values()
                for competitor in (entry.get("brand_question") or {}).get("competitors") or []
            ]
            for engine in sorted(answered, key=lambda engine: ENGINES[engine].kind == "query"):
                record, answer, call = answered[engine]
                calls.append(call)
                if answer is not None and record.get("status") != "empty":
                    record.update(read_category(answer, name, site, known))
                    results[engine]["model"] = results[engine]["model"] or (
                        excerpt(answer.model, 40) if answer.model else None
                    )
                    known += [item["name"] for item in record.get("listed") or []]
                results[engine]["category_question"] = record
        else:
            why = "no engine named a category to ask about"
            if not any(engine in engines for engine in CATEGORY_SOURCES):
                why = "only ChatGPT and Gemini name a category, and neither was asked"
            for engine in engines:
                results[engine]["category_question"] = {"status": "skipped", "reason": why}

    known = [call.credits for call in calls if call.credits is not None]
    remaining = [call.remaining for call in calls if call.remaining is not None]
    return {
        "asked": True,
        "reason": None,
        "provider": PROVIDER,
        "locale": LOCALE,
        "requested": requested,
        "brand": name,
        "site": site,
        "category": category,
        "category_source": source,
        # Summed from scrape.do's own cost header; null when it sent none.
        "credits_used": sum(known) if known else None,
        "credits_remaining": min(remaining) if remaining else None,
        "engines": list(results.values()),
    }


# --- saying what came back --------------------------------------------------


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _in_sentence(phrase: str) -> str:
    """An engine's "Popup builder software" read mid-sentence; "SEO tools" keeps its acronym."""
    return phrase if phrase[:2].isupper() else phrase[:1].lower() + phrase[1:]


def _names(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def describe(entry: dict, brand: str) -> tuple[str, str]:
    """One sentence per question, for the terminal and the report alike.

    The engine speaks of the brand by name, never "you": reports are run on
    competitors and handed to clients.
    """
    first = entry.get("brand_question") or {}
    if first.get("status") == "failed":
        about = f"did not answer the question about {brand} ({first.get('reason')})."
    elif first.get("status") == "empty":
        about = f"showed no answer about {brand}."
    elif first.get("recognized"):
        about = (f"describes {brand} as {_in_sentence(first['category'])}." if first.get("category")
                 else f"recognizes {brand}.")
    else:
        about = f"does not recognize {brand}."

    second = entry.get("category_question") or {}
    status = second.get("status")
    if status == "skipped":
        ranking = f"was not asked for the best in its category: {second.get('reason')}."
    elif status == "failed":
        ranking = f"did not answer the category question ({second.get('reason')})."
    elif status == "empty":
        ranking = "showed no AI Mode answer for the category question."
    elif second.get("named"):
        listed = len(second.get("listed") or [])
        ranking = (f"named {brand} {_ordinal(second['position'])} of {listed}." if second.get("position")
                   else f"listed {brand} among {listed}, unranked.")
    elif second.get("named_outside_list"):
        ranking = f"mentioned {brand} but did not list it."
    else:
        others = [item["name"] for item in (second.get("listed") or [])[:3]]
        ranking = f"did not name {brand}" + (f"; it named {_names(others)}." if others else ".")
    return about, ranking


__all__ = [
    "ENGINES",
    "describe",
    "TOKEN_ENV",
    "ask",
    "brand_question",
    "category_question",
    "domain_label",
    "max_credits",
    "not_asked",
    "parse_engines",
    "read_brand",
    "read_category",
    "sanitize_brand",
    "sanitize_category",
]
