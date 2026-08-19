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
from .terminals import (
    ANON,
    BLANK_NODE_LABEL,
    DECIMAL,
    DECIMAL_NEGATIVE,
    DECIMAL_POSITIVE,
    DOUBLE,
    DOUBLE_NEGATIVE,
    DOUBLE_POSITIVE,
    INTEGER,
    INTEGER_NEGATIVE,
    INTEGER_POSITIVE,
)
from .terms import IRI, BooleanLiteral, RDFLiteral, Var, numeric_literal

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
    if isinstance(value, (int, float)):
        return numeric_literal(value)
    if isinstance(value, str):
        # A Python str converts to a literal, exactly as ``rdflib.Literal("x")`` does -
        # it is never read as an IRI. Pass ``rdflib.URIRef`` for that. This is a value
        # converter, so the Python type decides and nothing is read out of the text.
        return RDFLiteral(value)
    raise TypeError(f"cannot convert {type(value).__name__} to a grammar term")


def _literal_to_grammar(value: Any, typed_numerics: bool) -> Node:
    datatype = str(value.datatype) if value.datatype else None

    if datatype == f"{_XSD}boolean":
        return BooleanLiteral(bool(value))
    if typed_numerics and datatype is not None:
        text = str(value)
        if datatype in _INTEGER_TYPES:
            return _numeric_terminal("integer", text)
        if datatype in _DECIMAL_TYPES:
            return _numeric_terminal("decimal", text if "." in text else f"{text}.0")
        if datatype in _DOUBLE_TYPES:
            return _numeric_terminal("double", text if "e" in text.lower() else f"{text}e0")

    if value.language:
        return RDFLiteral.langed(str(value), _language_with_direction(value))
    if datatype is not None:
        return RDFLiteral.typed(str(value), IRI(datatype))
    # not escaped here: RDFLiteral escapes plain text when it renders, and doing it
    # in both places would double every backslash
    return RDFLiteral(str(value))


#: The three numeric families, each as (unsigned, positive, negative).
_NUMERIC_CLASSES = {
    "integer": (INTEGER, INTEGER_POSITIVE, INTEGER_NEGATIVE),
    "decimal": (DECIMAL, DECIMAL_POSITIVE, DECIMAL_NEGATIVE),
    "double": (DOUBLE, DOUBLE_POSITIVE, DOUBLE_NEGATIVE),
}

#: Numeric terminals grouped for the reverse direction: an integer becomes a Python
#: int, the rest a float.
_INTEGER_TERMINALS = _NUMERIC_CLASSES["integer"]
_NUMERIC_TERMINALS = tuple(c for family in _NUMERIC_CLASSES.values() for c in family)


def _numeric_terminal(kind: str, text: str) -> Node:
    """A numeric terminal from signed text.

    ``INTEGER`` and friends are unsigned in the grammar; the sign lives in the
    ``*_POSITIVE``/``*_NEGATIVE`` productions, which hold the unsigned digits and
    render the sign. Handing ``"-5"`` to ``INTEGER`` would build a node that renders
    correctly but fails ``validate("terminals")``.
    """
    plain, positive, negative = _NUMERIC_CLASSES[kind]
    if text.startswith("-"):
        return negative(text[1:])
    if text.startswith("+"):
        return positive(text[1:])
    return plain(text)


def _language_with_direction(value: Any) -> str:
    """Carry an RDF 1.2 base direction through to SPARQL 1.2 LANG_DIR when present."""
    direction = getattr(value, "direction", None)
    return f"{value.language}--{direction}" if direction else str(value.language)


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
    if isinstance(node, _INTEGER_TERMINALS):
        # to_string() carries the sign, which node.value deliberately does not
        return rdflib.Literal(int(node.to_string()))
    if isinstance(node, _NUMERIC_TERMINALS):
        return rdflib.Literal(float(node.to_string()))
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
