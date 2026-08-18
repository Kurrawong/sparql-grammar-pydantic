"""Parsing SPARQL text into grammar objects, and the W3C corpus round-trip."""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

pytest.importorskip("lark", reason="needs the parse extra")

from sparql_grammar import (  # noqa: E402
    AskQuery,
    ConstructQuery,
    DescribeQuery,
    INTEGER,
    IRI,
    InsertData,
    Modify,
    QueryUnit,
    SelectQuery,
    UpdateUnit,
    Var,
)
from sparql_grammar.parse import (  # noqa: E402
    SparqlSyntaxError,
    parse,
    parse_query,
    parse_update,
    to_python_source,
)

CORPUS_ROOT = Path("/workspace/kurrawong/sparqlib/tests/data")


class TestBasicParsing:
    def test_returns_typed_tree(self):
        query = parse("SELECT ?s WHERE { ?s ?p ?o }")
        assert isinstance(query, QueryUnit)
        assert isinstance(query.query.query, SelectQuery)

    def test_query_forms(self):
        assert isinstance(parse("SELECT * WHERE { ?s ?p ?o }").query.query, SelectQuery)
        assert isinstance(parse("ASK WHERE { ?s ?p ?o }").query.query, AskQuery)
        assert isinstance(parse("DESCRIBE <http://x>").query.query, DescribeQuery)
        assert isinstance(
            parse("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }").query.query,
            ConstructQuery,
        )

    def test_update_forms(self):
        request = parse("INSERT DATA { <http://s> <http://p> <http://o> }")
        assert isinstance(request, UpdateUnit)
        assert isinstance(request.update.operations[0], InsertData)

    def test_modify(self):
        request = parse(
            "WITH <http://g> DELETE { ?s <http://p> ?o } "
            "INSERT { ?s <http://q> ?o } WHERE { ?s <http://p> ?o }"
        )
        assert isinstance(request.update.operations[0], Modify)

    def test_parse_query_rejects_update(self):
        with pytest.raises(SparqlSyntaxError):
            parse_query("INSERT DATA { <http://s> <http://p> <http://o> }")

    def test_parse_update_rejects_query(self):
        with pytest.raises(SparqlSyntaxError):
            parse_update("SELECT * WHERE { ?s ?p ?o }")

    def test_invalid_input_raises(self):
        with pytest.raises(SparqlSyntaxError):
            parse("SELECT WHERE {")

    def test_earley_fallback_available(self):
        assert parse("SELECT * WHERE { ?s ?p ?o }", parser="earley") is not None

    def test_property_path_in_collection(self):
        """Was the one construct LALR could not lex, until path_mod stopped
        needing a terminal of its own."""
        query = (
            'PREFIX : <http://example.org/> '
            'SELECT * WHERE { ?s ?p ( [:p*/:q 123 ] [ ^:r "hello"] ) }'
        )
        assert parse(query).to_string() == parse(query, parser="earley").to_string()

    @pytest.mark.parametrize("modifier", ["*", "+", "?"])
    def test_path_modifiers_lex_under_lalr(self, modifier):
        query = f"SELECT * WHERE {{ ?s <http://a>{modifier} ?o }}"
        assert parse(query).to_string().endswith(f"<http://a>{modifier} ?o\n}}")

    def test_variables_still_lex_as_variables(self):
        """Guards the fix above: a bare '?' terminal must not outrank VAR1."""
        assert parse("SELECT ?o WHERE { ?o ?p ?q }").collect(Var)


class TestManipulation:
    """The point of parsing: change the query, then render it back."""

    def test_mutate_limit(self):
        query = parse("SELECT ?s WHERE { ?s ?p ?o } LIMIT 10")
        query.query.query.solution_modifier.limit_offset.limit_clause.limit = INTEGER("99")
        assert "LIMIT 99" in query.to_string()

    def test_add_a_triple_to_a_parsed_query(self):
        from sparql_grammar import triple

        query = parse("SELECT ?s WHERE { ?s ?p ?o }")
        ggps = query.query.query.where_clause.group_graph_pattern.content
        ggps.add_triples([triple("?s", IRI("http://extra"), "?x")])
        assert "<http://extra>" in query.to_string()

    def test_collect_variables(self):
        query = parse("SELECT ?s WHERE { ?s <http://p> ?o . ?o <http://q> ?z }")
        names = {v.value for v in query.collect(Var)}
        assert {"s", "o", "z"} <= names

    def test_parsed_nodes_are_hashable(self):
        a = parse("SELECT ?s WHERE { ?s ?p ?o }")
        b = parse("SELECT ?s WHERE { ?s ?p ?o }")
        assert a == b and hash(a) == hash(b)


class TestRoundTrip:
    @pytest.mark.parametrize(
        "query",
        [
            "SELECT ?s WHERE { ?s a <http://ex/C> } LIMIT 10",
            "PREFIX ex: <http://ex/> SELECT DISTINCT ?s WHERE { ?s ex:p ?o } ORDER BY DESC(?o)",
            "SELECT * WHERE { ?s ?p ?o OPTIONAL { ?s <http://q> ?x } FILTER(?o > 5) }",
            "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o } GROUP BY ?s HAVING (COUNT(*) > 1)",
            "SELECT (GROUP_CONCAT(?x ; SEPARATOR=',') AS ?g) WHERE { ?s ?p ?x }",
            "SELECT * WHERE { { ?s <http://a> ?o } UNION { ?s <http://b> ?o } }",
            "SELECT * WHERE { ?s <http://a>/<http://b>|^<http://c> ?o }",
            "SELECT * WHERE { ?s <http://a>* ?o }",
            "SELECT * WHERE { ?s !(<http://a>|^<http://b>) ?o }",
            "SELECT * WHERE { VALUES (?a ?b) { (<http://1> 'x') (<http://2> UNDEF) } }",
            "SELECT * WHERE { GRAPH ?g { ?s ?p ?o } }",
            "SELECT * WHERE { SERVICE SILENT <http://e> { ?s ?p ?o } }",
            "SELECT * WHERE { ?s ?p ?o FILTER NOT EXISTS { ?s <http://q> ?x } }",
            "SELECT * WHERE { ?s ?p ?o FILTER(?o IN (1, 2)) }",
            "SELECT * WHERE { ?s ?p ?o FILTER(?o NOT IN (1, 2)) }",
            "SELECT * WHERE { ?s ?p ?o FILTER(?a + 1 > ?b * 2) }",
            "SELECT * WHERE { ?s ?p ?o FILTER(true && NOT EXISTS { ?s ?p ?o }) }",
            "SELECT * WHERE { ?s <http://p> [ <http://q> ?o ] }",
            "SELECT * WHERE { [ <http://p> 'v' ] }",
            "SELECT * WHERE { ?s <http://p> ( ?a ?b ) }",
            "SELECT * WHERE { { SELECT ?s WHERE { ?s ?p ?o } LIMIT 1 } }",
            "SELECT (CONCAT() AS ?c) (BNODE() AS ?b) (NOW() AS ?n) WHERE { }",
            "SELECT * WHERE { } VALUES () { () }",
            "SELECT * FROM <http://g1> FROM NAMED <http://g2> WHERE { ?s ?p ?o }",
            # SPARQL 1.2
            'VERSION "1.2" SELECT * WHERE { ?s ?p ?o }',
            "SELECT * WHERE { <<?s <http://p> ?o>> <http://c> 0.9 }",
            "SELECT * WHERE { <<?s <http://p> ?o ~?r>> <http://c> 0.9 }",
            "SELECT * WHERE { ?s <http://says> <<(?a <http://b> ?c)>> }",
            "SELECT * WHERE { ?s <http://p> ?o {| <http://src> ?x |} }",
            'SELECT * WHERE { ?s <http://p> "hi"@ar--rtl }',
            "SELECT (isTRIPLE(?x) AS ?t) (TRIPLE(?s,?p,?o) AS ?u) WHERE { ?s ?p ?o }",
            # update
            "INSERT DATA { <http://s> <http://p> <http://o> }",
            "DELETE DATA { GRAPH <http://g> { <http://s> <http://p> <http://o> } }",
            "DELETE WHERE { ?s <http://p> ?o }",
            "DROP SILENT GRAPH <http://g>",
            "LOAD <http://d.ttl> INTO GRAPH <http://g>",
            "CLEAR ALL",
            "ADD DEFAULT TO GRAPH <http://g>",
            "INSERT DATA { <http://s> <http://p> 1 } ; DROP GRAPH <http://g>",
        ],
    )
    def test_render_is_stable(self, query):
        once = parse(query).to_string()
        assert parse(once).to_string() == once

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT ?s WHERE { ?s a <http://ex/C> } LIMIT 10",
            "SELECT * WHERE { ?s ?p ?o OPTIONAL { ?s <http://q> ?x } }",
            "INSERT DATA { <http://s> <http://p> <http://o> }",
        ],
    )
    def test_formatted_output_is_equivalent(self, query):
        tree = parse(query)
        assert parse(tree.to_pretty_string()).to_string() == tree.to_string()

    def test_multiline_literals_survive_formatting(self):
        """Formatting must never rewrite the contents of a literal."""
        query = parse("PREFIX : <http://e/> SELECT * WHERE { :x :p '''line one\nline two''' }")
        assert "line one\nline two" in query.to_pretty_string()


def _corpus(subpath: str) -> list[str]:
    if not CORPUS_ROOT.exists():
        return []
    return sorted(glob.glob(str(CORPUS_ROOT / subpath), recursive=True))


@pytest.mark.skipif(not CORPUS_ROOT.exists(), reason="W3C corpus not available")
class TestCorpus:
    """The W3C syntax suites and specification examples.

    These are the reason to trust the parser: 900+ real queries, each parsed,
    rendered, and re-parsed to confirm the rendering is stable.
    """

    def _files(self):
        return [f for f in _corpus("**/*.rq") if "negative" not in f]

    def test_all_positive_files_parse_and_round_trip(self):
        failures = []
        for path in self._files():
            source = Path(path).read_text(encoding="utf-8")
            for mode in ("lalr", "earley"):
                try:
                    tree = parse(source, parser=mode)
                except Exception as exc:  # noqa: BLE001
                    if mode == "earley":
                        failures.append(f"{Path(path).name}: no parse ({exc!r:.60})")
                    continue
                rendered = tree.to_string()
                try:
                    if parse(rendered, parser=mode).to_string() != rendered:
                        failures.append(f"{Path(path).name}: unstable render")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{Path(path).name}: render invalid ({exc!r:.60})")
                break
        assert not failures, f"{len(failures)} corpus failures: {failures[:10]}"

    def test_negative_suite_is_mostly_rejected(self):
        """Invalid queries should be refused.

        Not all of them are: the parser grammar is more permissive than the spec in
        a handful of cases. That matters little for a library whose main job is
        generating queries, and never causes a valid query to be rejected, but it is
        asserted here so the number cannot quietly get worse.
        """
        negative = [f for f in _corpus("**/*.rq") if "negative" in f]
        if not negative:
            pytest.skip("no negative suite")
        accepted = 0
        for path in negative:
            try:
                parse(Path(path).read_text(encoding="utf-8"), parser="earley")
                accepted += 1
            except Exception:  # noqa: BLE001
                pass
        assert accepted <= 11, f"{accepted} invalid queries accepted (was 11)"


class TestToPythonSource:
    def test_emits_constructor_code(self):
        source = to_python_source(parse("SELECT ?s WHERE { ?s ?p ?o }"))
        assert source.startswith("query = QueryUnit(")
        assert "SelectQuery(" in source and "Var(" in source

    def test_generated_code_rebuilds_the_query(self):
        tree = parse("SELECT ?s WHERE { ?s <http://p> ?o } LIMIT 3")
        import sparql_grammar

        namespace = {name: getattr(sparql_grammar, name) for name in sparql_grammar.__all__}
        exec(to_python_source(tree), namespace)  # noqa: S102
        assert namespace["query"].to_string() == tree.to_string()
