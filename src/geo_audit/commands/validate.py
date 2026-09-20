"""`geo validate` - what the structured data on a page actually says.

Reports per node rather than per page, because "three blocks, two problems" is
not actionable and "the Article node has no author" is. Required and
recommended properties come from `data/schema_requirements.json`, so correcting
one is a data change.

`--suggest` emits JSON-LD built from what the page already states - its title,
byline, dates and canonical - rather than a blank template. A skeleton someone
has to fill in by hand is a skeleton that ships with `"name": "TODO"` in it.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from geo_audit import data, envelope
from geo_audit.commands.common import Options, evidence_block, load_page, page_block
from geo_audit.lib.slug import host_of
from geo_audit.scoring import schema_org
from geo_audit.scoring.model import composite, findings_for, prioritize


def _node_report(node: dict, type_name: str, spec: dict) -> dict:
    missing_required = [prop for prop in spec["required"] if prop not in node]
    missing_recommended = [prop for prop in spec["recommended"] if prop not in node]
    return {
        "type": type_name,
        "properties": sorted(key for key in node if not key.startswith("@")),
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "valid": not missing_required,
    }


def validate_document(doc) -> dict:
    requirements = data.load("schema_requirements")["types"]
    nodes: list[dict] = []
    for type_name, spec in requirements.items():
        for node in schema_org._nodes_of(doc, {type_name}):
            nodes.append(_node_report(node, type_name, spec))

    known = set(requirements)
    declared = schema_org.types_in(doc)
    attempted = len(doc.jsonld) + len(doc.jsonld_errors)
    if not attempted:
        verdict = "absent"
    elif doc.jsonld_errors or not all(node["valid"] for node in nodes):
        verdict = "invalid"
    else:
        verdict = "valid"
    return {
        "blocks": len(doc.jsonld),
        "blocks_attempted": attempted,
        "types": sorted(declared),
        "unrecognised_types": sorted(declared - known),
        "parse_errors": doc.jsonld_errors,
        "nodes": nodes,
        "verdict": verdict,
        # Absent is not valid: there was nothing to be valid about.
        "valid": verdict == "valid",
    }


def suggest(doc, url: str) -> dict:
    """A JSON-LD block built from what the page already claims."""
    host = host_of(url)
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    declared = schema_org.types_in(doc)

    graph: list[dict] = []
    if not (declared & {"Organization", "LocalBusiness", "Person", "NewsMediaOrganization"}):
        graph.append(
            {
                "@type": "Organization",
                "@id": f"{origin}/#organization",
                "name": host,
                "url": origin,
                "description": doc.meta.get("description") or "",
                "sameAs": [],
            }
        )

    article_types = set(data.load("schema_requirements")["article_types"])
    if not (declared & article_types) and doc.title:
        article = {
            "@type": "Article",
            "headline": doc.title,
            "url": doc.meta.get("canonical") or url,
            "publisher": {"@id": f"{origin}/#organization"},
        }
        author = doc.meta.get("author")
        if author:
            article["author"] = {"@type": "Person", "name": author}
        published = doc.meta.get("article:published_time")
        modified = doc.meta.get("article:modified_time")
        if published:
            article["datePublished"] = published
        if modified:
            article["dateModified"] = modified
        description = doc.meta.get("description")
        if description:
            article["description"] = description
        graph.append(article)

    if not graph:
        return {"needed": False, "note": "The page already declares a publisher and an article."}

    payload = {"@context": "https://schema.org", "@graph": graph}
    blanks = sorted(
        f"{node['@type']}.{key}"
        for node in graph
        for key, value in node.items()
        if value in ("", [], {})
    )
    return {
        "needed": True,
        "jsonld": payload,
        "script": (
            '<script type="application/ld+json">\n'
            + json.dumps(payload, indent=2, ensure_ascii=False)
            + "\n</script>"
        ),
        "fill_in": blanks,
    }


def run(args, run_id: str) -> dict:
    options = Options(
        allow_private=args.allow_private,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        check_robots=not args.no_robots,
    )
    page = load_page(args.url, options)
    block = page_block(page)
    evidence = evidence_block(page)

    if page.doc is None:
        return envelope.build(
            "validate",
            ok=True,
            run_id=run_id,
            evidence=evidence,
            scores=None,
            findings=[f.to_dict() for f in prioritize(page.findings)],
            extra={"page": block, "schema": None},
        )

    signals = schema_org.score(page)
    score, completeness = composite(signals)
    tier = data.tier_for(score)
    findings = prioritize(findings_for(signals, block["final_url"]) + page.findings)

    report = validate_document(page.doc)
    if getattr(args, "suggest", False):
        report["suggestion"] = suggest(page.doc, block["final_url"])

    return envelope.build(
        "validate",
        ok=True,
        run_id=run_id,
        evidence=evidence,
        completeness=completeness,
        scores={
            "composite": score,
            "tier": tier["label"],
            "tier_meaning": tier["meaning"],
            "categories": {"schema": score},
        },
        signals=[signal.to_dict() for signal in signals],
        findings=[finding.to_dict() for finding in findings],
        extra={"page": block, "schema": report},
    )
