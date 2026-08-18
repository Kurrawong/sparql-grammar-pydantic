"""Conversion between rdflib terms and grammar terms.

Requires the ``rdflib`` extra::

    pip install sparql-grammar[rdflib]

rdflib is imported lazily and only from this module, so the core library keeps zero
runtime dependencies. Consumers that build queries from RDF graphs were writing this
mapping by hand, usually more than once in the same codebase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import Node
from .terminals import ANON, BLANK_NODE_LABEL, DECIMAL, DOUBLE, INTEGER
from .terms import IRI, BooleanLiteral, RDFLiteral, Var

if TYPE_CHECKING:  # pragma: no cover
    from rdflib.term import Identifier

__all__ = ["to_grammar_term", "from_grammar_term", "prologue_from_namespaces"]

_XSD = "http://www.w3.org/2001/XMLSchema#"
_INTEGER_TYPES = frozenset(
    f"{_XSD}{name}"
    for name in (
        "integer", "int", "long", "short", "byte",
        "nonNegativeInteger", "positiveInteger",
        "nonPositiveInteger", "negativeInteger",
        "unsignedInt", "unsignedLong", "unsignedShort", "unsignedByte",
    )
)
_DECIMAL_TYPES = frozenset({f"{_XSD}decimal"})
_DOUBLE_TYPES = frozenset({f"{_XSD}double", f"{_XSD}float"})


def _rdflib():
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "rdflib term conversion needs the rdflib extra: "
            "pip install sparql-grammar[rdflib]"
        ) from exc
    return rdflib


def to_grammar_term(value: Any, *, typed_numerics: bool = True) -> Node:
    """Convert an rdflib term (or plain Python value) into a grammar term.

    ``URIRef`` becomes ``IRI``, ``Variable`` becomes ``Var``, ``BNode`` becomes
    ``BLANK_NODE_LABEL``, and ``Literal`` becomes ``BooleanLiteral``, a numeric
    terminal, or ``RDFLiteral`` carrying its language or datatype.

    With ``typed_numerics=False``, numeric literals keep their explicit
    ``"1"^^xsd:integer`` form instead of being written as bare numbers.
    """
    rdflib = _rdflib()

    if isinstance(value, Node):
        return value
    if isinstance(value, rdflib.URIRef):
        return IRI(str(value))
    if isinstance(value, rdflib.Variable):
        return Var(str(value))
    if isinstance(value, rdflib.BNode):
        return BLANK_NODE_LABEL(str(value))
    if isinstance(value, rdflib.Literal):
        return _literal_to_grammar(value, typed_numerics)
    if isinstance(value, bool):
        return BooleanLiteral(value)
    if isinstance(value, int):
        return INTEGER(str(value))
    if isinstance(value, float):
        return DOUBLE(repr(value)) if "e" in repr(value).lower() else DECIMAL(repr(value))
    if isinstance(value, str):
        return RDFLiteral(value)
    raise TypeError(f"cannot convert {type(value).__name__} to a grammar term")


def _literal_to_grammar(value: Any, typed_numerics: bool) -> Node:
    datatype = str(value.datatype) if value.datatype else None

    if datatype == f"{_XSD}boolean":
        return BooleanLiteral(bool(value))
    if typed_numerics and datatype is not None:
        text = str(value)
        if datatype in _INTEGER_TYPES:
            return INTEGER(text)
        if datatype in _DECIMAL_TYPES:
            return DECIMAL(text if "." in text else f"{text}.0")
        if datatype in _DOUBLE_TYPES:
            return DOUBLE(text if "e" in text.lower() else f"{text}e0")

    if value.language:
        return RDFLiteral.langed(str(value), _language_with_direction(value))
    if datatype is not None:
        return RDFLiteral.typed(_escaped(str(value)), IRI(datatype))
    return RDFLiteral(_escaped(str(value)))


def _language_with_direction(value: Any) -> str:
    """Carry an RDF 1.2 base direction through to SPARQL 1.2 LANG_DIR when present."""
    direction = getattr(value, "direction", None)
    return f"{value.language}--{direction}" if direction else str(value.language)


def _escaped(text: str) -> str:
    """Escape what a double-quoted SPARQL string literal cannot hold verbatim."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def from_grammar_term(node: Node) -> Identifier:
    """Convert a grammar term back into an rdflib term.

    Raises ``TypeError`` for nodes that have no rdflib equivalent, such as ``ANON``.
    """
    rdflib = _rdflib()

    if isinstance(node, IRI):
        return rdflib.URIRef(node.value)
    if isinstance(node, Var):
        return rdflib.Variable(node.value)
    if isinstance(node, BLANK_NODE_LABEL):
        return rdflib.BNode(node.value)
    if isinstance(node, BooleanLiteral):
        return rdflib.Literal(node.value)
    if isinstance(node, INTEGER):
        return rdflib.Literal(int(node.value))
    if isinstance(node, (DECIMAL, DOUBLE)):
        return rdflib.Literal(float(node.value))
    if isinstance(node, RDFLiteral):
        return _rdf_literal_from_grammar(node, rdflib)
    if isinstance(node, ANON):
        raise TypeError("ANON has no rdflib equivalent; use a labelled blank node")
    raise TypeError(f"cannot convert {type(node).__name__} to an rdflib term")


def _rdf_literal_from_grammar(node: RDFLiteral, rdflib: Any) -> Any:
    text = node.value if isinstance(node.value, str) else node.value.value
    if node.lang_dir is not None:
        language = node.lang_dir.value
        base, _, direction = language.partition("--")
        if direction:
            try:
                return rdflib.Literal(text, lang=base, direction=direction)
            except TypeError:  # rdflib without RDF 1.2 direction support
                return rdflib.Literal(text, lang=base)
        return rdflib.Literal(text, lang=base)
    if node.datatype is not None:
        return rdflib.Literal(text, datatype=rdflib.URIRef(node.datatype.value))
    return rdflib.Literal(text)


def prologue_from_namespaces(namespace_manager: Any) -> Node:
    """Build a ``Prologue`` from an rdflib graph's namespace bindings.

    Pass ``graph.namespace_manager``. Only bound prefixes are emitted.
    """
    from .grammar import Prologue

    return Prologue.from_prefixes(
        {prefix: str(namespace) for prefix, namespace in namespace_manager.namespaces()}
    )
