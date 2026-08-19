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

One consequence of the aliasing is worth spelling out, because the name reads as
lexical rather than semantic: **``INTEGER`` is a term**. The spec has
``VarOrTerm ::= Var | iri | RDFLiteral | NumericLiteral | ...``,
``NumericLiteral ::= NumericLiteralUnsigned | ...`` and
``NumericLiteralUnsigned ::= INTEGER | DECIMAL | DOUBLE``; since the two middle
productions are bare alternations, ``INTEGER`` and its siblings appear in
:data:`VarOrTerm` directly. A bare ``5`` in a triple is an ``INTEGER`` token per the
grammar, and :func:`numeric_literal` is how a Python number becomes one.

Note also that the signed numerics (``INTEGER_NEGATIVE`` and friends) hold *unsigned*
text and render the sign, in keeping with the rule above - so ``-5`` is
``INTEGER_NEGATIVE("5")``, not ``INTEGER("-5")``, whose value would not match the
production's own pattern.
"""

from __future__ import annotations

import re
from math import isfinite
from typing import ClassVar, NoReturn, Union

from ._base import Add, Node, alias, production
from .terminals import (
    IRIREF_INNER_RE,
    LANG_DIR_INNER_RE,
    VARNAME_RE,
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
    escape_string,
)

__all__ = [
    "Var",
    "IRI",
    "iri_is_valid",
    "numeric_literal",
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


_VARNAME = re.compile(VARNAME_RE)
_IRI_TEXT = re.compile(IRIREF_INNER_RE)
_LANG_DIR = re.compile(LANG_DIR_INNER_RE)

#: Characters that can never appear in an IRI. A backslash is excluded because it is
#: legal inside a \uXXXX escape, which is handled by the second stage below.
_IRI_FORBIDDEN = re.compile(r'[<>"{}|^\x00-\x20]')


def iri_is_valid(text: str) -> bool:
    r"""Whether ``text`` can be rendered inside ``<...>`` without changing the query.

    Two stages, because the full spec pattern alternates per character to allow
    ``\uXXXX`` escapes and is five times slower than a plain scan. Almost no IRI
    contains a backslash, so the scan answers on its own; when one does, the spec
    pattern decides. The two agree on every input - the split is only for speed, and
    it is what makes checking cheap enough to be the default.
    """
    if _IRI_FORBIDDEN.search(text):
        return False
    if "\\" in text:
        return _IRI_TEXT.fullmatch(text) is not None
    return True


def numeric_literal(value: int | float) -> Node:
    """The numeric literal the spec spells for a Python number.

    ``INTEGER``, ``DECIMAL`` and ``DOUBLE`` are all unsigned, and the signed terminals
    hold unsigned text and render the sign - so a negative number needs the matching
    ``*_NEGATIVE`` class rather than a minus tucked inside the value. ``DOUBLE`` is the
    form carrying an exponent and ``DECIMAL`` the form without, which is exactly the
    split :func:`repr` already makes.

    Shared by :func:`sparql_grammar.helpers.literal`, the expression builders and the
    rdflib bridge, so that one Python number means one SPARQL literal everywhere.
    """
    if isinstance(value, bool):
        # bool is a subclass of int, and "True" is not an INTEGER
        raise TypeError("a bool is a BooleanLiteral, not a numeric literal")
    if isinstance(value, int):
        return INTEGER(str(value)) if value >= 0 else INTEGER_NEGATIVE(str(-value))
    if not isinstance(value, float):
        raise TypeError(f"{type(value).__name__} is not a number")
    if not isfinite(value):
        raise ValueError(
            f"{value!r} cannot be a SPARQL literal: the grammar has no syntax for "
            "infinity or NaN. Write it as a typed literal if your store accepts one, "
            'e.g. literal("INF", datatype=iri("http://www.w3.org/2001/XMLSchema#double")).'
        )
    text = repr(abs(value))
    negative = value < 0 or (value == 0 and str(value)[:1] == "-")
    if "e" in text or "E" in text:
        return DOUBLE_NEGATIVE(text) if negative else DOUBLE(text)
    return DECIMAL_NEGATIVE(text) if negative else DECIMAL(text)


#: Text shaped like a prefixed name. Used only to pick the more helpful suggestion in
#: :func:`refuse_string`; it decides nothing about what gets built.
_PREFIXED_SHAPE = re.compile(r"[A-Za-z][\w.\-]*:\S*")


def refuse_string(value: str, *, literals_allowed: bool = True) -> NoReturn:
    """Refuse a bare string in a term position, naming the constructor to use.

    No string is ever read as a term - not here, not in a triple, not in an
    expression - which is the same bargain rdflib strikes with ``URIRef`` and
    ``Literal``. The reasons:

    * ``"<http://x>"`` is as plausibly a literal as an IRI, and only the caller knows;
    * a value read as a *variable* is worse than merely wrong.
      ``VALUES ?name { "Alice" }`` constrains a query, while
      ``VALUES ?name { ?anything }`` removes the constraint altogether - so one
      untrusted string starting with ``?`` would rewrite a query rather than
      parameterise it.

    The suggestion in the message is chosen from the text's shape to make the fix
    obvious. Nothing is built from it.
    """
    text = value.strip()
    shown = value if len(value) <= 60 else value[:57] + "..."
    if text[:1] in ("?", "$"):
        suggestion = f"var({text[1:]!r})"
    elif text.startswith("<") and text.endswith(">"):
        suggestion = f"iri({text[1:-1]!r})"
    elif not literals_allowed or "://" in text or _PREFIXED_SHAPE.fullmatch(text):
        suggestion = f"iri({text!r})"
    else:
        suggestion = f"literal({text!r})"
    options = "iri(), literal() or var()" if literals_allowed else "iri() or var()"
    raise TypeError(
        f"{shown!r} is a str, and a str is never read as a term - probably "
        f"{suggestion}, otherwise one of {options}."
    )


@production(rule="Var")
class Var(Node):
    """Var ::= VAR1 | VAR2

    ``sigil`` selects the surface form: ``?name`` (default) or ``$name``.
    """

    value: str
    sigil: str = "?"

    def _check(self, level: str) -> list[str]:
        errors = super()._check(level)
        if not _VARNAME.fullmatch(self.value):
            errors.append(f"Var: {self.value!r} is not a valid variable name")
        return errors

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

    def _check(self, level: str) -> list[str]:
        errors = super()._check(level)
        if not iri_is_valid(self.value):
            # An IRI has no escape syntax for the delimiters, so a value carrying
            # '>' or whitespace cannot be rendered safely - it can only be refused.
            errors.append(
                f"IRI: {self.value!r} is not a valid IRI "
                "(it contains a character that would terminate the IRI)"
            )
        return errors

    @classmethod
    def from_string(cls, text: str) -> IRI:
        text = text.strip()
        if text.startswith("<") and text.endswith(">"):
            text = text[1:-1]
        return cls(text)

    @classmethod
    def checked(cls, text: str) -> IRI:
        """Build an IRI, refusing anything that is not one.

        The constructor to reach for at the boundary where untrusted input enters a
        query: see :func:`sparql_grammar.helpers.iri` with ``check=True``.
        """
        node = cls.from_string(text)
        node.validate("terminals")
        return node

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

    def _check(self, level: str) -> list[str]:
        errors = super()._check(level)
        if self.lang_dir is not None and self.datatype is not None:
            errors.append("RDFLiteral: a literal has a language or a datatype, not both")
        # The text is escaped when rendered, but a language tag and a datatype IRI
        # are not escapable, so they are checked here rather than being left to a
        # whole-tree walk: they are part of what makes this one literal safe.
        if self.lang_dir is not None and not _LANG_DIR.fullmatch(self.lang_dir.value):
            errors.append(
                f"RDFLiteral: {self.lang_dir.value!r} is not a valid language tag"
            )
        if self.datatype is not None:
            errors.extend(self.datatype._check(level))
        return errors

    def render(self, add: Add) -> None:
        value = self.value
        if isinstance(value, str):
            # Plain text is raw content, so it is escaped on the way out. Without
            # this, a value containing a quote closes its own literal and whatever
            # follows becomes part of the query. Pass a String terminal instead to
            # take responsibility for the surface form yourself.
            add('"')
            add(escape_string(value))
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
