"""Query forms, graph patterns, triples, UPDATE, and the SPARQL 1.2 additions."""

from __future__ import annotations

import sys

import pytest

from sparql_grammar import (
    IRI,
    Add_,
    AskQuery,
    Bind,
    Clear,
    ConstructQuery,
    ConstructTemplate,
    ConstructTriples,
    Copy,
    Create,
    DatasetClause,
    DeleteClause,
    DeleteData,
    DeleteWhere,
    DescribeQuery,
    Drop,
    Expression,
    Filter,
    GraphGraphPattern,
    GraphOrDefault,
    GraphRef,
    GraphRefAll,
    GraphRefTarget,
    GroupClause,
    GroupGraphPattern,
    GroupGraphPatternSub,
    GroupOrUnionGraphPattern,
    HavingClause,
    InlineData,
    InlineDataFull,
    InlineDataOneVar,
    InsertClause,
    InsertData,
    Load,
    LimitOffsetClauses,
    MinusGraphPattern,
    Modify,
    Move,
    OptionalGraphPattern,
    OrderClause,
    OrderCondition,
    PathAlternative,
    PrefixDecl,
    Prologue,
    QuadPattern,
    Quads,
    Query,
    QueryUnit,
    RDFLiteral,
    Reifier,
    ReifiedTriple,
    SelectClause,
    SelectQuery,
    ServiceGraphPattern,
    SolutionModifier,
    SubSelect,
    TripleTerm,
    TriplesBlock,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    Update,
    UpdateUnit,
    ValidationError,
    ValuesClause,
    Var,
    VersionDecl,
    WhereClause,
)

TSSP = TriplesSameSubjectPath
TSS = TriplesSameSubject


def spo(s="s", p="http://ex/p", o="o"):
    return TSSP.from_spo(Var(s), IRI(p), Var(o))


class TestTriples:
    def test_single_triple(self):
        assert spo().to_string() == "?s <http://ex/p> ?o"

    def test_rdf_type_shorthand(self):
        assert TSSP.from_spo(Var("c"), "a", IRI("http://ex/C")).to_string() == (
            "?c a <http://ex/C>"
        )

    def test_path_predicate(self):
        assert TSSP.from_spo(
            Var("a"), PathAlternative.seq(IRI("http://p"), IRI("http://q")), Var("b")
        ).to_string() == "?a <http://p>/<http://q> ?b"

    def test_var_predicate(self):
        assert TSSP.from_spo(Var("s"), Var("p"), Var("o")).to_string() == "?s ?p ?o"

    def test_triples_block_source_order(self):
        """The old from_tssp_list reversed the triples; this one does not."""
        block = TriplesBlock.from_tssp_list([spo(o="first"), spo(o="second")])
        assert block.to_string() == (
            "?s <http://ex/p> ?first .\n?s <http://ex/p> ?second"
        )

    def test_triples_block_from_spo_list(self):
        block = TriplesBlock.from_spo_list(
            [(Var("s"), "a", IRI("http://C")), (Var("s"), IRI("http://p"), Var("o"))]
        )
        assert block.to_string() == "?s a <http://C> .\n?s <http://p> ?o"

    def test_construct_triples_merge_deduplicates(self):
        a = ConstructTriples.from_spo_list([(Var("s"), IRI("http://p"), Var("o"))])
        b = ConstructTriples.from_spo_list(
            [(Var("s"), IRI("http://p"), Var("o")), (Var("s"), IRI("http://q"), Var("o"))]
        )
        assert len(a.merge(b).triples) == 2

    def test_multiple_predicates_same_subject(self):
        from sparql_grammar import ObjectListPath, PropertyListPathNotEmpty

        plp = PropertyListPathNotEmpty(
            [
                (PathAlternative.iri("a"), ObjectListPath.create(IRI("http://C"))),
                (
                    PathAlternative.iri(IRI("http://p")),
                    ObjectListPath.create(Var("o")),
                ),
            ]
        )
        assert TSSP(Var("s"), plp).to_string() == "?s a <http://C> ; <http://p> ?o"

    def test_object_list(self):
        from sparql_grammar import ObjectListPath, PropertyListPathNotEmpty

        plp = PropertyListPathNotEmpty(
            [
                (
                    PathAlternative.iri(IRI("http://p")),
                    ObjectListPath.create(Var("a"), Var("b")),
                )
            ]
        )
        assert TSSP(Var("s"), plp).to_string() == "?s <http://p> ?a, ?b"


class TestGroupGraphPatternSub:
    def test_add_triples_merges_into_adjacent_block(self):
        ggps = GroupGraphPatternSub()
        ggps.add_triples([spo(o="a")])
        ggps.add_triples([spo(o="b")])
        assert len(ggps.patterns) == 1
        assert len(ggps.triples) == 2

    def test_add_pattern_then_triples_starts_new_block(self):
        ggps = GroupGraphPatternSub()
        ggps.add_triples([spo()])
        ggps.add_pattern(Filter(Expression.compare(Var("x"), ">", 1)))
        ggps.add_triples([spo(o="later")])
        assert len(ggps.patterns) == 3

    def test_prepend(self):
        ggps = GroupGraphPatternSub()
        ggps.add_triples([spo(o="second")])
        ggps.add_triples([spo(o="first")], prepend=True)
        assert ggps.triples[0].to_string().endswith("?first")

    def test_deduplicate_triples(self):
        """Needs hashable nodes - impossible in the pydantic version."""
        ggps = GroupGraphPatternSub()
        ggps.add_triples([spo(), spo(), spo(o="other")])
        ggps.deduplicate_triples()
        assert len(ggps.triples) == 2

    def test_chaining(self):
        ggps = (
            GroupGraphPatternSub()
            .add_triples([spo()])
            .add_pattern(Filter(Expression.compare(Var("x"), ">", 1)))
        )
        assert "FILTER" in ggps.to_string()


class TestGraphPatterns:
    def test_optional(self):
        assert OptionalGraphPattern(
            GroupGraphPattern.from_triples([spo()])
        ).to_string() == "OPTIONAL {\n?s <http://ex/p> ?o\n}"

    def test_minus(self):
        assert "MINUS {" in MinusGraphPattern(
            GroupGraphPattern.from_triples([spo()])
        ).to_string()

    def test_graph(self):
        assert GraphGraphPattern(
            IRI("http://g"), GroupGraphPattern.from_triples([spo()])
        ).to_string().startswith("GRAPH <http://g> {")

    def test_service(self):
        assert ServiceGraphPattern(
            IRI("http://endpoint"), GroupGraphPattern.from_triples([spo()])
        ).to_string().startswith("SERVICE <http://endpoint> {")

    def test_service_silent(self):
        assert ServiceGraphPattern(
            IRI("http://e"), GroupGraphPattern.from_triples([spo()]), silent=True
        ).to_string().startswith("SERVICE SILENT ")

    def test_union(self):
        pattern = GroupOrUnionGraphPattern(
            [
                GroupGraphPattern.from_triples([spo(o="a")]),
                GroupGraphPattern.from_triples([spo(o="b")]),
            ]
        )
        assert "UNION" in pattern.to_string()

    def test_filter_brackets_bare_expression(self):
        assert Filter(Expression.compare(Var("count"), "=", 101)).to_string() == (
            "FILTER (?count = 101)"
        )

    def test_bind(self):
        assert Bind(Expression.from_primary_expression(Var("x")), Var("y")).to_string() == (
            "BIND(?x AS ?y)"
        )


class TestInlineData:
    def test_one_var(self):
        data = InlineData(
            InlineDataOneVar(Var("x"), [IRI("http://a"), IRI("http://b")])
        )
        assert data.to_string() == "VALUES ?x { <http://a> <http://b> }"

    def test_undef(self):
        from sparql_grammar import UNDEF

        assert "UNDEF" in InlineDataOneVar(Var("x"), [UNDEF]).to_string()

    def test_full_multi_var(self):
        data = InlineDataFull(
            [Var("a"), Var("b")],
            [[IRI("http://1"), RDFLiteral("x")], [IRI("http://2"), RDFLiteral("y")]],
        )
        assert data.to_string() == (
            '(?a ?b) { (<http://1> "x") (<http://2> "y") }'
        )


class TestQueryForms:
    def test_select(self):
        query = SelectQuery(
            SelectClause.create(Var("s")),
            WhereClause.from_triples([spo()]),
        )
        assert query.to_string() == (
            "SELECT ?s\nWHERE {\n?s <http://ex/p> ?o\n}"
        )

    def test_select_star(self):
        assert SelectClause().to_string() == "SELECT *"

    def test_select_distinct(self):
        assert SelectClause.create(Var("s"), distinct=True).to_string() == (
            "SELECT DISTINCT ?s"
        )

    def test_select_reduced(self):
        assert SelectClause.create(Var("s"), reduced=True).to_string() == (
            "SELECT REDUCED ?s"
        )

    def test_select_expression_as_var(self):
        from sparql_grammar import Aggregate

        clause = SelectClause.create(
            Var("g"),
            (Expression.from_primary_expression(Aggregate.count()), Var("n")),
        )
        assert clause.to_string() == "SELECT ?g (COUNT(*) AS ?n)"

    def test_construct(self):
        query = ConstructQuery(
            ConstructTemplate(ConstructTriples.from_spo_list([(Var("s"), IRI("http://p"), Var("o"))])),
            WhereClause.from_triples([spo()]),
        )
        assert query.to_string().startswith("CONSTRUCT {")
        assert "WHERE {" in query.to_string()

    def test_construct_where_shorthand(self):
        query = ConstructQuery(
            where_template=ConstructTemplate(
                ConstructTriples.from_spo_list([(Var("s"), IRI("http://p"), Var("o"))])
            )
        )
        assert query.to_string().startswith("CONSTRUCT \nWHERE {")

    def test_describe(self):
        assert DescribeQuery([IRI("http://x")]).to_string() == "DESCRIBE <http://x>"

    def test_describe_star(self):
        assert DescribeQuery().to_string() == "DESCRIBE *"

    def test_ask(self):
        assert AskQuery(WhereClause.from_triples([spo()])).to_string().startswith("ASK\nWHERE")

    def test_subselect(self):
        sub = SubSelect(SelectClause.create(Var("s")), WhereClause.from_triples([spo()]))
        assert GroupGraphPattern(sub).to_string().startswith("{\nSELECT ?s")

    def test_dataset_clauses(self):
        query = SelectQuery(
            SelectClause.create(Var("s")),
            WhereClause.from_triples([spo()]),
            dataset_clauses=[
                DatasetClause.create(IRI("http://g1")),
                DatasetClause.create(IRI("http://g2"), named=True),
            ],
        )
        assert "FROM <http://g1>" in query.to_string()
        assert "FROM NAMED <http://g2>" in query.to_string()

    def test_solution_modifier_empty_renders_nothing(self):
        assert SolutionModifier().to_string() == ""

    def test_full_solution_modifier(self):
        modifier = SolutionModifier(
            group_by=GroupClause.create(Var("g")),
            having=HavingClause.create(Expression.compare(Var("n"), ">", 1)),
            order_by=OrderClause.create(OrderCondition.desc(Var("n"))),
            limit_offset=LimitOffsetClauses.create(limit=10, offset=20),
        )
        assert modifier.to_string() == (
            "\nGROUP BY ?g\nHAVING (?n > 1)\nORDER BY DESC(?n)\nLIMIT 10 OFFSET 20"
        )

    def test_having_renders(self):
        """HAVING existed but was never rendered in the pydantic version."""
        assert "HAVING" in SolutionModifier(
            having=HavingClause.create(Expression.compare(Var("n"), ">", 1))
        ).to_string()

    def test_order_asc(self):
        assert OrderCondition.asc(Var("x")).to_string() == "ASC(?x)"

    def test_order_bare_var(self):
        assert OrderCondition(Var("x")).to_string() == "?x"


class TestPrologue:
    def test_prefix_decl(self):
        assert PrefixDecl.create("skos", "http://www.w3.org/2004/02/skos/core#").to_string() == (
            "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>"
        )

    def test_prologue_from_prefixes(self):
        """The pydantic version could not emit PREFIX declarations at all."""
        prologue = Prologue.from_prefixes({"ex": "http://ex/", "skos": "http://skos/"})
        assert prologue.to_string() == (
            "PREFIX ex: <http://ex/>\nPREFIX skos: <http://skos/>\n"
        )

    def test_version_decl(self):
        """New in SPARQL 1.2."""
        assert VersionDecl("1.2").to_string() == 'VERSION "1.2"'

    def test_full_query_unit(self):
        unit = QueryUnit(
            Query(
                SelectQuery(SelectClause.create(Var("s")), WhereClause.from_triples([spo()])),
                Prologue.from_prefixes({"ex": "http://ex/"}),
            )
        )
        assert unit.to_string().startswith("PREFIX ex: <http://ex/>\nSELECT ?s")

    def test_values_clause_empty_renders_nothing(self):
        assert ValuesClause().to_string() == ""


class TestSparql12:
    def test_reified_triple(self):
        assert ReifiedTriple(Var("s"), IRI("http://p"), Var("o")).to_string() == (
            "<<?s <http://p> ?o>>"
        )

    def test_reified_triple_with_reifier(self):
        assert ReifiedTriple(
            Var("s"), IRI("http://p"), Var("o"), Reifier(Var("r"))
        ).to_string() == "<<?s <http://p> ?o ~?r>>"

    def test_bare_reifier(self):
        assert Reifier().to_string() == "~"

    def test_triple_term(self):
        assert TripleTerm(Var("s"), IRI("http://p"), Var("o")).to_string() == (
            "<<(?s <http://p> ?o)>>"
        )

    def test_annotation_block(self):
        from sparql_grammar import AnnotationBlockPath, AnnotationPath, PropertyListPathNotEmpty

        annotation = AnnotationPath(
            [AnnotationBlockPath(PropertyListPathNotEmpty.create(IRI("http://p"), Var("o")))]
        )
        assert annotation.to_string() == " {| <http://p> ?o |}"

    def test_triple_term_as_object(self):
        triple = TSSP.from_spo(
            Var("s"), IRI("http://ex/says"), TripleTerm(Var("a"), IRI("http://b"), Var("c"))
        )
        assert triple.to_string() == "?s <http://ex/says> <<(?a <http://b> ?c)>>"


class TestUpdate:
    """None of this was constructible in the pydantic version."""

    def _tss(self):
        return [TSS.from_spo(IRI("http://ex/s"), "a", IRI("http://ex/C"))]

    def test_insert_data(self):
        assert InsertData.from_tss_list(self._tss()).to_string() == (
            "INSERT DATA {\n<http://ex/s> a <http://ex/C>\n}"
        )

    def test_delete_data(self):
        assert DeleteData.from_tss_list(self._tss()).to_string().startswith("DELETE DATA {")

    def test_delete_where(self):
        assert DeleteWhere.from_tss_list(self._tss()).to_string().startswith("DELETE WHERE {")

    def test_modify(self):
        modify = Modify(
            where=GroupGraphPattern.from_triples([spo()]),
            delete_clause=DeleteClause(QuadPattern(Quads.from_tss_list(self._tss()))),
            insert_clause=InsertClause(QuadPattern(Quads.from_tss_list(self._tss()))),
            with_iri=IRI("http://ex/g"),
        )
        rendered = modify.to_string()
        assert rendered.startswith("WITH <http://ex/g>")
        assert "DELETE {" in rendered and "INSERT {" in rendered and "WHERE {" in rendered

    def test_modify_requires_a_clause(self):
        with pytest.raises(ValidationError, match="requires a DELETE clause"):
            Modify(where=GroupGraphPattern.from_triples([])).validate("full")

    def test_load(self):
        assert Load(IRI("http://d.ttl"), into=GraphRef(IRI("http://g"))).to_string() == (
            "LOAD <http://d.ttl> INTO GRAPH <http://g>"
        )

    def test_clear_all(self):
        assert Clear(GraphRefAll(GraphRefTarget.ALL)).to_string() == "CLEAR ALL"

    def test_drop_silent_graph(self):
        assert Drop(GraphRefAll.graph(IRI("http://g")), silent=True).to_string() == (
            "DROP SILENT GRAPH <http://g>"
        )

    def test_create(self):
        assert Create(GraphRef(IRI("http://g"))).to_string() == "CREATE GRAPH <http://g>"

    @pytest.mark.parametrize(
        "cls,keyword", [(Add_, "ADD"), (Move, "MOVE"), (Copy, "COPY")]
    )
    def test_graph_to_graph(self, cls, keyword):
        operation = cls(GraphOrDefault.default(), GraphOrDefault(IRI("http://g")))
        assert operation.to_string() == f"{keyword} DEFAULT TO <http://g>"

    def test_multi_operation_update(self):
        unit = UpdateUnit(
            Update(
                [DeleteData.from_tss_list(self._tss()), InsertData.from_tss_list(self._tss())],
                Prologue.from_prefixes({"ex": "http://ex/"}),
            )
        )
        rendered = unit.to_string()
        assert rendered.startswith("PREFIX ex: <http://ex/>")
        assert " ;\n" in rendered


class TestScaleAndCoverage:
    def test_renders_10k_triples_without_recursion_error(self):
        """The linked-list model raised RecursionError somewhere past 1000."""
        block = TriplesBlock.from_spo_list(
            [(Var(f"s{i}"), IRI("http://p"), Var(f"o{i}")) for i in range(10_000)]
        )
        assert len(block.to_string().splitlines()) == 10_000

    def test_render_scales_linearly(self):
        import timeit

        def render(n):
            block = TriplesBlock.from_spo_list(
                [(Var(f"s{i}"), IRI("http://p"), Var(f"o{i}")) for i in range(n)]
            )
            return timeit.timeit(block.to_string, number=20) / 20

        ratio = render(2000) / render(500)
        # 4x the input should cost about 4x, not 16x as the quadratic model did
        assert ratio < 8, f"rendering scaled super-linearly: {ratio:.1f}x for 4x input"

    def test_default_recursion_limit_is_enough(self):
        assert sys.getrecursionlimit() == 1000  # not raised by this library

    def test_every_production_is_implemented(self):
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from sparql_grammar._base import ALIASES, REGISTRY
        from tools.bnf import parse_bnf

        implemented = {**REGISTRY, **ALIASES}
        missing = [p.name for p in parse_bnf() if p.name not in implemented]
        assert missing == []
