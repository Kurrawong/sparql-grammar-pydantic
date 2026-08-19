"""Pretty-printing."""

from __future__ import annotations

import pytest

from sparql_grammar import (
    IRI,
    Expression,
    OrderCondition,
    bound,
    construct,
    filter_,
    format_sparql,
    graph,
    group,
    insert_data,
    iri,
    literal,
    minus,
    modify,
    not_exists,
    optional,
    select,
    service,
    subselect,
    triple,
    union,
    var,
)


class TestBasics:
    def test_indents_nested_blocks(self):
        query = select(var("s"), where=[(var("s"), "a", iri("http://ex/C"))])
        assert format_sparql(query) == (
            "SELECT ?s\nWHERE {\n  ?s a <http://ex/C>\n}"
        )

    def test_indent_string_is_configurable(self):
        query = select(var("s"), where=[(var("s"), "a", iri("http://ex/C"))])
        assert "\t?s a" in format_sparql(query, indent="\t")

    def test_node_method_matches_function(self):
        query = select(var("s"), where=[(var("s"), var("p"), var("o"))])
        assert query.to_pretty_string() == format_sparql(query)

    def test_canonical_output_is_unchanged(self):
        """Layout is opt-in; to_string stays the cheap canonical path."""
        query = select(var("s"), where=[(var("s"), var("p"), var("o"))])
        assert "\n  " not in query.to_string()

    def test_nesting_depth_accumulates(self):
        query = select(
            var("s"),
            where=[
                optional(
                    union(
                        (var("s"), iri("http://a"), var("y")),
                        (var("s"), iri("http://b"), var("y")),
                    )
                )
            ],
        )
        lines = format_sparql(query).splitlines()
        indents = {len(line) - len(line.lstrip()) for line in lines if line.strip()}
        assert indents == {0, 2, 4, 6}


class TestConstructs:
    @pytest.mark.parametrize(
        "pattern,opening",
        [
            (optional((var("s"), var("p"), var("o"))), "OPTIONAL {"),
            (minus((var("s"), var("p"), var("o"))), "MINUS {"),
            (graph(var("g"), (var("s"), var("p"), var("o"))), "GRAPH ?g {"),
            (
                service(iri("http://e"), (var("s"), var("p"), var("o"))),
                "SERVICE <http://e> {",
            ),
        ],
    )
    def test_block_openings(self, pattern, opening):
        text = format_sparql(select(var("s"), where=[pattern]))
        assert f"  {opening}" in text

    def test_union_arms_are_separate_blocks(self):
        text = format_sparql(
            select(
                var("s"),
                where=[
                    union(
                        (var("s"), iri("http://a"), var("y")),
                        (var("s"), iri("http://b"), var("y")),
                    )
                ],
            )
        )
        assert "\n  UNION\n" in text

    def test_filter_exists_is_a_block(self):
        text = format_sparql(
            select(var("s"), where=[filter_(not_exists((var("s"), var("p"), var("o"))))])
        )
        assert "  FILTER NOT EXISTS {" in text

    def test_plain_filter_stays_on_one_line(self):
        text = format_sparql(select(var("s"), where=[filter_(bound(var("o")))]))
        assert "  FILTER BOUND(?o)" in text

    def test_triples_are_dot_separated(self):
        text = format_sparql(
            select(
                var("s"),
                where=[
                    (var("s"), iri("http://a"), var("x")),
                    (var("s"), iri("http://b"), var("y")),
                ],
            )
        )
        assert text.count(" .") == 1  # between the two, not after the last

    def test_construct_template_and_where(self):
        text = format_sparql(construct([(var("s"), iri("http://p"), var("o"))]))
        assert text.startswith("CONSTRUCT {\n  ?s <http://p> ?o\n}\nWHERE {")

    def test_solution_modifiers_on_their_own_lines(self):
        text = format_sparql(
            select(
                var("s"),
                where=[(var("s"), var("p"), var("o"))],
                order_by=OrderCondition.desc(var("s")),
                limit=5,
            )
        )
        assert text.endswith("ORDER BY DESC(?s)\nLIMIT 5")

    def test_prefixes_precede_the_query(self):
        text = format_sparql(
            select(var("s"), where=[(var("s"), var("p"), var("o"))], prefixes={"ex": "http://ex/"})
        )
        assert text.startswith("PREFIX ex: <http://ex/>\nSELECT")

    def test_subselect_is_indented(self):
        inner = subselect(var("s"), where=[(var("s"), var("p"), var("o"))], limit=1)
        text = format_sparql(select(var("s"), where=[group(inner)]))
        assert "  SELECT ?s" in text

    def test_update_operations(self):
        text = format_sparql(
            modify(
                where=[(var("s"), iri("ex:old"), var("o"))],
                delete=[(var("s"), iri("ex:old"), var("o"))],
                insert=[(var("s"), iri("ex:new"), var("o"))],
            )
        )
        assert text.startswith("DELETE {\n  ?s ex:old ?o\n}\nINSERT {")

    def test_insert_data(self):
        text = format_sparql(
            insert_data([(iri("http://s"), iri("http://p"), literal("v"))])
        )
        assert text == 'INSERT DATA {\n  <http://s> <http://p> "v"\n}'


class TestLiteralIntegrity:
    """Formatting must never change what a query means."""

    def test_escaped_newlines_pass_through_untouched(self):
        """A newline cannot appear raw in a short literal, so it renders escaped.

        What matters here is that the formatter does not then alter it: the two-
        character escape must survive layout unchanged.
        """
        query = select(
            var("s"), where=[(var("s"), iri("http://p"), literal("line one\nline two"))]
        )
        assert "line one\\nline two" in format_sparql(query)

    def test_escaped_tabs_pass_through_untouched(self):
        query = select(var("s"), where=[(var("s"), iri("http://p"), literal("a\tb"))])
        assert "a\\tb" in format_sparql(query)

    def test_long_literals_keep_real_newlines(self):
        """A long literal may hold newlines verbatim, and formatting must keep them."""
        from sparql_grammar import RDFLiteral, STRING_LITERAL_LONG1

        query = select(
            var("s"),
            where=[
                (var("s"), iri("http://p"), RDFLiteral(STRING_LITERAL_LONG1("one\ntwo")))
            ],
        )
        assert "one\ntwo" in format_sparql(query)


class TestUnknownNodes:
    def test_unhandled_node_still_formats_inline(self):
        """Anything without a layout handler renders via its own to_string."""
        assert format_sparql(IRI("http://x")) == "<http://x>"
        assert format_sparql(Expression.compare(var("a"), "=", 1)) == "?a = 1"

    def test_bare_triple(self):
        pattern = triple(var("s"), iri("http://p"), var("o"))
        assert format_sparql(pattern) == "?s <http://p> ?o"
