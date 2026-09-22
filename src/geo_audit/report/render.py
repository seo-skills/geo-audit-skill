"""Rendering. One pipeline, two entry points that cannot be confused.

`render_client` builds a namespace containing only the client context. The
operator template is the only one that names `operator`, and it is never
reachable from the client entry point. With `StrictUndefined`, a field that
drifts out of the context is a render error rather than a blank in a delivered
report.

Autoescape is on and asserted by a test that renders a site whose title is
`<script>`. The report is a document someone forwards; it must not execute
anything from a page it audited.
"""

from __future__ import annotations

from importlib import resources
from urllib.parse import urlsplit

from jinja2 import ChoiceLoader, DictLoader, Environment, FunctionLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from geo_audit.report.context import ClientContext, OperatorContext

CLIENT_TEMPLATE = "report.html.j2"
OPERATOR_TEMPLATE = "report-operator.html.j2"


def _asset(name: str) -> str:
    return resources.files("geo_audit.assets").joinpath(name).read_text(encoding="utf-8")


def page_path(url: str, site: str) -> str:
    """A page as a reader scans it: its path when it is on the audited site.

    The site is already in the masthead, and repeating it on every page of every
    finding buried the part that differs. A page elsewhere keeps its host.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    if host == (site or "").removeprefix("www."):
        return path
    return f"{host}{path}"


def _environment() -> Environment:
    environment = Environment(
        loader=FunctionLoader(lambda name: _asset(name)),
        autoescape=select_autoescape(default=True, default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    environment.filters["page_path"] = page_path
    return environment


def _stylesheet(client: ClientContext) -> Markup:
    """The stylesheet carries brand tokens, so it is a template too.

    Rendered with autoescape off: CSS is not HTML, and escaping a hex colour
    into `&#35;` would break every rule. The values substituted here are hex
    colours validated by `brand.load`, never free text.

    It enters the page as trusted markup for the same reason: a browser decodes
    no entities inside <style>, so the page template escaping it cost every
    rule with a quote or a `>` - the font and the bar fills among them. The
    trust holds only while nothing in it can end the element, so that is
    checked rather than assumed.
    """
    css = Environment(autoescape=False, undefined=StrictUndefined).from_string(_asset("report.css"))
    rendered = css.render(client=client)
    if "</" in rendered:
        raise ValueError("the stylesheet contains '</', which could end its <style> element")
    return Markup(rendered)


def render_client(client: ClientContext) -> str:
    """The delivered report. The namespace has no `operator` key at all."""
    template = _environment().get_template(CLIENT_TEMPLATE)
    return template.render(client=client, stylesheet=_stylesheet(client))


def render_operator(client: ClientContext, operator: OperatorContext) -> str:
    """The agency copy: the client report plus a provenance section."""
    template = _environment().get_template(OPERATOR_TEMPLATE)
    return template.render(
        client=client, operator=operator, stylesheet=_stylesheet(client)
    )
