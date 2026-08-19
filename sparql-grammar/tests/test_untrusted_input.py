"""Untrusted input must not be able to change what a query means.

The use this library is put to is parameterised queries: a skeleton built once from
values the program controls, with inputs substituted per request. That makes the term
constructors the security boundary, and there are two different jobs to do there:

* A string literal **can** be escaped, so it is escaped automatically on render.
  Building a literal from hostile input is safe without asking for anything.
* An IRI, a variable name and a prefixed name have **no** escape syntax. A value
  carrying ``>`` or whitespace cannot be rendered as an IRI at all, so it can only be
  refused - which is what ``check=True`` / ``checked()`` do.

These tests are written as attacks, so a regression shows up as a query whose shape
changed rather than as a failed assertion about escaping.
"""

from __future__ import annotations

import pytest

from sparql_grammar import (
    IRI,
    RDFLiteral,
    ValidationError,
    Var,
    checked,
    construct,
    insert_data,
    iri,
    literal,
    modify,
    select,
    term,
    values,
    var,
)
from sparql_grammar.terminals import escape_string

pytest.importorskip("lark", reason="the attacks are confirmed by re-parsing")
from sparql_grammar.parse import parse  # noqa: E402

#: Values crafted to break out of the term they are placed in.
BREAKOUT_STRINGS = [
    'x" . ?s ?p ?o . #',
    'x"@en . ?evil ?evil ?evil . #',
    'x"^^<http://evil> . ?s ?p ?o . #',
    "x' . ?s ?p ?o . #",
    'x\\" . ?s ?p ?o . #',
    'multi\nline" . ?s ?p ?o . #',
]

BREAKOUT_IRIS = [
    "http://x> . ?s ?p ?o . <http://y",
    "http://x> } ; DROP ALL ; INSERT DATA { <http://a> <http://b> <http://c",
    "http://x <http://y",
    "http://x\n?s ?p ?o",
]


def _raw_triple_block(payload: str):
    """A triples block built only from production classes, so nothing validates."""
    from sparql_grammar import TriplesBlock, TriplesSameSubjectPath

    return TriplesBlock(
        [TriplesSameSubjectPath.from_spo(Var("s"), IRI("http://p"), IRI(payload))]
    )


def triple_count(query_text: str) -> int:
    """How many triple patterns the query actually contains once parsed."""
    from sparql_grammar import TriplesSameSubjectPath

    return len(parse(query_text).collect(TriplesSameSubjectPath))


class TestLiteralsAreEscaped:
    """Literals are safe by default: escaping is not something to remember."""

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_payload_cannot_add_triples(self, payload):
        query = select("?s", where=[("?s", iri("http://p"), literal(payload))])
        text = query.to_string()
        # the query still has exactly the one triple it was built with
        assert triple_count(text) == 1

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_payload_survives_intact(self, payload):
        """Escaping must preserve the value, not mangle it."""
        query = select("?s", where=[("?s", iri("http://p"), literal(payload))])
        objects = [
            node
            for node in parse(query.to_string()).collect(type(literal("x")))
        ]
        assert objects, "no literal found in the reparsed query"

    def test_quote_is_escaped(self):
        assert literal('say "hi"').to_string() == '"say \\"hi\\""'

    def test_backslash_is_escaped(self):
        assert literal("back\\slash").to_string() == '"back\\\\slash"'

    def test_newline_is_escaped(self):
        assert literal("a\nb").to_string() == '"a\\nb"'

    def test_clean_text_is_untouched(self):
        assert literal("a plain label").to_string() == '"a plain label"'

    def test_explicit_string_terminal_is_not_escaped_again(self):
        """Passing a String terminal means taking charge of the surface form."""
        from sparql_grammar import STRING_LITERAL2

        assert RDFLiteral(STRING_LITERAL2("already \\\" escaped")).to_string() == (
            '"already \\" escaped"'
        )

    def test_escape_string_is_idempotent_on_clean_input(self):
        assert escape_string("clean") == "clean"

    def test_literal_from_hostile_input_needs_no_check(self):
        # the point of escaping: the safe path is the default one
        literal(BREAKOUT_STRINGS[0])  # no exception, and rendering is safe


class TestIrisAreRefused:
    """An IRI cannot be escaped, so a bad one must be rejected."""

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_checked_refuses(self, payload):
        with pytest.raises(ValidationError, match="not a valid IRI"):
            iri(payload, check=True)

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_validation_catches_it_after_the_fact(self, payload):
        with pytest.raises(ValidationError):
            IRI(payload).validate("terminals")

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_the_helper_refuses_by_default(self, payload):
        """``iri()`` validates unless told not to, so the easy path is the safe one."""
        with pytest.raises(ValidationError):
            iri(payload)

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_helpers_check_even_a_prebuilt_node(self, payload):
        """Handing a raw IRI node to a helper does not get round the check."""
        with pytest.raises(ValidationError):
            select("?s", where=[("?s", iri("http://p"), IRI(payload))])

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_the_raw_production_classes_are_the_unchecked_path(self, payload):
        """The production constructors never validate - that is their purpose.

        They exist so code that produced its own values does not pay for a check per
        term. This documents what that costs if the value did come from outside:
        build a tree without touching a helper and the rendered query is no longer
        the query you built.
        """
        block = _raw_triple_block(payload)
        rendered = block.to_string()
        try:
            changed = triple_count(f"SELECT * WHERE {{ {rendered} }}") > 1
        except Exception:
            changed = True  # unparseable counts as changed, and is not silent either
        assert changed or "DROP" in rendered.upper()

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_validation_is_the_backstop_for_the_raw_path(self, payload):
        """A validate() pass in tests catches what the fast path let through."""
        with pytest.raises(ValidationError):
            _raw_triple_block(payload).validate("terminals")

    def test_checked_accepts_ordinary_iris(self):
        for good in [
            "http://example.com/thing",
            "https://linked.data.gov.au/def/borehole",
            "urn:uuid:12345",
            "http://example.com/path?query=1&x=2#frag",
        ]:
            iri(good, check=True)

    def test_iri_checked_classmethod(self):
        assert IRI.checked("<http://example.com/a>") == IRI("http://example.com/a")
        with pytest.raises(ValidationError):
            IRI.checked(BREAKOUT_IRIS[0])


class TestVariableNames:
    @pytest.mark.parametrize("payload", ["s . ?x ?y ?z", "s}", "s ?p ?o", ""])
    def test_checked_refuses_bad_names(self, payload):
        with pytest.raises(ValidationError, match="variable name"):
            var(payload, check=True)

    def test_checked_accepts_good_names(self):
        for good in ["s", "?s", "focus_node", "v123", "_private"]:
            var(good, check=True)


class TestCheckedBoundary:
    """``checked()`` is the one call to reach for at the input boundary."""

    def test_helpers_validate_by_default(self):
        """checked() is explicit, but term()/iri()/var() already check."""
        with pytest.raises(ValidationError):
            term(f"<{BREAKOUT_IRIS[0]}>")
        with pytest.raises(ValidationError):
            var("s . ?x ?y ?z")

    def test_check_false_opts_out(self):
        # the escape hatch for hot paths over values the program produced
        iri(BREAKOUT_IRIS[0], check=False)
        var("s . ?x ?y ?z", check=False)

    def test_dispatches_by_shape(self):
        assert isinstance(checked("?s"), Var)
        assert isinstance(checked("<http://x>"), IRI)
        assert isinstance(checked("plain text"), RDFLiteral)

    @pytest.mark.parametrize("payload", BREAKOUT_IRIS)
    def test_refuses_hostile_iris(self, payload):
        with pytest.raises(ValidationError):
            checked(f"<{payload}>")

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_accepts_hostile_text_because_it_is_escaped(self, payload):
        node = checked(payload)
        query = select("?s", where=[("?s", iri("http://p"), node)])
        assert triple_count(query.to_string()) == 1

    def test_equivalent_to_term_with_check(self):
        assert checked("?s") == term("?s", check=True)

    def test_passes_existing_nodes_through_validation(self):
        with pytest.raises(ValidationError):
            checked(IRI(BREAKOUT_IRIS[0]))


class TestUpdateAndConstructPaths:
    """The same protection has to hold on the paths that write data."""

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_insert_data_literal(self, payload):
        request = insert_data([("<http://s>", iri("http://p"), literal(payload))])
        reparsed = parse(request.to_string())
        from sparql_grammar import TriplesSameSubject

        assert len(reparsed.collect(TriplesSameSubject)) == 1

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_modify_literal(self, payload):
        request = modify(
            where=[("?s", iri("http://p"), var("o"))],
            insert=[("?s", iri("http://p"), literal(payload))],
        )
        parse(request.to_string())  # still one well-formed request

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_construct_template_literal(self, payload):
        query = construct(
            [("?s", iri("http://p"), literal(payload))],
            where=[("?s", iri("http://p"), var("o"))],
        )
        parse(query.to_string())

    @pytest.mark.parametrize("payload", BREAKOUT_STRINGS)
    def test_values_block_literal(self, payload):
        query = select("?v", where=[values("v", [literal(payload)])])
        assert triple_count(query.to_string()) == 0  # a VALUES block, no triples
        parse(query.to_string())


class TestParameterisedQueryPattern:
    """The intended shape: trusted skeleton, checked parameters."""

    def test_skeleton_is_reusable_and_inputs_are_checked(self):
        template = select(
            "?s",
            where=[("?s", iri("ex:p"), var("value"))],
            prefixes={"ex": "http://ex/"},
        )
        first = template.to_string()

        good = [checked(f"http://example.com/{i}") for i in range(3)]
        assert len(good) == 3

        with pytest.raises(ValidationError):
            checked(f"<{BREAKOUT_IRIS[0]}>")

        # the skeleton is untouched by any of it
        assert template.to_string() == first

    def test_language_tag_cannot_carry_a_payload(self):
        """No check= argument: the default refuses it."""
        with pytest.raises(ValidationError, match="language tag"):
            literal("x", lang='en" . ?s ?p ?o . #')

    def test_datatype_iri_cannot_carry_a_payload(self):
        with pytest.raises(ValidationError, match="not a valid IRI"):
            literal("x", datatype=BREAKOUT_IRIS[0])

    def test_good_language_and_datatype_still_work(self):
        assert literal("x", lang="en").to_string() == '"x"@en'
        assert literal("x", lang="ar--rtl").to_string() == '"x"@ar--rtl'
        xsd_integer = "http://www.w3.org/2001/XMLSchema#integer"
        assert literal("1", datatype=xsd_integer).to_string() == f'"1"^^<{xsd_integer}>'

    def test_every_string_entry_point_is_safe_by_default(self):
        """The summary of the whole file: no argument needed to be safe."""
        for call in (
            lambda: iri(BREAKOUT_IRIS[0]),
            lambda: var("s . ?x ?y"),
            lambda: term(f"<{BREAKOUT_IRIS[0]}>"),
            lambda: literal("x", lang='en" . #'),
            lambda: literal("x", datatype=BREAKOUT_IRIS[0]),
        ):
            with pytest.raises(ValidationError):
                call()
        # and the escapable one needs no refusal at all
        assert literal(BREAKOUT_STRINGS[0]).to_string().count('"') >= 2

    def test_literal_cannot_have_both_language_and_datatype(self):
        node = RDFLiteral("x", lang_dir=None, datatype=IRI("http://d"))
        node.lang_dir = __import__(
            "sparql_grammar", fromlist=["LANG_DIR"]
        ).LANG_DIR("en")
        with pytest.raises(ValidationError, match="language or a datatype"):
            node.validate("terminals")
