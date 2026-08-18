"""RDF term productions: variables, IRIs, literals, blank nodes.

Two shaping decisions worth knowing, both aimed at cutting nesting depth:

* Productions that are a bare alternation (``Var ::= VAR1 | VAR2``,
  ``VarOrTerm ::= Var | iri | ...``) are union *aliases*, not wrapper classes, so a
  term goes straight where the grammar allows a term. SPARQL 1.2 helps here too:
  it removed ``GraphTerm``, so ``VarOrTerm`` now holds terms directly.
* ``Var`` and ``IRI`` carry their text directly instead of boxing a terminal node.
  ``Var ::= VAR1 | VAR2`` differs only by sigil, and ``iri ::= IRIREF | PrefixedName``
  splits by surface form, so one node with a sigil does the same work as two nodes.
  ``VAR1``/``VAR2``/``IRIREF`` remain available for exact-fidelity round-tripping.
"""

from __future__ import annotations

from typing import ClassVar, Union

from ._base import Add, Node, alias, production
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
    IRIREF,
    LANG_DIR,
    NIL,
    PNAME_LN,
    PNAME_NS,
    STRING_LITERAL1,
    STRING_LITERAL2,
    STRING_LITERAL_LONG1,
    STRING_LITERAL_LONG2,
    VAR1,
    VAR2,
)

__all__ = [
    "Var",
    "IRI",
    "PrefixedName",
    "String",
    "RDFLiteral",
    "NumericLiteral",
    "NumericLiteralUnsigned",
    "NumericLiteralPositive",
    "NumericLiteralNegative",
    "BooleanLiteral",
    "BlankNode",
    "VarOrIri",
    "VarOrTerm",
]


@production(rule="Var")
class Var(Node):
    """Var ::= VAR1 | VAR2

    ``sigil`` selects the surface form: ``?name`` (default) or ``$name``.
    """

    value: str
    sigil: str = "?"

    def render(self, add: Add) -> None:
        add(self.sigil)
        add(self.value)

    @classmethod
    def from_string(cls, text: str) -> Var:
        """Accept ``?name``, ``$name`` or a bare name."""
        text = text.strip()
        if text[:1] in ("?", "$"):
            return cls(text[1:], text[0])
        return cls(text)

    @classmethod
    def from_terminal(cls, term: VAR1 | VAR2) -> Var:
        return cls(term.value, "?" if isinstance(term, VAR1) else "$")

    def to_terminal(self) -> VAR1 | VAR2:
        return VAR1(self.value) if self.sigil == "?" else VAR2(self.value)


@production(rule="iri")
class IRI(Node):
    """iri ::= IRIREF | PrefixedName

    Holds a full IRI and renders it in angle brackets. For the prefixed form use
    ``PNAME_LN``/``PNAME_NS`` directly, or :meth:`prefixed`.
    """

    value: str

    def render(self, add: Add) -> None:
        add("<")
        add(self.value)
        add(">")

    @classmethod
    def from_string(cls, text: str) -> IRI:
        text = text.strip()
        if text.startswith("<") and text.endswith(">"):
            text = text[1:-1]
        return cls(text)

    @staticmethod
    def prefixed(prefix: str, local: str = "") -> PNAME_LN | PNAME_NS:
        """``IRI.prefixed("skos", "prefLabel")`` -> ``skos:prefLabel``."""
        return PNAME_LN.from_parts(prefix, local) if local else PNAME_NS(prefix)

    def to_terminal(self) -> IRIREF:
        return IRIREF(self.value)


#: PrefixedName ::= PNAME_LN | PNAME_NS
PrefixedName = alias("PrefixedName", Union[PNAME_LN, PNAME_NS])

#: String ::= STRING_LITERAL1 | STRING_LITERAL2 | STRING_LITERAL_LONG1 | STRING_LITERAL_LONG2
String = alias(
    "String",
    Union[
        STRING_LITERAL1,
        STRING_LITERAL2,
        STRING_LITERAL_LONG1,
        STRING_LITERAL_LONG2,
    ],
)

#: NumericLiteralUnsigned ::= INTEGER | DECIMAL | DOUBLE
NumericLiteralUnsigned = alias(
    "NumericLiteralUnsigned", Union[INTEGER, DECIMAL, DOUBLE]
)

#: NumericLiteralPositive ::= INTEGER_POSITIVE | DECIMAL_POSITIVE | DOUBLE_POSITIVE
NumericLiteralPositive = alias(
    "NumericLiteralPositive",
    Union[INTEGER_POSITIVE, DECIMAL_POSITIVE, DOUBLE_POSITIVE],
)

#: NumericLiteralNegative ::= INTEGER_NEGATIVE | DECIMAL_NEGATIVE | DOUBLE_NEGATIVE
NumericLiteralNegative = alias(
    "NumericLiteralNegative",
    Union[INTEGER_NEGATIVE, DECIMAL_NEGATIVE, DOUBLE_NEGATIVE],
)

#: NumericLiteral ::= NumericLiteralUnsigned | NumericLiteralPositive | NumericLiteralNegative
NumericLiteral = alias(
    "NumericLiteral",
    Union[NumericLiteralUnsigned, NumericLiteralPositive, NumericLiteralNegative],
)

#: BlankNode ::= BLANK_NODE_LABEL | ANON
BlankNode = alias("BlankNode", Union[BLANK_NODE_LABEL, ANON])


@production(rule="RDFLiteral")
class RDFLiteral(Node):
    """RDFLiteral ::= String ( LANG_DIR | '^^' iri )?

    ``value`` may be given as a plain ``str`` for convenience, in which case it is
    rendered as a double-quoted string literal.
    """

    value: object
    lang_dir: LANG_DIR | None = None
    datatype: object = None

    def render(self, add: Add) -> None:
        value = self.value
        if isinstance(value, str):
            add('"')
            add(value)
            add('"')
        else:
            value.render(add)
        if self.lang_dir is not None:
            self.lang_dir.render(add)
        elif self.datatype is not None:
            add("^^")
            self.datatype.render(add)

    @classmethod
    def langed(cls, text: str, lang: str) -> RDFLiteral:
        """``RDFLiteral.langed("hello", "en")`` -> ``"hello"@en``."""
        return cls(text, lang_dir=LANG_DIR.from_string(lang))

    @classmethod
    def typed(cls, text: str, datatype: str | IRI) -> RDFLiteral:
        """``RDFLiteral.typed("1", xsd_integer)`` -> ``"1"^^<...>``."""
        dt = IRI.from_string(datatype) if isinstance(datatype, str) else datatype
        return cls(text, datatype=dt)


@production(rule="BooleanLiteral")
class BooleanLiteral(Node):
    """BooleanLiteral ::= 'true' | 'false'"""

    value: bool

    def render(self, add: Add) -> None:
        add("true" if self.value else "false")


#: VarOrIri ::= Var | iri
VarOrIri = alias("VarOrIri", Union[Var, IRI, PNAME_LN, PNAME_NS])

#: VarOrTerm ::= Var | iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | NIL | TripleTerm
#:
#: SPARQL 1.2 dropped the ``GraphTerm`` wrapper, so terms sit here directly.
#: ``TripleTerm`` is added to this union in ``grammar.py`` (it is defined there).
VarOrTerm = alias(
    "VarOrTerm",
    Union[
        Var,
        IRI,
        PNAME_LN,
        PNAME_NS,
        RDFLiteral,
        INTEGER,
        DECIMAL,
        DOUBLE,
        INTEGER_POSITIVE,
        DECIMAL_POSITIVE,
        DOUBLE_POSITIVE,
        INTEGER_NEGATIVE,
        DECIMAL_NEGATIVE,
        DOUBLE_NEGATIVE,
        BooleanLiteral,
        BLANK_NODE_LABEL,
        ANON,
        NIL,
    ],
)
