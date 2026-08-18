"""Terms, property paths, and expressions."""

from __future__ import annotations

import pytest

from sparql_grammar import (
    IRI,
    INTEGER,
    Aggregate,
    AggregateFunction,
    BooleanLiteral,
    BuiltInCall,
    Expression,
    ExprTripleTerm,
    Node,
    PathAlternative,
    PathMod,
    RDFLiteral,
    RegexExpression,
    ValidationError,
    Var,
    production,
)


class TestTerms:
    def test_var_default_sigil(self):
        assert Var("s").to_string() == "?s"

    def test_var_dollar_sigil(self):
        assert Var("s", "$").to_string() == "$s"

    def test_var_from_string(self):
        assert Var.from_string("?s") == Var("s")
        assert Var.from_string("$s") == Var("s", "$")
        assert Var.from_string("s") == Var("s")

    def test_var_keyword_matches_old_api(self):
        # prez constructs Var(value="x") in 132 places
        assert Var(value="x").to_string() == "?x"

    def test_iri(self):
        assert IRI("http://ex/p").to_string() == "<http://ex/p>"

    def test_iri_keyword_matches_old_api(self):
        assert IRI(value="http://ex/p").to_string() == "<http://ex/p>"

    def test_iri_prefixed(self):
        assert IRI.prefixed("skos", "prefLabel").to_string() == "skos:prefLabel"
        assert IRI.prefixed("ex").to_string() == "ex:"

    def test_plain_literal(self):
        assert RDFLiteral("hi").to_string() == '"hi"'

    def test_language_literal(self):
        assert RDFLiteral.langed("hi", "en").to_string() == '"hi"@en'

    def test_language_literal_with_direction(self):
        # SPARQL 1.2 base direction
        assert RDFLiteral.langed("مرحبا", "ar--rtl").to_string() == '"مرحبا"@ar--rtl'

    def test_typed_literal(self):
        assert (
            RDFLiteral.typed("1", "http://www.w3.org/2001/XMLSchema#integer").to_string()
            == '"1"^^<http://www.w3.org/2001/XMLSchema#integer>'
        )

    def test_boolean_literal(self):
        assert BooleanLiteral(True).to_string() == "true"
        assert BooleanLiteral(False).to_string() == "false"


class TestPaths:
    P = PathAlternative

    def test_single_predicate(self):
        assert self.P.iri(IRI("http://ex/p")).to_string() == "<http://ex/p>"

    def test_rdf_type_shorthand(self):
        assert self.P.iri("a").to_string() == "a"

    def test_inverse(self):
        assert self.P.inverse(IRI("http://ex/p")).to_string() == "^<http://ex/p>"

    def test_sequence(self):
        assert (
            self.P.seq(IRI("http://ex/p"), IRI("http://ex/q")).to_string()
            == "<http://ex/p>/<http://ex/q>"
        )

    def test_alternative(self):
        assert (
            self.P.alt(IRI("http://ex/p"), IRI("http://ex/q")).to_string()
            == "<http://ex/p>|<http://ex/q>"
        )

    def test_modifiers(self):
        assert self.P.mod(IRI("http://ex/p"), "*").to_string() == "<http://ex/p>*"
        assert self.P.mod(IRI("http://ex/p"), "+").to_string() == "<http://ex/p>+"
        assert (
            self.P.mod(IRI("http://ex/p"), PathMod.ZERO_OR_ONE).to_string()
            == "<http://ex/p>?"
        )

    def test_negated_property_set(self):
        assert (
            self.P.negated(IRI("http://ex/p"), IRI("http://ex/q")).to_string()
            == "!(<http://ex/p>|<http://ex/q>)"
        )

    def test_negated_single_renders_bare(self):
        assert self.P.negated(IRI("http://ex/p")).to_string() == "!<http://ex/p>"

    def test_alternative_of_sequences_composes(self):
        # this is prez's create_tssp_alt_or_alt_inverse, in one call
        assert (
            self.P.alt(
                self.P.seq(IRI("http://a"), IRI("http://b")),
                self.P.inverse(IRI("http://c")),
            ).to_string()
            == "<http://a>/<http://b>|^<http://c>"
        )

    def test_prefixed_names_in_paths(self):
        assert (
            self.P.seq(IRI.prefixed("skos", "broader"), "a").to_string()
            == "skos:broader/a"
        )


class TestExpressionBuilders:
    def test_compare(self):
        # count.py:114 in prez spells this out over 39 lines
        assert Expression.compare(Var("count"), "=", 101).to_string() == "?count = 101"

    def test_compare_all_operators(self):
        for operator in ("=", "!=", "<", ">", "<=", ">="):
            assert (
                Expression.compare(Var("a"), operator, 1).to_string()
                == f"?a {operator} 1"
            )

    def test_and_chain(self):
        assert (
            Expression.all_of(
                Expression.compare(Var("a"), ">", 1),
                Expression.compare(Var("b"), "<", 10),
            ).to_string()
            == "?a > 1 && ?b < 10"
        )

    def test_or_chain(self):
        assert (
            Expression.any_of(
                Expression.compare(Var("a"), "=", 1),
                Expression.compare(Var("b"), "=", 2),
            ).to_string()
            == "?a = 1 || ?b = 2"
        )

    def test_or_inside_and_is_bracketed(self):
        assert (
            Expression.all_of(
                Expression.any_of(
                    Expression.compare(Var("a"), "=", 1),
                    Expression.compare(Var("a"), "=", 2),
                ),
                Expression.compare(Var("b"), ">", 0),
            ).to_string()
            == "(?a = 1 || ?a = 2) && ?b > 0"
        )

    def test_negate_builtin(self):
        # search_fuseki_fts.py:266 spells this out over 37 lines
        assert (
            Expression.negate(BuiltInCall.create("isBLANK", Var("focus"))).to_string()
            == "!isBLANK(?focus)"
        )

    def test_negate_compound_is_bracketed(self):
        assert (
            Expression.negate(Expression.compare(Var("a"), "=", 1)).to_string()
            == "!(?a = 1)"
        )

    def test_in_expression(self):
        assert (
            Expression.in_(Var("x"), [IRI("http://a"), IRI("http://b")]).to_string()
            == "?x IN (<http://a>, <http://b>)"
        )

    def test_not_in_expression(self):
        assert Expression.in_(Var("x"), [1, 2], negated=True).to_string() == (
            "?x NOT IN (1, 2)"
        )

    def test_python_values_are_lifted(self):
        assert Expression.compare(Var("a"), "=", "text").to_string() == '?a = "text"'
        assert Expression.compare(Var("a"), "=", True).to_string() == "?a = true"
        assert Expression.compare(Var("a"), "=", 5).to_string() == "?a = 5"

    def test_from_primary_expression(self):
        # the constructor prez uses 25 times
        assert Expression.from_primary_expression(Var("x")).to_string() == "?x"

    def test_expression_is_alias_of_conditional_or(self):
        from sparql_grammar import ConditionalOrExpression

        assert Expression is ConditionalOrExpression


class TestBuiltInCalls:
    def test_simple_call(self):
        assert BuiltInCall.create("STR", Var("x")).to_string() == "STR(?x)"

    def test_multi_argument_call(self):
        assert (
            BuiltInCall.create("CONTAINS", Var("a"), RDFLiteral("x")).to_string()
            == 'CONTAINS(?a, "x")'
        )

    def test_zero_argument_call(self):
        assert BuiltInCall.create("NOW").to_string() == "NOW()"

    @pytest.mark.parametrize(
        "name,args,expected",
        [
            ("LANGDIR", 1, "LANGDIR(?a0)"),
            ("STRLANGDIR", 3, "STRLANGDIR(?a0, ?a1, ?a2)"),
            ("hasLANG", 1, "hasLANG(?a0)"),
            ("hasLANGDIR", 1, "hasLANGDIR(?a0)"),
            ("isTRIPLE", 1, "isTRIPLE(?a0)"),
            ("TRIPLE", 3, "TRIPLE(?a0, ?a1, ?a2)"),
            ("SUBJECT", 1, "SUBJECT(?a0)"),
            ("PREDICATE", 1, "PREDICATE(?a0)"),
            ("OBJECT", 1, "OBJECT(?a0)"),
        ],
    )
    def test_sparql_12_builtins(self, name, args, expected):
        call = BuiltInCall.create(name, *[Var(f"a{i}") for i in range(args)])
        assert call.to_string() == expected

    def test_regex(self):
        assert (
            RegexExpression(
                Expression.from_primary_expression(
                    BuiltInCall.create("STR", Var("label"))
                ),
                Expression.from_primary_expression(RDFLiteral("foo")),
            ).to_string()
            == 'REGEX(STR(?label), "foo")'
        )

    def test_expr_triple_term(self):
        assert (
            ExprTripleTerm(Var("s"), IRI("http://ex/p"), Var("o")).to_string()
            == "<<(?s <http://ex/p> ?o)>>"
        )


class TestAggregates:
    def test_count_star(self):
        """COUNT(*) could not be constructed at all in the pydantic version."""
        assert Aggregate.count().to_string() == "COUNT(*)"

    def test_count_distinct_var(self):
        assert Aggregate.count(Var("x"), distinct=True).to_string() == (
            "COUNT(DISTINCT ?x)"
        )

    def test_group_concat_separator(self):
        """GROUP_CONCAT with SEPARATOR was also unconstructible before."""
        assert Aggregate.create("GROUP_CONCAT", Var("x"), separator=",").to_string() == (
            'GROUP_CONCAT(?x;SEPARATOR=",")'
        )

    @pytest.mark.parametrize("name", ["SUM", "MIN", "MAX", "AVG", "SAMPLE"])
    def test_other_aggregates(self, name):
        assert Aggregate.create(name, Var("x")).to_string() == f"{name}(?x)"

    def test_separator_on_non_group_concat_is_invalid(self):
        with pytest.raises(ValidationError, match="SEPARATOR is only valid"):
            Aggregate.create("SUM", Var("x"), separator=",").validate("full")

    def test_star_on_non_count_is_invalid(self):
        with pytest.raises(ValidationError, match=r"only valid for COUNT"):
            Aggregate(AggregateFunction.SUM).validate("full")

    def test_valid_aggregates_pass(self):
        Aggregate.count().validate("full")
        Aggregate.create("GROUP_CONCAT", Var("x"), separator=",").validate("full")


class TestArithmetic:
    def test_multiplication_chain(self):
        from sparql_grammar import (
            MultiplicativeExpression,
            MultiplicativeOperator,
            UnaryExpression,
        )

        expression = MultiplicativeExpression(
            UnaryExpression(Var("a")),
            [(MultiplicativeOperator.TIMES, UnaryExpression(Var("b")))],
        )
        # the pydantic version rejected every non-empty operator list here
        assert expression.to_string() == "?a * ?b"

    def test_addition_chain(self):
        from sparql_grammar import (
            AdditiveExpression,
            AdditiveOperator,
            MultiplicativeExpression,
            UnaryExpression,
        )

        expression = AdditiveExpression(
            MultiplicativeExpression(UnaryExpression(Var("a"))),
            [
                (
                    AdditiveOperator.PLUS,
                    MultiplicativeExpression(UnaryExpression(INTEGER("1"))),
                )
            ],
        )
        assert expression.to_string() == "?a + 1"


class TestSlotsSuperRegression:
    """dataclass(slots=True) returns a new class, which breaks zero-arg super()."""

    def test_super_works_in_decorated_subclass(self):
        @production(rule="_TestSuperBase")
        class Base(Node):
            value: str

            def render(self, add) -> None:
                add(self.value)

            def _check(self, level):
                return [*super()._check(level), "base-ran"]

        @production(rule="_TestSuperChild")
        class Child(Base):
            def _check(self, level):
                return [*super()._check(level), "child-ran"]

        assert Child("x")._check("full") == ["base-ran", "child-ran"]

    def test_aggregate_check_calls_super(self):
        # concrete instance of the same trap: Aggregate._check uses super()
        Aggregate.count().validate("full")
