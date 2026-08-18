"""The helper layer: coercion rules, pattern assembly, query and update skeletons."""

from __future__ import annotations

import pytest

from sparql_grammar import (
    IRI,
    Aggregate,
    BooleanLiteral,
    ConstructQuery,
    Expression,
    GroupGraphPatternSub,
    INTEGER,
    OrderCondition,
    PNAME_LN,
    PNAME_NS,
    QueryUnit,
    RDFLiteral,
    SelectQuery,
    SubSelect,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    UpdateUnit,
    Var,
    bind,
    bound,
    construct,
    count,
    delete_data,
    delete_where,
    exists,
    filter_,
    graph,
    group,
    insert_data,
    iri,
    is_blank,
    lang,
    literal,
    minus,
    modify,
    not_exists,
    optional,
    regex,
    same_term,
    select,
    service,
    subselect,
    term,
    triple,
    triples,
    tss,
    tss_and_tssp,
    union,
    update,
    values,
    var,
)

XSD_DT = "http://www.w3.org/2001/XMLSchema#dateTime"


class TestTermCoercion:
    def test_var_accepts_sigil_or_bare(self):
        assert var("s") == var("?s") == Var("s")

    def test_var_passes_through(self):
        v = Var("s")
        assert var(v) is v

    def test_iri_plain(self):
        assert iri("http://x").to_string() == "<http://x>"

    def test_iri_angle_bracketed(self):
        assert iri("<http://x>").to_string() == "<http://x>"

    def test_iri_prefixed_name(self):
        assert isinstance(iri("skos:broader"), PNAME_LN)
        assert iri("skos:broader").to_string() == "skos:broader"

    def test_iri_prefix_only(self):
        assert isinstance(iri("skos:"), PNAME_NS)

    def test_iri_does_not_mistake_scheme_for_prefix(self):
        assert isinstance(iri("http://x"), IRI)

    def test_literal_kinds(self):
        assert isinstance(literal(True), BooleanLiteral)
        assert isinstance(literal(5), INTEGER)
        assert literal("x").to_string() == '"x"'
        assert literal("x", lang="en").to_string() == '"x"@en'
        assert literal("1", datatype=XSD_DT).to_string() == f'"1"^^<{XSD_DT}>'

    def test_term_reads_variables(self):
        assert term("?s") == Var("s")
        assert term("$s") == Var("s", "$")

    def test_term_reads_angle_bracketed_iris(self):
        assert term("<http://x>") == IRI("http://x")

    def test_term_defaults_to_literal(self):
        """No guessing from an http prefix - that would misread real literals."""
        assert term("http://x") == RDFLiteral("http://x")
        assert term("hello") == RDFLiteral("hello")

    def test_term_passes_nodes_through(self):
        node = IRI("http://x")
        assert term(node) is node


class TestTriples:
    def test_triple_coerces_all_positions(self):
        assert triple("?s", iri("http://p"), "?o").to_string() == "?s <http://p> ?o"

    def test_predicate_string_is_an_iri_not_a_literal(self):
        assert triple("?s", "http://p", "?o").to_string() == "?s <http://p> ?o"

    def test_predicate_variable(self):
        assert triple("?s", "?p", "?o").to_string() == "?s ?p ?o"

    def test_predicate_a_shorthand(self):
        assert triple("?s", "a", iri("http://C")).to_string() == "?s a <http://C>"

    def test_triples_block(self):
        block = triples([("?s", "a", iri("http://C")), ("?s", iri("http://p"), "?o")])
        assert block.to_string() == "?s a <http://C> .\n?s <http://p> ?o"

    def test_tss_and_tssp_returns_both_forms(self):
        template, pattern = tss_and_tssp("?s", iri("http://p"), "?o")
        assert isinstance(template, TriplesSameSubject)
        assert isinstance(pattern, TriplesSameSubjectPath)
        assert template.to_string() == pattern.to_string()


class TestPatternAssembly:
    def test_tuple_is_one_triple_list_is_many_patterns(self):
        sub = group(("?s", iri("http://p"), "?o"), ("?s", iri("http://q"), "?o2"))
        assert len(sub.triples) == 2
        assert len(sub.patterns) == 1  # merged into a single block

    def test_mixed_patterns_keep_order(self):
        sub = group(
            ("?s", iri("http://p"), "?o"),
            optional(("?s", iri("http://q"), "?o2")),
            filter_(bound("?o")),
        )
        rendered = sub.to_string()
        assert rendered.index("OPTIONAL") < rendered.index("FILTER")

    def test_optional(self):
        assert optional(("?s", iri("http://p"), "?o")).to_string() == (
            "OPTIONAL {\n?s <http://p> ?o\n}"
        )

    def test_minus(self):
        assert minus(("?s", iri("http://p"), "?o")).to_string().startswith("MINUS {")

    def test_union_one_arm_per_argument(self):
        pattern = union(
            ("?s", iri("http://p"), "?o"), ("?s", iri("http://q"), "?o")
        )
        assert len(pattern.group_graph_patterns) == 2
        assert "UNION" in pattern.to_string()

    def test_graph(self):
        assert graph("?g", ("?s", "?p", "?o")).to_string() == (
            "GRAPH ?g {\n?s ?p ?o\n}"
        )

    def test_service_silent(self):
        rendered = service(iri("http://e"), ("?s", "?p", "?o"), silent=True).to_string()
        assert rendered.startswith("SERVICE SILENT <http://e>")

    def test_exists_and_not_exists(self):
        assert filter_(exists(("?s", "?p", "?o"))).to_string().startswith("FILTER EXISTS")
        assert filter_(not_exists(("?s", "?p", "?o"))).to_string().startswith(
            "FILTER NOT EXISTS"
        )

    def test_bind(self):
        assert bind("?x", "?y").to_string() == "BIND(?x AS ?y)"

    def test_values_single_var(self):
        assert values("g", [iri("http://a"), iri("http://b")]).to_string() == (
            "VALUES ?g { <http://a> <http://b> }"
        )

    def test_values_multi_var(self):
        rendered = values(["a", "b"], [[iri("http://1"), literal("x")]]).to_string()
        assert rendered == 'VALUES (?a ?b) { (<http://1> "x") }'


class TestExpressionHelpers:
    def test_regex_wraps_text_in_str(self):
        assert filter_(regex("?label", "water")).to_string() == (
            'FILTER REGEX(STR(?label), "water")'
        )

    def test_regex_with_flags(self):
        assert 'REGEX(STR(?l), "w", "i")' in filter_(regex("?l", "w", "i")).to_string()

    def test_count_star_and_var(self):
        assert count().to_string() == "COUNT(*)"
        assert count("?x").to_string() == "COUNT(?x)"
        assert count("?x", distinct=True).to_string() == "COUNT(DISTINCT ?x)"

    def test_one_arg_builtins_coerce(self):
        assert filter_(bound("?x")).to_string() == "FILTER BOUND(?x)"
        assert filter_(is_blank("?x")).to_string() == "FILTER isBLANK(?x)"
        assert filter_(lang("?x")).to_string() == "FILTER LANG(?x)"

    def test_same_term(self):
        assert filter_(same_term("?a", "?b")).to_string() == "FILTER sameTerm(?a, ?b)"

    def test_negated_builtin(self):
        assert filter_(Expression.negate(is_blank("?x"))).to_string() == (
            "FILTER (!isBLANK(?x))"
        )


class TestQuerySkeletons:
    def test_minimal_select(self):
        query = select("?s", where=[("?s", "a", iri("http://C"))])
        assert isinstance(query, SelectQuery)
        assert query.to_string() == "SELECT ?s\nWHERE {\n?s a <http://C>\n}"

    def test_select_star(self):
        assert select(where=[("?s", "?p", "?o")]).to_string().startswith("SELECT *")

    def test_select_with_prefixes_returns_query_unit(self):
        query = select("?s", where=[("?s", "?p", "?o")], prefixes={"ex": "http://ex/"})
        assert isinstance(query, QueryUnit)
        assert query.to_string().startswith("PREFIX ex: <http://ex/>")

    def test_select_modifiers(self):
        query = select(
            "?s",
            where=[("?s", "?p", "?o")],
            distinct=True,
            order_by=OrderCondition.desc(var("s")),
            limit=10,
            offset=20,
        )
        rendered = query.to_string()
        assert "SELECT DISTINCT" in rendered
        assert "ORDER BY DESC(?s)" in rendered
        assert "LIMIT 10 OFFSET 20" in rendered

    def test_select_dataset_clauses(self):
        query = select(
            "?s",
            where=[("?s", "?p", "?o")],
            from_=iri("http://g1"),
            from_named=[iri("http://g2")],
        )
        assert "FROM <http://g1>" in query.to_string()
        assert "FROM NAMED <http://g2>" in query.to_string()

    def test_group_by_and_having(self):
        query = select(
            "?g",
            (Expression.from_primary_expression(count()), var("n")),
            where=[("?s", "?p", "?o")],
            group_by=var("g"),
            having=Expression.compare(var("n"), ">", 1),
        )
        rendered = query.to_string()
        assert "GROUP BY ?g" in rendered
        assert "HAVING (?n>1)" in rendered

    def test_construct(self):
        query = construct(
            [("?s", iri("http://p"), "?o")], where=[("?s", iri("http://p"), "?o")]
        )
        assert isinstance(query, ConstructQuery)
        assert query.to_string().startswith("CONSTRUCT {")

    def test_construct_reuses_template_as_where(self):
        query = construct([("?s", iri("http://p"), "?o")])
        rendered = query.to_string()
        assert rendered.count("?s <http://p> ?o") == 2

    def test_subselect_nests(self):
        inner = subselect("?s", where=[("?s", "?p", "?o")], limit=5)
        assert isinstance(inner, SubSelect)
        query = select("?s", where=[group(inner)])
        assert "SELECT ?s" in query.to_string()


class TestUpdateSkeletons:
    def test_insert_data(self):
        assert insert_data([("<http://s>", iri("http://p"), literal("v"))]).to_string() == (
            'INSERT DATA {\n<http://s> <http://p> "v"\n}'
        )

    def test_delete_data(self):
        assert delete_data([("<http://s>", "a", iri("http://C"))]).to_string().startswith(
            "DELETE DATA {"
        )

    def test_delete_where(self):
        assert delete_where([("?s", iri("http://p"), "?o")]).to_string().startswith(
            "DELETE WHERE {"
        )

    def test_modify(self):
        operation = modify(
            where=[("?s", iri("ex:old"), "?o")],
            delete=[("?s", iri("ex:old"), "?o")],
            insert=[("?s", iri("ex:new"), "?o")],
            prefixes={"ex": "http://ex/"},
        )
        rendered = operation.to_string()
        assert rendered.startswith("PREFIX ex: <http://ex/>")
        assert "DELETE {" in rendered and "INSERT {" in rendered

    def test_multi_operation_update(self):
        request = update(
            delete_data([("<http://s>", "a", iri("http://C"))]),
            insert_data([("<http://s>", "a", iri("http://D"))]),
            prefixes={"ex": "http://ex/"},
        )
        assert isinstance(request, UpdateUnit)
        assert " ;\n" in request.to_string()


class TestPrezGoldenQuery:
    """Reproduce a query the previous library generated in production.

    Source: prez test_data/cql/expected_generated_queries/example65.rq. Building this
    with the old API took a 39-line expression ladder per comparison, inside a
    103-line helper; here it is the body of one function.
    """

    def test_temporal_filter_construct(self):
        def dt(value):
            return literal(value, datatype=XSD_DT)

        ends_at = ("?focus_node", iri("<ex:ends_at>"), "?dt_1_end")
        starts_at = ("?focus_node", iri("<ex:starts_at>"), "?dt_1_start")
        start, end = "1991-10-07T08:21:06.393262+00:00", "1992-10-09T08:08:08.393473+00:00"

        query = construct(
            [ends_at, starts_at],
            where=[
                ends_at,
                starts_at,
                filter_(
                    Expression.all_of(
                        Expression.compare(var("dt_1_start"), "<", dt(start)),
                        Expression.compare(var("dt_1_end"), ">", dt(start)),
                        Expression.compare(var("dt_1_end"), "<", dt(end)),
                    )
                ),
            ],
        )

        rendered = query.to_string()
        assert rendered.startswith("CONSTRUCT {")
        assert "<ex:ends_at>" in rendered and "<ex:starts_at>" in rendered
        # one FILTER, three comparisons joined by &&
        assert rendered.count("FILTER") == 1
        assert rendered.count("&&") == 2
        assert rendered.count(f'"{start}"^^<{XSD_DT}>') == 2
        # the CONSTRUCT template and the WHERE clause both carry both triples
        assert rendered.count("?focus_node <ex:ends_at> ?dt_1_end") == 2


class TestHelpersReturnPlainNodes:
    def test_result_is_mutable_like_any_node(self):
        query = select("?s", where=[("?s", "?p", "?o")], limit=10)
        query.solution_modifier.limit_offset.limit_clause.limit = INTEGER("99")
        assert "LIMIT 99" in query.to_string()

    def test_result_is_hashable(self):
        a = triple("?s", iri("http://p"), "?o")
        b = triple("?s", iri("http://p"), "?o")
        assert len({a, b}) == 1

    def test_group_result_supports_incremental_assembly(self):
        sub = group(("?s", "?p", "?o"))
        assert isinstance(sub, GroupGraphPatternSub)
        sub.add_pattern(filter_(bound("?o")))
        assert "FILTER" in sub.to_string()
