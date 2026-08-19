"""Parse SPARQL text into grammar objects.

Requires the ``parse`` extra::

    pip install sparql-grammar[parse]

    >>> from sparql_grammar import parse
    >>> query = parse("SELECT ?s WHERE { ?s a <http://ex/C> } LIMIT 10")
    >>> query.query.query.solution_modifier.limit_offset.limit_clause.limit
    INTEGER('10')
    >>> print(query)
    SELECT ?s
    WHERE {
    ?s a <http://ex/C>
    }
    LIMIT 10

Write the SPARQL you want, get a typed tree, change it programmatically, render it
back. The parser is kept in an extra so that building and rendering queries - which
is what runs in production - needs no third-party package at all.

``grammar.lark`` is the same grammar in Lark form. It started as the SPARQL 1.1
grammar from Kurrawong/sparqlib and was extended here to SPARQL 1.2, but it is not
taken on trust: ``tools/audit.py --lark`` checks its rule set against
``spec/sparql.bnf``, the W3C grammar, and every rule it adds beyond the spec is
reported and accounted for. The whole W3C syntax corpus is round-tripped in the
tests.

LALR is the default, being roughly two orders of magnitude faster than Earley, and
currently parses everything in the corpus. ``parser="earley"`` remains available for
anything that turns out to need it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from ._base import Node
from .expressions import (
    AdditiveExpression,
    AdditiveOperator,
    Aggregate,
    AggregateFunction,
    ArgList,
    BrackettedExpression,
    BuiltIn,
    BuiltInCall,
    ConditionalAndExpression,
    ConditionalOrExpression,
    ExistsFunc,
    ExpressionList,
    ExprTripleTerm,
    FunctionCall,
    IRIOrFunction,
    MultiplicativeExpression,
    MultiplicativeOperator,
    NotExistsFunc,
    RegexExpression,
    RelationalExpression,
    RelationalOperator,
    StrReplaceExpression,
    SubstringExpression,
    UnaryExpression,
    UnaryOperator,
)
from .grammar import (
    Annotation,
    AnnotationBlock,
    AnnotationBlockPath,
    AnnotationPath,
    AskQuery,
    BaseDecl,
    Bind,
    BlankNodePropertyList,
    BlankNodePropertyListPath,
    Collection,
    CollectionPath,
    ConstructQuery,
    ConstructTemplate,
    ConstructTriples,
    DatasetClause,
    DefaultGraphClause,
    DescribeQuery,
    Filter,
    GraphGraphPattern,
    GroupClause,
    GroupCondition,
    GroupGraphPattern,
    GroupGraphPatternSub,
    GroupOrUnionGraphPattern,
    HavingClause,
    HavingCondition,
    InlineData,
    InlineDataFull,
    InlineDataOneVar,
    LimitClause,
    LimitOffsetClauses,
    MinusGraphPattern,
    NamedGraphClause,
    Object,
    ObjectList,
    ObjectListPath,
    ObjectPath,
    OffsetClause,
    OptionalGraphPattern,
    OrderClause,
    OrderCondition,
    OrderDirection,
    PrefixDecl,
    Prologue,
    PropertyListNotEmpty,
    PropertyListPathNotEmpty,
    Query,
    QueryUnit,
    ReifiedTriple,
    ReifiedTripleBlock,
    ReifiedTripleBlockPath,
    Reifier,
    SelectClause,
    SelectModifier,
    SelectQuery,
    ServiceGraphPattern,
    SolutionModifier,
    SourceSelector,
    SubSelect,
    TripleTerm,
    TripleTermData,
    TriplesBlock,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    TriplesTemplate,
    UNDEF,
    ValuesClause,
    VarOrReifierId,
    VersionDecl,
    WhereClause,
)
from .paths import (
    PathAlternative,
    PathElt,
    PathEltOrInverse,
    PathMod,
    PathNegatedPropertySet,
    PathOneInPropertySet,
    PathPrimary,
)
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
)
from .terms import IRI, BooleanLiteral, RDFLiteral, Var
from .update import (
    Add_,
    Clear,
    Copy,
    Create,
    DeleteClause,
    DeleteData,
    DeleteWhere,
    Drop,
    GraphOrDefault,
    GraphRef,
    GraphRefAll,
    GraphRefTarget,
    InsertClause,
    InsertData,
    Load,
    Modify,
    Move,
    QuadData,
    QuadPattern,
    Quads,
    QuadsNotTriples,
    Update,
    Update1,
    UpdateUnit,
    UsingClause,
)

__all__ = ["parse", "parse_query", "parse_update", "SparqlSyntaxError", "to_python_source"]

GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


def _flatten(items: list) -> list:
    """Flatten one level of the list-valued helper rules."""
    out = []
    for item in items:
        if isinstance(item, list):
            out.extend(item)
        else:
            out.append(item)
    return out


class SparqlSyntaxError(ValueError):
    """Raised when the input is not valid SPARQL."""


def _lark():
    try:
        import lark
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "parsing needs the parse extra: pip install sparql-grammar[parse]"
        ) from exc
    return lark


@lru_cache(maxsize=None)
def _parser(start: str, parser: str):
    lark = _lark()
    return lark.Lark(
        GRAMMAR_PATH.read_text(encoding="utf-8"),
        start=start,
        parser=parser,
        maybe_placeholders=False,
    )


def _is_token(value: Any) -> bool:
    return type(value).__name__ == "Token"


def _tree_data(value: Any) -> str | None:
    return getattr(value, "data", None) if hasattr(value, "children") else None


class _Builder:
    """Walks a Lark tree and builds grammar nodes.

    Written as a plain recursive walker rather than a ``lark.Transformer`` subclass so
    that the rule-to-class mapping is one readable dispatch table, and so an
    unhandled rule raises with its name instead of silently yielding a Tree.
    """

    # rules that only wrap a single child and add nothing of their own
    PASS_THROUGH = frozenset(
        {
            "unit", "path", "value_logical", "numeric_expression", "expression",
            "string", "iri", "prefixed_name", "blank_node", "var_or_iri",
            "var_or_term", "graph_node", "graph_node_path", "triples_node",
            "triples_node_path", "data_block", "data_block_value", "constraint",
            "primary_expression", "verb", "verb_path", "verb_simple", "update1",
            "graph_pattern_not_triples", "numeric_literal", "numeric_literal_unsigned",
            "numeric_literal_positive", "numeric_literal_negative",
            "select_clause_var_or_expression", "triple_term_subject",
            "triple_term_object", "triple_term_data_subject",
            "triple_term_data_object", "reified_triple_subject",
            "reified_triple_object", "expr_triple_term_subject",
            "expr_triple_term_object", "version_specifier",
        }
    )

    TERMINALS = {
        "IRIREF": lambda text: IRI(text[1:-1]),
        "PNAME_LN": PNAME_LN,
        "PNAME_NS": lambda text: PNAME_NS(text[:-1]),
        "BLANK_NODE_LABEL": lambda text: BLANK_NODE_LABEL(text[2:]),
        "VAR1": lambda text: Var(text[1:]),
        "VAR2": lambda text: Var(text[1:], "$"),
        "LANG_DIR": lambda text: LANG_DIR(text[1:]),
        "INTEGER": INTEGER,
        "DECIMAL": DECIMAL,
        "DOUBLE": DOUBLE,
        "INTEGER_POSITIVE": lambda text: INTEGER_POSITIVE(text[1:]),
        "DECIMAL_POSITIVE": lambda text: DECIMAL_POSITIVE(text[1:]),
        "DOUBLE_POSITIVE": lambda text: DOUBLE_POSITIVE(text[1:]),
        "INTEGER_NEGATIVE": lambda text: INTEGER_NEGATIVE(text[1:]),
        "DECIMAL_NEGATIVE": lambda text: DECIMAL_NEGATIVE(text[1:]),
        "DOUBLE_NEGATIVE": lambda text: DOUBLE_NEGATIVE(text[1:]),
        "STRING_LITERAL1": lambda text: STRING_LITERAL1(text[1:-1]),
        "STRING_LITERAL2": lambda text: STRING_LITERAL2(text[1:-1]),
        "STRING_LITERAL_LONG1": lambda text: STRING_LITERAL_LONG1(text[3:-3]),
        "STRING_LITERAL_LONG2": lambda text: STRING_LITERAL_LONG2(text[3:-3]),
        "NIL": lambda text: NIL(),
        "ANON": lambda text: ANON(),
        # the VALUES marker: a node, so a data block never holds a bare string
        "UNDEF": lambda text: UNDEF,
    }

    #: Keywords that carry no information once the rule is known. Matched on the
    #: token's text, not its type: the grammar spells keywords as inline regexes
    #: (``/SELECT/i``), so Lark gives them anonymous token types.
    #:
    #: Keywords that DO carry information are deliberately absent - DISTINCT,
    #: REDUCED, ASC, DESC, SILENT, GRAPH, NAMED, DEFAULT, ALL, NOT, IN, and every
    #: function name - because the rule alone does not determine the node.
    NOISE_KEYWORDS = frozenset(
        {
            "SELECT", "WHERE", "CONSTRUCT", "DESCRIBE", "ASK", "PREFIX", "BASE",
            "VERSION", "FROM", "ORDER", "BY", "GROUP", "HAVING", "LIMIT", "OFFSET",
            "VALUES", "OPTIONAL", "MINUS", "UNION", "AS", "FILTER", "BIND",
            "SERVICE", "EXISTS", "SEPARATOR", "INSERT", "DELETE", "DATA", "WITH",
            "USING", "INTO", "LOAD", "CLEAR", "DROP", "CREATE", "ADD", "MOVE",
            "COPY", "TO",
        }
    )

    #: Punctuation that only delimits. Path operators (``^ ! * + ? /``) and the
    #: comparison operators are excluded, since those are part of the node.
    NOISE_PUNCTUATION = frozenset(
        {
            "(", ")", "{", "}", "[", "]", ".", ";", ",", "^^", "<<", ">>", "<<(",
            ")>>", "{|", "|}", "~", "&&", "||", "|",
        }
    )

    def build(self, node: Any) -> Any:
        if _is_token(node):
            return self._token(node)
        rule = node.data
        if rule in self.PASS_THROUGH:
            children = self._children(node)
            return children[0] if children else None
        handler = getattr(self, f"r_{rule}", None)
        if handler is None:
            raise SparqlSyntaxError(
                f"the parser has no mapping for grammar rule {rule!r}; "
                "please report this with the query that triggered it"
            )
        return handler(self._children(node), node)

    def _children(self, node: Any) -> list:
        out = []
        for child in node.children:
            if _is_token(child) and self._is_noise(child):
                continue
            built = self.build(child)
            if built is not None:
                out.append(built)
        return out

    def _is_noise(self, token: Any) -> bool:
        if token.type in self.TERMINALS:
            return False
        text = str(token).strip()
        return (
            not text
            or text in self.NOISE_PUNCTUATION
            or text.upper() in self.NOISE_KEYWORDS
        )

    def _token(self, token: Any) -> Any:
        factory = self.TERMINALS.get(token.type)
        if factory is not None:
            return factory(str(token))
        text = str(token)
        upper = text.upper()
        if upper in ("TRUE", "FALSE"):
            return BooleanLiteral(upper == "TRUE")
        if self._is_noise(token):
            return None
        return text

    # -- prologue ---------------------------------------------------------

    def r_query_unit(self, c, _):
        return QueryUnit(c[0])

    def r_update_unit(self, c, _):
        return UpdateUnit(c[0])

    def r_query(self, c, _):
        prologue = c[0] if isinstance(c[0], Prologue) else Prologue()
        rest = c[1:] if isinstance(c[0], Prologue) else c
        query = rest[0]
        values = next((x for x in rest[1:] if isinstance(x, ValuesClause)), None)
        return Query(query, prologue, values or ValuesClause())

    def r_prologue(self, c, _):
        return Prologue(list(c))

    def r_base_decl(self, c, _):
        iri = c[-1]
        return BaseDecl(IRIREF(iri.value if isinstance(iri, IRI) else str(iri)))

    def r_prefix_decl(self, c, _):
        ns = next(x for x in c if isinstance(x, PNAME_NS))
        iri = next(x for x in c if isinstance(x, IRI))
        return PrefixDecl(ns, IRIREF(iri.value))

    def r_pname_ns(self, c, _):
        return c[0] if c else PNAME_NS("")

    def r_prefix(self, c, _):
        return None

    def r_base(self, c, _):
        return None

    def r_version_decl(self, c, _):
        return VersionDecl(c[0])

    # -- query forms ------------------------------------------------------

    def r_select_query(self, c, _):
        select = c[0]
        where = next(x for x in c if isinstance(x, WhereClause))
        modifier = next((x for x in c if isinstance(x, SolutionModifier)), None)
        datasets = [x for x in c if isinstance(x, DatasetClause)]
        return SelectQuery(select, where, modifier or SolutionModifier(), datasets)

    def r_sub_select(self, c, _):
        select = c[0]
        where = next(x for x in c if isinstance(x, WhereClause))
        modifier = next((x for x in c if isinstance(x, SolutionModifier)), None)
        values = next((x for x in c if isinstance(x, ValuesClause)), None)
        return SubSelect(select, where, modifier or SolutionModifier(), values or ValuesClause())

    def r_select_clause(self, c, _):
        modifier = None
        variables = []
        for item in c:
            if isinstance(item, str) and item.upper() in ("DISTINCT", "REDUCED"):
                modifier = SelectModifier(item.upper())
            elif item == "*":
                continue
            else:
                variables.append(item)
        return SelectClause(variables, modifier)

    def r_select_clause_expression_as_var(self, c, _):
        return (c[0], c[1])

    def r_construct_query(self, c, _):
        if len(c) == 1 and isinstance(c[0], ConstructQuery):
            return c[0]  # the inner alternative already built it
        template = next((x for x in c if isinstance(x, ConstructTemplate)), None)
        where = next((x for x in c if isinstance(x, WhereClause)), None)
        modifier = next((x for x in c if isinstance(x, SolutionModifier)), None)
        datasets = [x for x in c if isinstance(x, DatasetClause)]
        if where is None:  # CONSTRUCT WHERE { ... } shorthand
            return ConstructQuery(
                None, None, modifier or SolutionModifier(), datasets, template
            )
        return ConstructQuery(template, where, modifier or SolutionModifier(), datasets)

    r_construct_construct_template = r_construct_query

    def r_construct_triples_template(self, c, _):
        triples = next((x for x in c if isinstance(x, TriplesTemplate)), None)
        modifier = next((x for x in c if isinstance(x, SolutionModifier)), None)
        datasets = [x for x in c if isinstance(x, DatasetClause)]
        template = ConstructTemplate(
            ConstructTriples(list(triples.triples)) if triples else None
        )
        return ConstructQuery(
            None, None, modifier or SolutionModifier(), datasets, template
        )

    def r_describe_query(self, c, _):
        variables = [x for x in c if isinstance(x, (Var, IRI, PNAME_LN, PNAME_NS))]
        where = next((x for x in c if isinstance(x, WhereClause)), None)
        modifier = next((x for x in c if isinstance(x, SolutionModifier)), None)
        datasets = [x for x in c if isinstance(x, DatasetClause)]
        return DescribeQuery(variables, where, modifier or SolutionModifier(), datasets)

    def r_ask_query(self, c, _):
        where = next(x for x in c if isinstance(x, WhereClause))
        modifier = next((x for x in c if isinstance(x, SolutionModifier)), None)
        datasets = [x for x in c if isinstance(x, DatasetClause)]
        return AskQuery(where, modifier or SolutionModifier(), datasets)

    def r_dataset_clause(self, c, _):
        return DatasetClause(c[0])

    def r_default_graph_clause(self, c, _):
        return DefaultGraphClause(SourceSelector(c[0]))

    def r_named_graph_clause(self, c, _):
        return NamedGraphClause(
            SourceSelector(next(x for x in c if isinstance(x, Node)))
        )

    def r_source_selector(self, c, _):
        return c[0]

    def r_where_clause(self, c, _):
        return WhereClause(c[0])

    # -- solution modifiers ----------------------------------------------

    def r_solution_modifier(self, c, _):
        return SolutionModifier(
            group_by=next((x for x in c if isinstance(x, GroupClause)), None),
            having=next((x for x in c if isinstance(x, HavingClause)), None),
            order_by=next((x for x in c if isinstance(x, OrderClause)), None),
            limit_offset=next((x for x in c if isinstance(x, LimitOffsetClauses)), None),
        )

    def r_group_clause(self, c, _):
        return GroupClause([x if isinstance(x, GroupCondition) else GroupCondition(x) for x in c])

    def r_group_condition(self, c, _):
        return GroupCondition(c[0])

    def r_group_condition_expression_as_var(self, c, _):
        return GroupCondition(c[0], c[1] if len(c) > 1 else None)

    def r_having_clause(self, c, _):
        return HavingClause([x if isinstance(x, HavingCondition) else HavingCondition(x) for x in c])

    def r_having_condition(self, c, _):
        return HavingCondition(c[0])

    def r_order_clause(self, c, _):
        return OrderClause([x if isinstance(x, OrderCondition) else OrderCondition(x) for x in c])

    def r_order_condition(self, c, _):
        direction = None
        content = None
        for item in c:
            if isinstance(item, str) and item.upper() in ("ASC", "DESC"):
                direction = OrderDirection(item.upper())
            else:
                content = item
        return OrderCondition(content, direction)

    def r_limit_offset_clauses(self, c, _):
        return LimitOffsetClauses(
            next((x for x in c if isinstance(x, LimitClause)), None),
            next((x for x in c if isinstance(x, OffsetClause)), None),
        )

    def r_limit_clause(self, c, _):
        return LimitClause(c[0])

    def r_offset_clause(self, c, _):
        return OffsetClause(c[0])

    def r_values_clause(self, c, _):
        return ValuesClause(c[0] if c else None)

    # -- graph patterns ---------------------------------------------------

    def r_group_graph_pattern(self, c, _):
        return GroupGraphPattern(c[0] if c else GroupGraphPatternSub())

    def r_group_graph_pattern_sub(self, c, _):
        patterns = []
        for item in _flatten(c):
            if isinstance(item, TriplesBlock) and patterns and isinstance(patterns[-1], TriplesBlock):
                patterns[-1].extend(item.triples)
            else:
                patterns.append(item)
        return GroupGraphPatternSub(patterns)

    def r_triples_block(self, c, _):
        triples = []
        for item in c:
            if isinstance(item, TriplesBlock):
                triples.extend(item.triples)
            else:
                triples.append(item)
        return TriplesBlock(triples)

    def r_optional_graph_pattern(self, c, _):
        return OptionalGraphPattern(c[0])

    def r_minus_graph_pattern(self, c, _):
        return MinusGraphPattern(c[0])

    def r_graph_graph_pattern(self, c, _):
        nodes = [x for x in c if isinstance(x, Node)]
        return GraphGraphPattern(nodes[0], nodes[1])

    def r_service_graph_pattern(self, c, _):
        silent = any(isinstance(x, str) and x.upper() == "SILENT" for x in c)
        nodes = [x for x in c if isinstance(x, Node)]
        return ServiceGraphPattern(nodes[0], nodes[1], silent)

    def r_group_or_union_graph_pattern(self, c, _):
        return GroupOrUnionGraphPattern(list(c))

    def r_filter(self, c, _):
        return Filter(c[0])

    def r_bind(self, c, _):
        return Bind(c[0], c[1])

    def r_inline_data(self, c, _):
        return InlineData(c[0])

    def r_inline_data_one_var(self, c, _):
        return InlineDataOneVar(c[0], list(c[1:]))

    def r_inline_data_full(self, c, _):
        variables = []
        rows = []
        for item in c:
            if isinstance(item, list):
                rows.append(item)
            elif isinstance(item, Var):
                variables.append(item)
        return InlineDataFull(variables, rows)

    def r_data_block_value_group(self, c, _):
        # 'data_block_value_group: "(" data_block_value* ")" | NIL': as with ArgList,
        # the NIL alternative *is* the empty row rather than a value within it
        return self._expressions(c)

    # -- triples ----------------------------------------------------------

    def r_construct_template(self, c, _):
        return ConstructTemplate(c[0] if c else None)

    def r_construct_triples(self, c, _):
        triples = []
        for item in c:
            if isinstance(item, ConstructTriples):
                triples.extend(item.triples)
            else:
                triples.append(item)
        return ConstructTriples(triples)

    def r_triples_template(self, c, _):
        triples = []
        for item in c:
            if isinstance(item, TriplesTemplate):
                triples.extend(item.triples)
            else:
                triples.append(item)
        return TriplesTemplate(triples)

    def r_triples_same_subject(self, c, _):
        if isinstance(c[0], ReifiedTripleBlock):
            return c[0]
        return TriplesSameSubject(c[0], c[1] if len(c) > 1 else None)

    def r_triples_same_subject_path(self, c, _):
        if isinstance(c[0], ReifiedTripleBlockPath):
            return c[0]
        return TriplesSameSubjectPath(c[0], c[1] if len(c) > 1 else None)

    def r_property_list(self, c, _):
        return c[0] if c else None

    def r_property_list_path(self, c, _):
        return c[0] if c else None

    def r_property_list_not_empty(self, c, _):
        return PropertyListNotEmpty(self._verb_object_pairs(c, ObjectList))

    def r_property_list_path_not_empty(self, c, _):
        return PropertyListPathNotEmpty(self._verb_object_pairs(c, ObjectListPath))

    @staticmethod
    def _verb_object_pairs(children: list, object_list_type: type) -> list:
        pairs = []
        verb = None
        for item in children:
            if isinstance(item, object_list_type):
                if verb is not None:
                    pairs.append((verb, item))
                    verb = None
            elif isinstance(item, list):
                pairs.extend(item)
            else:
                verb = item
        return pairs

    def r_property_list_path_not_empty_other(self, c, _):
        return self._verb_object_pairs(c, ObjectListPath)

    def r_verb_object_list(self, c, _):
        return self._verb_object_pairs(c, ObjectList)

    def r_object_list(self, c, _):
        objects = []
        for item in c:
            objects.extend(item if isinstance(item, list) else [item])
        return ObjectList([o if isinstance(o, Object) else Object(o) for o in objects])

    def r_object(self, c, _):
        annotation = next((x for x in c if isinstance(x, Annotation)), None)
        return Object(c[0], annotation if annotation and annotation.parts else None)

    def r_object_list_path(self, c, _):
        objects = []
        for item in c:
            objects.extend(item if isinstance(item, list) else [item])
        return ObjectListPath([o if isinstance(o, ObjectPath) else ObjectPath(o) for o in objects])

    def r_object_list_path_other(self, c, _):
        return list(c)

    def r_object_path(self, c, _):
        annotation = next((x for x in c if isinstance(x, AnnotationPath)), None)
        return ObjectPath(c[0], annotation if annotation and annotation.parts else None)

    def r_collection(self, c, _):
        return Collection(list(c))

    def r_collection_path(self, c, _):
        return CollectionPath(list(c))

    def r_blank_node_property_list(self, c, _):
        return BlankNodePropertyList(c[0])

    def r_blank_node_property_list_path(self, c, _):
        return BlankNodePropertyListPath(c[0])

    # -- paths ------------------------------------------------------------

    def r_path_alternative(self, c, _):
        return PathAlternative([x for x in c if isinstance(x, Node)])

    def r_path_sequence(self, c, _):
        from .paths import PathSequence

        return PathSequence([x for x in c if isinstance(x, Node)])

    def r_path_elt(self, c, _):
        primary = c[0] if isinstance(c[0], PathPrimary) else PathPrimary(c[0])
        mod = next((PathMod(x) for x in c[1:] if isinstance(x, str) and x in "?*+"), None)
        return PathElt(primary, mod)

    def r_path_elt_or_inverse(self, c, _):
        inverse = any(isinstance(x, str) and x == "^" for x in c)
        elt = next(x for x in c if isinstance(x, PathElt))
        return PathEltOrInverse(elt, inverse)

    def r_path_primary(self, c, _):
        return PathPrimary(c[0])

    def r_path_mod(self, c, _):
        return c[0]

    def r_path_negated_property_set(self, c, _):
        return PathNegatedPropertySet(
            [
                x if isinstance(x, PathOneInPropertySet) else PathOneInPropertySet(x)
                for x in c
                if isinstance(x, Node) or x == "a"
            ]
        )

    def r_path_one_in_property_set(self, c, _):
        inverse = any(isinstance(x, str) and x == "^" for x in c)
        value = next(x for x in c if not (isinstance(x, str) and x == "^"))
        return PathOneInPropertySet(value, inverse)

    # -- expressions ------------------------------------------------------

    def r_conditional_or_expression(self, c, _):
        return ConditionalOrExpression(
            [
                x if isinstance(x, ConditionalAndExpression) else ConditionalAndExpression([x])
                for x in c
                if isinstance(x, Node)
            ]
        )

    def r_conditional_and_expression(self, c, _):
        return ConditionalAndExpression([x for x in c if isinstance(x, Node)])

    def r_relational_expression(self, c, _):
        left = c[0]
        if len(c) == 1:
            return RelationalExpression(left)
        words = [x.upper() for x in c[1:] if isinstance(x, str)]
        if "IN" in words:
            operator = (
                RelationalOperator.NOT_IN if "NOT" in words else RelationalOperator.IN
            )
        else:
            operator = RelationalOperator(next(x for x in c[1:] if isinstance(x, str)))
        return RelationalExpression(left, operator, c[-1])

    SIGNED_LITERALS = {
        INTEGER_POSITIVE: (AdditiveOperator.PLUS, INTEGER),
        DECIMAL_POSITIVE: (AdditiveOperator.PLUS, DECIMAL),
        DOUBLE_POSITIVE: (AdditiveOperator.PLUS, DOUBLE),
        INTEGER_NEGATIVE: (AdditiveOperator.MINUS, INTEGER),
        DECIMAL_NEGATIVE: (AdditiveOperator.MINUS, DECIMAL),
        DOUBLE_NEGATIVE: (AdditiveOperator.MINUS, DOUBLE),
    }

    def r_additive_expression(self, c, _):
        base = c[0]
        extra = []
        operator = None
        for item in c[1:]:
            if isinstance(item, str) and item in ("+", "-"):
                operator = AdditiveOperator(item)
                continue
            if operator is None:
                # the grammar's third branch: '?a +1' lexes the sign into the
                # literal, so recover the operator from the literal's own type
                signed = self.SIGNED_LITERALS.get(type(item))
                if signed is None:
                    continue
                sign, unsigned = signed
                extra.append(
                    (sign, self._as_multiplicative(unsigned(item.value)))
                )
                continue
            extra.append((operator, item))
            operator = None
        return AdditiveExpression(base, extra)

    @staticmethod
    def _as_multiplicative(node: Node) -> MultiplicativeExpression:
        return MultiplicativeExpression(UnaryExpression(node))

    def r_multiplicative_expression(self, c, _):
        base = c[0]
        extra = []
        operator = None
        for item in c[1:]:
            if isinstance(item, str) and item in ("*", "/"):
                operator = MultiplicativeOperator(item)
            elif operator is not None:
                extra.append((operator, item))
                operator = None
        return MultiplicativeExpression(base, extra)

    def r_unary_expression(self, c, _):
        operator = next(
            (UnaryOperator(x) for x in c if isinstance(x, str) and x in ("!", "+", "-")),
            None,
        )
        operand = next(x for x in c if not (isinstance(x, str) and x in ("!", "+", "-")))
        return UnaryExpression(operand, operator)

    def r_bracketted_expression(self, c, _):
        return BrackettedExpression(c[0])

    def r_expression_list(self, c, _):
        # 'ExpressionList ::= NIL | ...': the NIL alternative *is* the empty list,
        # so it must not become a member of it
        return ExpressionList(self._expressions(c))

    def r_arg_list(self, c, _):
        distinct = any(isinstance(x, str) and x.upper() == "DISTINCT" for x in c)
        return ArgList(self._expressions(c), distinct)

    @staticmethod
    def _expressions(children: list) -> list:
        return [x for x in children if isinstance(x, Node) and not isinstance(x, NIL)]

    def r_built_in_call(self, c, _):
        if len(c) == 1 and isinstance(
            c[0],
            (Aggregate, RegexExpression, SubstringExpression, StrReplaceExpression,
             ExistsFunc, NotExistsFunc),
        ):
            return c[0]
        name = next(x for x in c if isinstance(x, str))
        # 'BNODE ( "(" Expression ")" | NIL )' and the zero-argument builtins spell
        # their empty argument list as NIL, which is not itself an argument
        arguments = self._expressions(c)
        if arguments and isinstance(arguments[0], ExpressionList):
            arguments = arguments[0].expressions
        return BuiltInCall(BuiltIn(self._builtin_name(name)), arguments)

    @staticmethod
    def _builtin_name(text: str) -> str:
        for member in BuiltIn:
            if member.value.upper() == text.upper():
                return member.value
        raise SparqlSyntaxError(f"unknown built-in function {text!r}")

    def r_regex_expression(self, c, _):
        expressions = [x for x in c if isinstance(x, Node)]
        return RegexExpression(*expressions[:3]) if len(expressions) > 2 else RegexExpression(*expressions)

    def r_substring_expression(self, c, _):
        return SubstringExpression(*[x for x in c if isinstance(x, Node)][:3])

    def r_str_replace_expression(self, c, _):
        return StrReplaceExpression(*[x for x in c if isinstance(x, Node)][:4])

    def r_exists_func(self, c, _):
        return ExistsFunc(next(x for x in c if isinstance(x, Node)))

    def r_not_exists_func(self, c, _):
        return NotExistsFunc(next(x for x in c if isinstance(x, Node)))

    def r_aggregate(self, c, _):
        name = next(x for x in c if isinstance(x, str) and x.upper() in
                    {m.value for m in AggregateFunction})
        distinct = any(isinstance(x, str) and x.upper() == "DISTINCT" for x in c)
        wildcard = any(isinstance(x, str) and x == "*" for x in c)
        expression = next((x for x in c if isinstance(x, Node)), None)
        separator = None
        strings = [x for x in c if isinstance(x, Node) and isinstance(x, (STRING_LITERAL1, STRING_LITERAL2))]
        if strings and name.upper() == "GROUP_CONCAT":
            separator = strings[-1].value
            if expression is strings[-1]:
                expression = None
        return Aggregate(
            AggregateFunction(name.upper()),
            "*" if wildcard or expression is None else expression,
            distinct,
            separator,
        )

    def r_iri_or_function(self, c, _):
        return IRIOrFunction(c[0], next((x for x in c if isinstance(x, ArgList)), None))

    def r_function_call(self, c, _):
        return FunctionCall(c[0], c[1])

    def r_rdf_literal(self, c, _):
        value = c[0]
        lang_dir = next((x for x in c if isinstance(x, LANG_DIR)), None)
        datatype = next(
            (x for x in c[1:] if isinstance(x, (IRI, PNAME_LN, PNAME_NS))), None
        )
        return RDFLiteral(value, lang_dir, datatype)

    def r_lang_dir(self, c, _):
        return c[0]

    def r_datatype(self, c, _):
        return c[0]

    def r_boolean_literal(self, c, _):
        value = c[0]
        return value if isinstance(value, BooleanLiteral) else BooleanLiteral(
            str(value).upper() == "TRUE"
        )

    def r_var(self, c, _):
        return c[0]

    # -- SPARQL 1.2 -------------------------------------------------------

    def r_reified_triple(self, c, _):
        reifier = next((x for x in c if isinstance(x, Reifier)), None)
        terms = [x for x in c if not isinstance(x, Reifier)]
        return ReifiedTriple(terms[0], terms[1], terms[2], reifier)

    def r_reified_triple_block(self, c, _):
        return ReifiedTripleBlock(c[0], c[1])

    def r_reified_triple_block_path(self, c, _):
        return ReifiedTripleBlockPath(c[0], c[1])

    def r_reifier(self, c, _):
        return Reifier(c[0] if c else None)

    def r_var_or_reifier_id(self, c, _):
        return VarOrReifierId(c[0])

    def r_triple_term(self, c, _):
        return TripleTerm(c[0], c[1], c[2])

    def r_triple_term_data(self, c, _):
        return TripleTermData(c[0], c[1], c[2])

    def r_expr_triple_term(self, c, _):
        return ExprTripleTerm(c[0], c[1], c[2])

    def r_annotation(self, c, _):
        return Annotation(list(c))

    def r_annotation_path(self, c, _):
        return AnnotationPath(list(c))

    def r_annotation_block(self, c, _):
        return AnnotationBlock(c[0])

    def r_annotation_block_path(self, c, _):
        return AnnotationBlockPath(c[0])

    # -- update -----------------------------------------------------------

    def r_update(self, c, _):
        prologue = c[0] if c and isinstance(c[0], Prologue) else Prologue()
        operations = []
        for item in c:
            if isinstance(item, Prologue):
                continue
            if isinstance(item, Update):
                operations.extend(item.operations)
            else:
                operations.append(item)
        return Update(operations, prologue)

    def r_load(self, c, _):
        silent = any(isinstance(x, str) and x.upper() == "SILENT" for x in c)
        nodes = [x for x in c if isinstance(x, Node)]
        into = next((x for x in nodes if isinstance(x, GraphRef)), None)
        iri = next(x for x in nodes if not isinstance(x, GraphRef))
        return Load(iri, into, silent)

    def _silent_and_target(self, c):
        silent = any(isinstance(x, str) and x.upper() == "SILENT" for x in c)
        target = next(x for x in c if isinstance(x, Node))
        return silent, target

    def r_clear(self, c, _):
        silent, target = self._silent_and_target(c)
        return Clear(target if isinstance(target, GraphRefAll) else GraphRefAll(target), silent)

    def r_drop(self, c, _):
        silent, target = self._silent_and_target(c)
        return Drop(target if isinstance(target, GraphRefAll) else GraphRefAll(target), silent)

    def r_create(self, c, _):
        silent, target = self._silent_and_target(c)
        return Create(target if isinstance(target, GraphRef) else GraphRef(target), silent)

    def _graph_to_graph(self, cls, c):
        silent = any(isinstance(x, str) and x.upper() == "SILENT" for x in c)
        graphs = [x for x in c if isinstance(x, GraphOrDefault)]
        return cls(graphs[0], graphs[1], silent)

    def r_add(self, c, _):
        return self._graph_to_graph(Add_, c)

    def r_move(self, c, _):
        return self._graph_to_graph(Move, c)

    def r_copy(self, c, _):
        return self._graph_to_graph(Copy, c)

    def r_insert_data(self, c, _):
        return InsertData(c[0] if isinstance(c[0], QuadData) else QuadData(c[0]))

    def r_delete_data(self, c, _):
        return DeleteData(c[0] if isinstance(c[0], QuadData) else QuadData(c[0]))

    def r_delete_where(self, c, _):
        return DeleteWhere(c[0] if isinstance(c[0], QuadPattern) else QuadPattern(c[0]))

    def r_modify(self, c, _):
        return Modify(
            where=next(x for x in c if isinstance(x, GroupGraphPattern)),
            delete_clause=next((x for x in c if isinstance(x, DeleteClause)), None),
            insert_clause=next((x for x in c if isinstance(x, InsertClause)), None),
            with_iri=next((x for x in c if isinstance(x, (IRI, PNAME_LN, PNAME_NS))), None),
            using_clauses=[x for x in c if isinstance(x, UsingClause)],
        )

    def r_delete_clause(self, c, _):
        return DeleteClause(c[0] if isinstance(c[0], QuadPattern) else QuadPattern(c[0]))

    def r_insert_clause(self, c, _):
        return InsertClause(c[0] if isinstance(c[0], QuadPattern) else QuadPattern(c[0]))

    def r_using_clause(self, c, _):
        named = any(isinstance(x, str) and x.upper() == "NAMED" for x in c)
        return UsingClause(next(x for x in c if isinstance(x, Node)), named)

    def r_graph_or_default(self, c, _):
        explicit = any(isinstance(x, str) and x.upper() == "GRAPH" for x in c)
        iri = next((x for x in c if isinstance(x, Node)), None)
        if iri is None:
            return GraphOrDefault()
        return GraphOrDefault(iri, explicit)

    def r_graph_ref(self, c, _):
        return GraphRef(next(x for x in c if isinstance(x, Node)))

    def r_graph_ref_all(self, c, _):
        if c and isinstance(c[0], GraphRef):
            return GraphRefAll(c[0])
        keyword = next((x for x in c if isinstance(x, str)), "DEFAULT")
        return GraphRefAll(GraphRefTarget(keyword.upper()))

    def r_quad_pattern(self, c, _):
        return QuadPattern(c[0] if c else Quads())

    def r_quad_data(self, c, _):
        return QuadData(c[0] if c else Quads())

    def r_quads(self, c, _):
        return Quads(list(c))

    def r_group_graph_pattern_sub_other(self, c, _):
        """group_graph_pattern_sub_other: graph_pattern_not_triples DOT? triples_block?"""
        return list(c)

    def r_property_list_path_not_empty_rest(self, c, _):
        return self._verb_object_pairs(c, ObjectListPath)

    def r_true(self, c, _):
        return BooleanLiteral(True)

    def r_false(self, c, _):
        return BooleanLiteral(False)

    def r_quads_not_triples(self, c, _):
        nodes = [x for x in c if isinstance(x, Node)]
        return QuadsNotTriples(
            nodes[0], next((x for x in nodes[1:] if isinstance(x, TriplesTemplate)), None)
        )


def _parse(text: str, start: str, parser: str) -> Node:
    lark = _lark()
    try:
        tree = _parser(start, parser).parse(text)
    except lark.exceptions.UnexpectedInput as exc:
        raise SparqlSyntaxError(str(exc)) from exc
    except lark.exceptions.LarkError as exc:  # pragma: no cover - defensive
        raise SparqlSyntaxError(str(exc)) from exc
    return _Builder().build(tree)


def parse(text: str, parser: str = "lalr") -> Node:
    """Parse a SPARQL query or update request into a grammar tree.

    Returns a ``QueryUnit`` or an ``UpdateUnit``. Pass ``parser="earley"`` for the
    slower, more permissive parser if LALR ever rejects something valid.
    """
    return _parse(text, "unit", parser)


def parse_query(text: str, parser: str = "lalr") -> Node:
    """Parse a query, rejecting update requests."""
    return _parse(text, "query_unit", parser)


def parse_update(text: str, parser: str = "lalr") -> Node:
    """Parse an update request, rejecting queries."""
    return _parse(text, "update_unit", parser)


def to_python_source(node: Node, variable: str = "query") -> str:
    """Emit Python source that rebuilds ``node``.

    Handy at development time: parse the SPARQL you already have, then paste the
    generated constructor calls into your code as a starting point.
    """
    return f"{variable} = {_repr_node(node)}"


def _repr_node(value: Any, indent: int = 0) -> str:
    from dataclasses import fields, is_dataclass

    pad = "    " * (indent + 1)
    if value is UNDEF:
        return "UNDEF"  # the marker is a singleton, so name it rather than rebuild it
    if isinstance(value, Node) and is_dataclass(value):
        parts = []
        for field in fields(value):
            item = getattr(value, field.name)
            if item is None or (isinstance(item, (list, tuple)) and not item):
                continue
            parts.append(f"{pad}{field.name}={_repr_node(item, indent + 1)}")
        if not parts:
            return f"{type(value).__name__}()"
        body = ",\n".join(parts)
        return f"{type(value).__name__}(\n{body},\n{'    ' * indent})"
    if isinstance(value, list):
        if not value:
            return "[]"
        body = ",\n".join(f"{pad}{_repr_node(v, indent + 1)}" for v in value)
        return f"[\n{body},\n{'    ' * indent}]"
    if isinstance(value, tuple):
        return "(" + ", ".join(_repr_node(v, indent) for v in value) + ")"
    return repr(value)
