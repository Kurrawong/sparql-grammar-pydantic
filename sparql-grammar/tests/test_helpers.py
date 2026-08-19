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

    def test_literal_numbers_follow_the_python_type(self):
        """The Python type decides, so nothing is read out of the text."""
        assert literal(5).to_string() == "5"
        assert literal(-5).to_string() == "-5"
        assert literal(1.5).to_string() == "1.5"
        assert literal(-1.5).to_string() == "-1.5"
        assert literal(1e30).to_string() == "1e+30"
        assert literal("5").to_string() == '"5"'  # a string stays a string

    def test_signed_numbers_validate(self):
        """A negative number needs the signed terminal, not a minus inside INTEGER."""
        for value in (-5, 5, -1.5, 1.5, -1e30, 1e30):
            literal(value).validate("terminals")

    def test_literal_refuses_infinity_and_nan(self):
        """SPARQL has no syntax for these, so there is nothing honest to render."""
        for value in (float("inf"), float("-inf"), float("nan")):
            with pytest.raises(ValueError, match="no syntax for"):
                literal(value)

    def test_numeric_literal_refuses_a_bool(self):
        """``bool`` subclasses ``int``, so the guard has to be explicit."""
        from sparql_grammar import numeric_literal

        with pytest.raises(TypeError, match="BooleanLiteral"):
            numeric_literal(True)
        assert literal(True).to_string() == "true"

    def test_lang_or_datatype_beats_the_numeric_form(self):
        assert literal(5, datatype=XSD_DT).to_string() == f'"5"^^<{XSD_DT}>'

    @pytest.mark.parametrize("text", ["?s", "$s", "<http://x>", "http://x", "hello", "a"])
    def test_term_never_reads_a_string(self, text):
        """The change this file's neighbours exist to protect: no guessing at all.

        Each of these used to become *something* - a Var, an IRI, a literal - chosen
        by looking at the text. Now the caller says which.
        """
        with pytest.raises(TypeError, match="never read as a term"):
            term(text)

    def test_the_refusal_names_the_constructor_to_use(self):
        """The error has to carry the fix, or explicitness is just friction."""
        with pytest.raises(TypeError, match=r"var\('s'\)"):
            term("?s")
        with pytest.raises(TypeError, match=r"iri\('http://x'\)"):
            term("<http://x>")
        with pytest.raises(TypeError, match=r"literal\('hello'\)"):
            term("hello")

    def test_term_refuses_other_python_types(self):
        with pytest.raises(TypeError, match="not a term"):
            term({"a": 1})

    def test_term_passes_nodes_through(self):
        node = IRI("http://x")
        assert term(node) is node


class TestVariableOnlySlots:
    """Where the grammar allows nothing but a variable, a name is unambiguous.

    This is the one place a string is still accepted, and the reason is narrow: there
    is no second reading of it to get wrong.
    """

    def test_projection(self):
        assert select("?s", where=[(var("s"), var("p"), var("o"))]).to_string().startswith(
            "SELECT ?s"
        )

    def test_subselect_projection(self):
        assert subselect("s", where=[(var("s"), var("p"), var("o"))]).to_string().startswith(
            "SELECT ?s"
        )

    def test_bind_target(self):
        assert bind(literal(1), "?x").to_string() == "BIND(1 AS ?x)"

    def test_values_variables(self):
        assert values("x", [literal(1)]).to_string() == "VALUES ?x { 1 }"
        assert values(["x", "y"], [[literal(1), literal(2)]]).to_string() == (
            "VALUES (?x ?y) { (1 2) }"
        )


class TestTriples:
    def test_triple_coerces_all_positions(self):
        assert triple(var("s"), iri("http://p"), var("o")).to_string() == "?s <http://p> ?o"

    def test_predicate_refuses_a_bare_string(self):
        """Predicate position takes a variable or an IRI, and text does not say which."""
        with pytest.raises(TypeError, match="never read as a term"):
            triple(var("s"), "http://p", var("o"))

    def test_predicate_refusal_does_not_suggest_a_literal(self):
        """A literal cannot be a predicate, so the message must not offer one."""
        with pytest.raises(TypeError, match=r"iri\('http://p'\)") as caught:
            triple(var("s"), "http://p", var("o"))
        assert "literal()" not in str(caught.value)

    def test_predicate_variable(self):
        assert triple(var("s"), var("p"), var("o")).to_string() == "?s ?p ?o"

    def test_predicate_a_shorthand(self):
        assert triple(var("s"), "a", iri("http://C")).to_string() == "?s a <http://C>"

    def test_triples_block(self):
        block = triples(
            [(var("s"), "a", iri("http://C")), (var("s"), iri("http://p"), var("o"))]
        )
        assert block.to_string() == "?s a <http://C> .\n?s <http://p> ?o"

    def test_tss_and_tssp_returns_both_forms(self):
        template, pattern = tss_and_tssp(var("s"), iri("http://p"), var("o"))
        assert isinstance(template, TriplesSameSubject)
        assert isinstance(pattern, TriplesSameSubjectPath)
        assert template.to_string() == pattern.to_string()


class TestPatternAssembly:
    def test_tuple_is_one_triple_list_is_many_patterns(self):
        sub = group(
            (var("s"), iri("http://p"), var("o")), (var("s"), iri("http://q"), var("o2"))
        )
        assert len(sub.triples) == 2
        assert len(sub.patterns) == 1  # merged into a single block

    def test_mixed_patterns_keep_order(self):
        sub = group(
            (var("s"), iri("http://p"), var("o")),
            optional((var("s"), iri("http://q"), var("o2"))),
            filter_(bound(var("o"))),
        )
        rendered = sub.to_string()
        assert rendered.index("OPTIONAL") < rendered.index("FILTER")

    def test_optional(self):
        assert optional((var("s"), iri("http://p"), var("o"))).to_string() == (
            "OPTIONAL {\n?s <http://p> ?o\n}"
        )

    def test_minus(self):
        assert minus((var("s"), iri("http://p"), var("o"))).to_string().startswith("MINUS {")

    def test_union_one_arm_per_argument(self):
        pattern = union(
            (var("s"), iri("http://p"), var("o")), (var("s"), iri("http://q"), var("o"))
        )
        assert len(pattern.group_graph_patterns) == 2
        assert "UNION" in pattern.to_string()

    def test_graph(self):
        assert graph(var("g"), (var("s"), var("p"), var("o"))).to_string() == (
            "GRAPH ?g {\n?s ?p ?o\n}"
        )

    def test_service_silent(self):
        pattern = service(iri("http://e"), (var("s"), var("p"), var("o")), silent=True)
        rendered = pattern.to_string()
        assert rendered.startswith("SERVICE SILENT <http://e>")

    def test_exists_and_not_exists(self):
        assert filter_(exists((var("s"), var("p"), var("o")))).to_string().startswith(
            "FILTER EXISTS"
        )
        assert filter_(not_exists((var("s"), var("p"), var("o")))).to_string().startswith(
            "FILTER NOT EXISTS"
        )

    def test_bind(self):
        assert bind(var("x"), var("y")).to_string() == "BIND(?x AS ?y)"

    def test_values_single_var(self):
        assert values("g", [iri("http://a"), iri("http://b")]).to_string() == (
            "VALUES ?g { <http://a> <http://b> }"
        )

    def test_values_multi_var(self):
        rendered = values(["a", "b"], [[iri("http://1"), literal("x")]]).to_string()
        assert rendered == 'VALUES (?a ?b) { (<http://1> "x") }'


class TestExpressionHelpers:
    def test_regex_wraps_text_in_str(self):
        assert filter_(regex(var("label"), "water")).to_string() == (
            'FILTER REGEX(STR(?label), "water")'
        )

    def test_regex_with_flags(self):
        assert 'REGEX(STR(?l), "w", "i")' in filter_(regex(var("l"), "w", "i")).to_string()

    def test_count_star_and_var(self):
        assert count().to_string() == "COUNT(*)"
        assert count(var("x")).to_string() == "COUNT(?x)"
        assert count(var("x"), distinct=True).to_string() == "COUNT(DISTINCT ?x)"

    def test_one_arg_builtins_coerce(self):
        assert filter_(bound(var("x"))).to_string() == "FILTER BOUND(?x)"
        assert filter_(is_blank(var("x"))).to_string() == "FILTER isBLANK(?x)"
        assert filter_(lang(var("x"))).to_string() == "FILTER LANG(?x)"

    def test_same_term(self):
        assert filter_(same_term(var("a"), var("b"))).to_string() == "FILTER sameTerm(?a, ?b)"

    def test_negated_builtin(self):
        assert filter_(Expression.negate(is_blank(var("x")))).to_string() == (
            "FILTER (!isBLANK(?x))"
        )


class TestQuerySkeletons:
    def test_minimal_select(self):
        query = select(var("s"), where=[(var("s"), "a", iri("http://C"))])
        assert isinstance(query, SelectQuery)
        assert query.to_string() == "SELECT ?s\nWHERE {\n?s a <http://C>\n}"

    def test_select_star(self):
        assert select(where=[(var("s"), var("p"), var("o"))]).to_string().startswith("SELECT *")

    def test_select_with_prefixes_returns_query_unit(self):
        query = select(
            var("s"), where=[(var("s"), var("p"), var("o"))], prefixes={"ex": "http://ex/"}
        )
        assert isinstance(query, QueryUnit)
        assert query.to_string().startswith("PREFIX ex: <http://ex/>")

    def test_select_modifiers(self):
        query = select(
            var("s"),
            where=[(var("s"), var("p"), var("o"))],
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
            var("s"),
            where=[(var("s"), var("p"), var("o"))],
            from_=iri("http://g1"),
            from_named=[iri("http://g2")],
        )
        assert "FROM <http://g1>" in query.to_string()
        assert "FROM NAMED <http://g2>" in query.to_string()

    def test_group_by_and_having(self):
        query = select(
            var("g"),
            (Expression.from_primary_expression(count()), var("n")),
            where=[(var("s"), var("p"), var("o"))],
            group_by=var("g"),
            having=Expression.compare(var("n"), ">", 1),
        )
        rendered = query.to_string()
        assert "GROUP BY ?g" in rendered
        assert "HAVING (?n > 1)" in rendered

    def test_construct(self):
        query = construct(
            [(var("s"), iri("http://p"), var("o"))],
            where=[(var("s"), iri("http://p"), var("o"))],
        )
        assert isinstance(query, ConstructQuery)
        assert query.to_string().startswith("CONSTRUCT {")

    def test_construct_reuses_template_as_where(self):
        query = construct([(var("s"), iri("http://p"), var("o"))])
        rendered = query.to_string()
        assert rendered.count("?s <http://p> ?o") == 2

    def test_subselect_nests(self):
        inner = subselect(var("s"), where=[(var("s"), var("p"), var("o"))], limit=5)
        assert isinstance(inner, SubSelect)
        query = select(var("s"), where=[group(inner)])
        assert "SELECT ?s" in query.to_string()


class TestUpdateSkeletons:
    def test_insert_data(self):
        assert insert_data([(iri("http://s"), iri("http://p"), literal("v"))]).to_string() == (
            'INSERT DATA {\n<http://s> <http://p> "v"\n}'
        )

    def test_delete_data(self):
        assert delete_data([(iri("http://s"), "a", iri("http://C"))]).to_string().startswith(
            "DELETE DATA {"
        )

    def test_delete_where(self):
        assert delete_where([(var("s"), iri("http://p"), var("o"))]).to_string().startswith(
            "DELETE WHERE {"
        )

    def test_modify(self):
        operation = modify(
            where=[(var("s"), iri("ex:old"), var("o"))],
            delete=[(var("s"), iri("ex:old"), var("o"))],
            insert=[(var("s"), iri("ex:new"), var("o"))],
            prefixes={"ex": "http://ex/"},
        )
        rendered = operation.to_string()
        assert rendered.startswith("PREFIX ex: <http://ex/>")
        assert "DELETE {" in rendered and "INSERT {" in rendered

    def test_multi_operation_update(self):
        request = update(
            delete_data([(iri("http://s"), "a", iri("http://C"))]),
            insert_data([(iri("http://s"), "a", iri("http://D"))]),
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

        ends_at = (var("focus_node"), iri("<ex:ends_at>"), var("dt_1_end"))
        starts_at = (var("focus_node"), iri("<ex:starts_at>"), var("dt_1_start"))
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
        query = select(var("s"), where=[(var("s"), var("p"), var("o"))], limit=10)
        query.solution_modifier.limit_offset.limit_clause.limit = INTEGER("99")
        assert "LIMIT 99" in query.to_string()

    def test_result_is_hashable(self):
        a = triple(var("s"), iri("http://p"), var("o"))
        b = triple(var("s"), iri("http://p"), var("o"))
        assert len({a, b}) == 1

    def test_group_result_supports_incremental_assembly(self):
        sub = group((var("s"), var("p"), var("o")))
        assert isinstance(sub, GroupGraphPatternSub)
        sub.add_pattern(filter_(bound(var("o"))))
        assert "FILTER" in sub.to_string()
