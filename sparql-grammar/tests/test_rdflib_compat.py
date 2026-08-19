"""rdflib term interop (the optional rdflib extra)."""

from __future__ import annotations

import pytest

rdflib = pytest.importorskip("rdflib", reason="needs the rdflib extra")

from rdflib import BNode, Literal, URIRef, Variable, XSD  # noqa: E402

from sparql_grammar import (  # noqa: E402
    ANON,
    BLANK_NODE_LABEL,
    DECIMAL,
    DOUBLE,
    INTEGER,
    IRI,
    BooleanLiteral,
    RDFLiteral,
    Var,
)
from sparql_grammar.rdflib_compat import (  # noqa: E402
    from_grammar_term,
    prologue_from_namespaces,
    to_grammar_term,
)


class TestToGrammar:
    @pytest.mark.parametrize(
        "value,expected_type,rendered",
        [
            (URIRef("http://ex/p"), IRI, "<http://ex/p>"),
            (Variable("s"), Var, "?s"),
            (BNode("b1"), BLANK_NODE_LABEL, "_:b1"),
            (Literal("hi"), RDFLiteral, '"hi"'),
            (Literal("hi", lang="en"), RDFLiteral, '"hi"@en'),
            (Literal(True), BooleanLiteral, "true"),
            (Literal(42), INTEGER, "42"),
            (Literal("3.14", datatype=XSD.decimal), DECIMAL, "3.14"),
        ],
    )
    def test_conversions(self, value, expected_type, rendered):
        node = to_grammar_term(value)
        assert isinstance(node, expected_type)
        assert node.to_string() == rendered

    def test_unknown_datatype_kept_as_typed_literal(self):
        node = to_grammar_term(Literal("2024-01-01", datatype=XSD.date))
        assert node.to_string() == f'"2024-01-01"^^<{XSD.date}>'

    def test_typed_numerics_can_be_kept_explicit(self):
        node = to_grammar_term(Literal(42), typed_numerics=False)
        assert node.to_string() == f'"42"^^<{XSD.integer}>'

    def test_quotes_and_backslashes_are_escaped(self):
        node = to_grammar_term(Literal('say "hi" \\ ok'))
        assert node.to_string() == '"say \\"hi\\" \\\\ ok"'

    def test_newlines_are_escaped(self):
        assert to_grammar_term(Literal("a\nb")).to_string() == '"a\\nb"'

    def test_plain_python_values(self):
        assert to_grammar_term(True).to_string() == "true"
        assert to_grammar_term(7).to_string() == "7"
        assert to_grammar_term("text").to_string() == '"text"'

    def test_grammar_nodes_pass_through(self):
        node = IRI("http://x")
        assert to_grammar_term(node) is node

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            to_grammar_term(object())


class TestFromGrammar:
    @pytest.mark.parametrize(
        "value",
        [
            URIRef("http://ex/p"),
            Variable("s"),
            Literal("hi"),
            Literal("hi", lang="en"),
            Literal(True),
            Literal(42),
        ],
    )
    def test_round_trip(self, value):
        assert from_grammar_term(to_grammar_term(value)) == value

    def test_blank_node_round_trip(self):
        assert str(from_grammar_term(to_grammar_term(BNode("b1")))) == "b1"

    def test_anon_has_no_equivalent(self):
        with pytest.raises(TypeError, match="ANON"):
            from_grammar_term(ANON())

    def test_typed_literal_round_trip(self):
        original = Literal("2024-01-01", datatype=XSD.date)
        assert from_grammar_term(to_grammar_term(original)) == original


class TestNamespaces:
    def test_prologue_from_graph(self):
        graph = rdflib.Graph()
        graph.bind("skos", "http://www.w3.org/2004/02/skos/core#")
        rendered = prologue_from_namespaces(graph.namespace_manager).to_string()
        assert "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>" in rendered


class TestCoreHasNoRdflibDependency:
    def test_core_modules_do_not_import_rdflib(self):
        """rdflib is only ever imported from rdflib_compat, and lazily.

        Matched on import statements rather than the word: other modules are free to
        mention rdflib in a docstring, and several do, since its ``URIRef``/``Literal``
        split is the precedent for requiring explicit terms.
        """
        import re
        from pathlib import Path

        package = Path(__file__).resolve().parent.parent / "sparql_grammar"
        imports = re.compile(r"^\s*(?:import rdflib|from rdflib)", re.MULTILINE)
        offenders = [
            path.name
            for path in package.glob("*.py")
            if path.name != "rdflib_compat.py" and imports.search(path.read_text())
        ]
        assert offenders == []
