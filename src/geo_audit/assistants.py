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
RETRY_AFTER = 2.0
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
    # AI Mode sends its list as structure; the chat engines as Markdown in `text`.
    items: list[ListItem] | None = None
    ranked: bool = True
    empty: bool = False


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _str(value) -> str | None:
    return value if isinstance(value, str) else None


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
    items: list[ListItem] | None = None
    ranked = True
    for block in blocks:
        kind = block.get("type")
        if kind in ("list", "ordered_list"):
            entries = [_dict(entry) for entry in _list(block.get("list"))]
            for entry in entries:
                lines.append(_str(entry.get("snippet")) or "")
            if items is None and entries:
                ranked = kind == "ordered_list"
                items = []
                for entry in entries:
                    link = _dict((_list(entry.get("snippet_links")) or [None])[0])
                    snippet = _str(entry.get("snippet")) or ""
                    name = _str(link.get("text")) or re.split(r"\s+[—–-]\s+|:\s", snippet, maxsplit=1)[0]
                    items.append(ListItem(name=name, url=_str(link.get("link"))))
        else:
            lines.append(_str(block.get("snippet")) or "")
    return Answer(text="\n".join(line for line in lines if line), cited=cited, searched=bool(cited),
                  items=items, ranked=ranked)


ADAPTERS = {"chatgpt": from_chatgpt, "gemini": from_gemini, "ai-mode": from_ai_mode}


# --- reading an answer ------------------------------------------------------

_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")
# A parenthesized run of Markdown links: the inline citation marker after a claim.
_CITATION_MARKER = re.compile(r"\s*\((?:\s*\[[^\]]*\]\([^)\s]*\)\s*,?)+\s*\)")
_EMPHASIS = re.compile(r"[*_`]+")
_NUMBERED = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(\d{1,2})[.)]\s+(.*)$")
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


def _chat_items(text: str) -> list[tuple[int, ListItem]] | None:
    """The numbered lines of a chat answer, or None when there are none or they restart."""
    numbered = []
    for line in _CITATION_MARKER.sub("", text).split("\n"):
        match = _NUMBERED.match(line)
        if match:
            numbered.append((int(match.group(1)), match.group(2)))
    if not numbered or any(number != index + 1 for index, (number, _) in enumerate(numbered)):
        return None
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
    return items


def read_category(answer: Answer, brand: str, site: str | None) -> dict:
    """The second question: is the brand among the best in its category, and where."""
    if answer.items is not None:
        numbered = [(index + 1, item) for index, item in enumerate(answer.items[:MAX_LISTED])]
        ranked = answer.ranked
    else:
        if _REFUSAL.search(answer.text) and not _NUMBERED.search(answer.text):
            return {"status": "failed", "reason": "refused"}
        numbered = _chat_items(answer.text)
        if numbered is None:
            return {"status": "failed", "reason": "unreadable answer"}
        ranked = True
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
        if not _NUMBERED.match(line) and _plain(line).strip() not in listed_names
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
    """One question, retried once on a documented transient status."""
    params = {"token": token, "q": question, **engine.params}
    started = time.monotonic()
    for attempt in range(2):
        result = _get(engine.path, params, engine.timeout, allow_private)
        elapsed = int((time.monotonic() - started) * 1000)
        if isinstance(result, str):
            return Call(None, None, None, None, elapsed, result)
        if result.status in RETRYABLE and attempt == 0:
            time.sleep(RETRY_AFTER)
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
            for engine, future in second.items():
                record, answer, call = future.result()
                calls.append(call)
                if answer is not None and record.get("status") != "empty":
                    record.update(read_category(answer, name, site))
                    results[engine]["model"] = results[engine]["model"] or (
                        excerpt(answer.model, 40) if answer.model else None
                    )
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
