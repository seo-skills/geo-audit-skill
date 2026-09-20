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

from jinja2 import ChoiceLoader, DictLoader, Environment, FunctionLoader, StrictUndefined, select_autoescape

from geo_audit.report.context import ClientContext, OperatorContext

CLIENT_TEMPLATE = "report.html.j2"
OPERATOR_TEMPLATE = "report-operator.html.j2"


def _asset(name: str) -> str:
    return resources.files("geo_audit.assets").joinpath(name).read_text(encoding="utf-8")


def _environment() -> Environment:
    return Environment(
        loader=FunctionLoader(lambda name: _asset(name)),
        autoescape=select_autoescape(default=True, default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _stylesheet(client: ClientContext) -> str:
    """The stylesheet carries brand tokens, so it is a template too.

    Rendered with autoescape off: CSS is not HTML, and escaping a hex colour
    into `&#35;` would break every rule. The values substituted here are hex
    colours validated by `brand.load`, never free text.
    """
    css = Environment(autoescape=False, undefined=StrictUndefined).from_string(_asset("report.css"))
    return css.render(client=client)


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
