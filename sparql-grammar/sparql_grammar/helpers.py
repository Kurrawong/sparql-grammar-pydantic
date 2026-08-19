"""Concise constructors for the shapes people actually build.

The grammar classes are faithful to the spec, which makes them verbose for common
work: a single ``FILTER`` needs nine levels of expression nesting, and a ``VALUES``
block needs four. The functions here are the short way to say the same thing. They
return ordinary grammar nodes, so anything built with them can be inspected and
mutated like anything else.

Design rules, in case you extend this:

* Lift inputs, never guess them. A bare term is lifted into whatever wrapper the slot
  requires - callers should not have to know that an object list wants ``ObjectPath``
  entries - and a Python ``bool``/``int``/``float`` becomes the literal its own type
  already names. A ``str`` is *not* a term: say :func:`iri`, :func:`literal` or
  :func:`var`. Reading text as one term type or another is how a value meant as a
  literal silently became an IRI, and one untrusted string became a query rewrite.
  The single exception is a slot the grammar restricts to a variable (the projection
  list, ``BIND ... AS``, the ``VALUES`` variable list), where a name is unambiguous.
* Name things after the SPARQL concept, not the use case that prompted them, so the
  set stays small and composable: there is ``filter_`` plus ``Expression.any_of``
  rather than a bespoke helper per kind of disjunctive filter.
* Cover the grammar evenly, including UPDATE and the 1.2 reification forms.
* Anything specific to one production belongs on that production as a classmethod
  (``PathAlternative.seq``, ``Aggregate.count``); this module is for things that
  span productions or assemble whole queries.
"""

from __future__ import annotations

from typing import Iterable

from ._base import Node, ValidationError
from .expressions import (
    Aggregate,
    BuiltIn,
    BuiltInCall,
    ConditionalOrExpression as Expression,
    ExistsFunc,
    NotExistsFunc,
    RegexExpression,
)
from .grammar import (
    Bind,
    ConstructQuery,
    ConstructTemplate,
    ConstructTriples,
    DatasetClause,
    Filter,
    GraphGraphPattern,
    GroupClause,
    GroupGraphPattern,
    GroupGraphPatternSub,
    GroupOrUnionGraphPattern,
    HavingClause,
    InlineData,
    InlineDataFull,
    InlineDataOneVar,
    LimitOffsetClauses,
    MinusGraphPattern,
    OptionalGraphPattern,
    OrderClause,
    OrderCondition,
    Prologue,
    Query,
    QueryUnit,
    SelectClause,
    SelectQuery,
    ServiceGraphPattern,
    SolutionModifier,
    SubSelect,
    TriplesBlock,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    UNDEF,
    WhereClause,
)
from .terminals import PNAME_LN, PNAME_NS
from .terms import (
    IRI,
    BooleanLiteral,
    RDFLiteral,
    Var,
    numeric_literal,
    refuse_string,
)
from .update import (
    DeleteClause,
    DeleteData,
    DeleteWhere,
    InsertClause,
    InsertData,
    Modify,
    QuadPattern,
    Quads,
    Update,
    UpdateUnit,
)

__all__ = [
    # terms
    "var", "iri", "literal", "term",
    # triples
    "triple", "triples", "tss", "tss_list", "tss_and_tssp",
    # patterns
    "group", "optional", "union", "minus", "graph", "service", "filter_", "bind",
    "values", "exists", "not_exists",
    # expressions
    "regex", "count", "bound", "is_blank", "is_iri", "is_literal", "str_",
    "lang", "lcase", "ucase", "datatype", "same_term",
    # queries
    "select", "construct", "subselect",
    # update
    "insert_data", "delete_data", "delete_where", "modify", "update",
]


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def _verify(node: Node) -> Node:
    """Check one freshly built term, without the cost of a whole-tree walk.

    ``validate()`` walks the tree and collects errors, which is the right shape for
    checking a query but roughly three times the cost of checking a single leaf. The
    terms built here are leaves, so their own check is the whole check.
    """
    errors = node._check("terminals")
    if errors:
        raise ValidationError(errors)
    return node


def var(name: str | Var, check: bool = True) -> Var:
    """``var("s")`` or ``var("?s")`` -> ``?s``

    Validated by default, for the same reason as :func:`iri`: a variable name has no
    escape syntax either. Pass ``check=False`` to skip it.
    """
    if isinstance(name, Var):
        return _verify(name) if check else name
    node = Var.from_string(name)
    return _verify(node) if check else node


def iri(value: str | Node, check: bool = True) -> object:
    """``iri("http://x")`` -> ``<http://x>``; ``iri("skos:broader")`` -> ``skos:broader``

    A value with no scheme separator but a colon is read as a prefixed name.

    The value is validated by default. An IRI has no escape syntax, so a value
    containing ``>`` or whitespace cannot be rendered safely - it can only be
    refused, rather than silently changing what the query means. This is the helper
    that untrusted strings arrive through, so it is safe by default; the check costs
    well under a microsecond.

    Pass ``check=False`` in a hot loop over values the program itself produced, or
    use the ``IRI`` constructor directly, which never validates.
    """
    if isinstance(value, Node):
        # a node handed in may be a whole subtree, so check all of it
        if check:
            value.validate("terminals")
        return value
    text = value.strip()
    if text.startswith("<") and text.endswith(">"):
        node = IRI(text[1:-1])
    elif "://" not in text and ":" in text:
        prefix, _, local = text.partition(":")
        node = PNAME_LN(text) if local else PNAME_NS(prefix)
    else:
        node = IRI(text)
    return _verify(node) if check else node


def literal(
    value: object,
    lang: str | None = None,
    datatype: str | Node | None = None,
    check: bool = True,
) -> Node:
    """A literal term. A ``bool``, ``int`` or ``float`` maps to its SPARQL form.

    ``literal("5")`` is the string ``"5"`` and ``literal(5)`` is the number ``5``:
    the Python type says which, so nothing is read out of the text. Giving a ``lang``
    or a ``datatype`` makes it a quoted literal regardless, since a number cannot
    carry either.

    The text itself is escaped when rendered, so it is safe from untrusted input
    either way. The check - on by default, as with :func:`iri` - covers the language
    tag and the datatype IRI, which have no escape syntax and so can only be refused.
    For plain text with neither, it costs almost nothing.
    """
    if lang is not None:
        node: Node = RDFLiteral.langed(str(value), lang)
    elif datatype is not None:
        node = RDFLiteral.typed(str(value), datatype)
    elif isinstance(value, bool):
        node = BooleanLiteral(value)
    elif isinstance(value, (int, float)):
        node = numeric_literal(value)
    else:
        node = RDFLiteral(str(value))
    return _verify(node) if check else node


def term(value: object, check: bool = True) -> object:
    """Lift a Python value into a term node. Nodes pass through, validated by default.

    A ``bool``, ``int`` or ``float`` becomes the literal its Python type already
    names. **A ``str`` is refused**: text alone does not say which term it is, so say
    it yourself with :func:`iri`, :func:`literal` or :func:`var`. This is the same
    bargain rdflib strikes with ``URIRef`` and ``Literal``, for the same reason - see
    :func:`sparql_grammar.terms.refuse_string`.
    """
    if isinstance(value, Node):
        if check:
            value.validate("terminals")
        return value
    if isinstance(value, str):
        refuse_string(value)
    if isinstance(value, (bool, int, float)):
        return literal(value, check=check)
    raise TypeError(
        f"a {type(value).__name__} is not a term. Pass a grammar node, a bool, an int "
        f"or a float, or say what it should become: iri(...), literal(...) or var(...)."
    )


def _predicate(value: object) -> object:
    """A predicate slot: ``"a"``, a path, a variable or an IRI.

    ``"a"`` stays a bare string because it is not a term: the grammar spells it as the
    keyword ``PathPrimary ::= 'a'``, standing for ``rdf:type``. Any other string is
    refused, since predicate position takes a variable or an IRI and text does not say
    which.
    """
    if value == "a" or isinstance(value, Node):
        return value
    if isinstance(value, str):
        refuse_string(value, literals_allowed=False)
    return term(value)


# ---------------------------------------------------------------------------
# Triples
# ---------------------------------------------------------------------------


def triple(subject: object, predicate: object, obj: object) -> TriplesSameSubjectPath:
    """One triple pattern. Terms must be nodes: ``var()``, ``iri()``, ``literal()``."""
    return TriplesSameSubjectPath.from_spo(
        term(subject), _predicate(predicate), term(obj)
    )


def triples(spo_list: Iterable[tuple]) -> TriplesBlock:
    """A triples block from ``(s, p, o)`` tuples."""
    return TriplesBlock([triple(*spo) for spo in spo_list])


def tss(subject: object, predicate: object, obj: object) -> TriplesSameSubject:
    """One triple for a CONSTRUCT template or an UPDATE quad."""
    return TriplesSameSubject.from_spo(term(subject), _predicate(predicate), term(obj))


def tss_list(spo_list: Iterable[tuple]) -> list:
    return [tss(*spo) for spo in spo_list]


def tss_and_tssp(
    subject: object, predicate: object, obj: object
) -> tuple[TriplesSameSubject, TriplesSameSubjectPath]:
    """Both flavours of the same triple.

    Consumers that build a CONSTRUCT template alongside its WHERE clause need the
    template form and the path form of every triple, and were writing both by hand.
    """
    return tss(subject, predicate, obj), triple(subject, predicate, obj)


# ---------------------------------------------------------------------------
# Graph patterns
# ---------------------------------------------------------------------------


def _is_spo(value: object) -> bool:
    """A 3-tuple is a triple; a list is a sequence of patterns."""
    return isinstance(value, tuple) and len(value) == 3


def _to_ggp(content: object) -> GroupGraphPattern:
    """Accept a pattern, a triple tuple, a list of either, or a whole subselect."""
    if isinstance(content, GroupGraphPattern):
        return content
    if isinstance(content, (GroupGraphPatternSub, SubSelect)):
        return GroupGraphPattern(content)
    if isinstance(content, TriplesBlock):
        return GroupGraphPattern(GroupGraphPatternSub([content]))
    if isinstance(content, TriplesSameSubjectPath):
        return GroupGraphPattern(GroupGraphPatternSub([TriplesBlock([content])]))
    if _is_spo(content):
        return GroupGraphPattern(group(content))
    if isinstance(content, (list, tuple)):
        return GroupGraphPattern(group(*content))
    return GroupGraphPattern(GroupGraphPatternSub([content]))


def group(*patterns: object) -> GroupGraphPatternSub:
    """Assemble a pattern group. Triples and tuples are folded into blocks.

    ``group(triple(...), optional(...), filter_(...))``
    """
    sub = GroupGraphPatternSub()
    pending: list = []
    for pattern in patterns:
        if isinstance(pattern, TriplesSameSubjectPath):
            pending.append(pattern)
            continue
        if _is_spo(pattern):
            pending.append(triple(*pattern))
            continue
        if isinstance(pattern, TriplesBlock):
            pending.extend(pattern.triples)
            continue
        if isinstance(pattern, list):
            sub.add_triples(pending)
            pending = []
            for item in pattern:
                nested = group(item) if not _is_spo(item) else group(item)
                sub.patterns.extend(nested.patterns)
            continue
        if pending:
            sub.add_triples(pending)
            pending = []
        sub.add_pattern(pattern)
    if pending:
        sub.add_triples(pending)
    return sub


def optional(*patterns: object) -> OptionalGraphPattern:
    """``OPTIONAL { ... }``"""
    return OptionalGraphPattern(_to_ggp(list(patterns)))


def minus(*patterns: object) -> MinusGraphPattern:
    """``MINUS { ... }``"""
    return MinusGraphPattern(_to_ggp(list(patterns)))


def union(*alternatives: object) -> GroupOrUnionGraphPattern:
    """``{ ... } UNION { ... }`` - each argument becomes one arm."""
    return GroupOrUnionGraphPattern([_to_ggp(a) for a in alternatives])


def graph(name: object, *patterns: object) -> GraphGraphPattern:
    """``GRAPH ?g { ... }`` or ``GRAPH <g> { ... }``

    ``name`` is a ``Var`` or an IRI - ``graph(var("g"), ...)``, ``graph(iri("http://g"),
    ...)`` - since the grammar allows either and a string cannot say which.
    """
    return GraphGraphPattern(term(name), _to_ggp(list(patterns)))


def service(endpoint: object, *patterns: object, silent: bool = False) -> ServiceGraphPattern:
    """``SERVICE <endpoint> { ... }``. ``endpoint`` is an ``iri()`` or a ``var()``."""
    return ServiceGraphPattern(term(endpoint), _to_ggp(list(patterns)), silent)


def filter_(constraint: object) -> Filter:
    """``FILTER (...)``. Named with a trailing underscore to avoid the builtin."""
    return Filter(constraint)


def bind(expression: object, as_var: object) -> Bind:
    """``BIND(expr AS ?v)``. ``as_var`` may be a name: only a variable is legal there."""
    if not isinstance(expression, Expression):
        expression = Expression.from_primary_expression(term(expression))
    return Bind(expression, var(as_var) if isinstance(as_var, str) else as_var)


def values(variables: object, rows: Iterable) -> InlineData:
    """``VALUES`` in either form.

    One variable and a flat list of values gives the single-variable form; a list of
    variables and a list of rows gives the full form. The variable position takes a
    name, since the grammar allows nothing else there; the values are terms.

        values("x", [iri("http://a"), iri("http://b")])
        values(["a", "b"], [[iri("http://1"), literal("x")], [iri("http://2"), UNDEF]])
    """
    if isinstance(variables, (str, Var)):
        return InlineData(
            InlineDataOneVar(var(variables), [_data_value(v) for v in rows])
        )
    variable_nodes = [var(v) if isinstance(v, str) else v for v in variables]
    value_rows = [[_data_value(v) for v in row] for row in rows]
    return InlineData(InlineDataFull(variable_nodes, value_rows))


def _data_value(value: object) -> object:
    """One cell of a ``VALUES`` row: a term or ``UNDEF``, and never a variable.

    ``DataBlockValue ::= iri | RDFLiteral | NumericLiteral | BooleanLiteral | 'UNDEF' |
    TripleTermData`` has no ``Var`` in it, and the omission matters: a variable here
    does not narrow the query, it widens it.
    """
    if value is UNDEF:
        return value
    if isinstance(value, str) and value.strip() == "UNDEF":
        raise TypeError(
            "pass the UNDEF marker itself, not the string: "
            "from sparql_grammar import UNDEF"
        )
    node = term(value)
    if isinstance(node, Var):
        raise TypeError(
            f"a VALUES row holds terms, not variables, so {node.to_string()} cannot "
            "appear in one: DataBlockValue is iri | RDFLiteral | NumericLiteral | "
            "BooleanLiteral | UNDEF | TripleTermData."
        )
    return node


def exists(*patterns: object) -> ExistsFunc:
    """``EXISTS { ... }``"""
    return ExistsFunc(_to_ggp(list(patterns)))


def not_exists(*patterns: object) -> NotExistsFunc:
    """``NOT EXISTS { ... }``"""
    return NotExistsFunc(_to_ggp(list(patterns)))


# ---------------------------------------------------------------------------
# Expression shorthands
# ---------------------------------------------------------------------------


def _expr(value: object) -> Expression:
    return (
        value
        if isinstance(value, Expression)
        else Expression.from_primary_expression(term(value) if not isinstance(value, Node) else value)
    )


def regex(text: object, pattern: object, flags: object = None) -> RegexExpression:
    """``REGEX(STR(?x), "pattern")`` - the text argument is wrapped in ``STR``.

    Pass an explicit expression as ``text`` to skip the ``STR`` wrapper.
    """
    if isinstance(text, Expression):
        text_expression = text
    else:
        text_expression = _expr(BuiltInCall.create(BuiltIn.STR, term(text)))
    return RegexExpression(
        text_expression,
        _expr(pattern if isinstance(pattern, Node) else RDFLiteral(str(pattern))),
        _expr(flags if isinstance(flags, Node) else RDFLiteral(str(flags)))
        if flags is not None
        else None,
    )


def count(expression: object = "*", distinct: bool = False) -> Aggregate:
    """``COUNT(*)``, ``COUNT(?x)`` or ``COUNT(DISTINCT ?x)``"""
    return Aggregate.count("*" if expression == "*" else _expr(expression), distinct)


def _one_arg(function: BuiltIn):
    """Build a one-argument built-in helper that coerces its argument."""

    def helper(value: object) -> BuiltInCall:
        return BuiltInCall.create(function, term(value))

    helper.__name__ = function.value
    helper.__doc__ = f"``{function.value}(...)``"
    return helper


bound = _one_arg(BuiltIn.BOUND)
is_blank = _one_arg(BuiltIn.IS_BLANK)
is_iri = _one_arg(BuiltIn.IS_IRI)
is_literal = _one_arg(BuiltIn.IS_LITERAL)
str_ = _one_arg(BuiltIn.STR)
lang = _one_arg(BuiltIn.LANG)
lcase = _one_arg(BuiltIn.LCASE)
ucase = _one_arg(BuiltIn.UCASE)
datatype = _one_arg(BuiltIn.DATATYPE)


def same_term(left: object, right: object) -> BuiltInCall:
    """``sameTerm(a, b)``"""
    return BuiltInCall.create(BuiltIn.SAME_TERM, term(left), term(right))


# ---------------------------------------------------------------------------
# Query skeletons
# ---------------------------------------------------------------------------


def _solution_modifier(
    group_by: object = None,
    having: object = None,
    order_by: object = None,
    limit: int | None = None,
    offset: int | None = None,
) -> SolutionModifier:
    return SolutionModifier(
        group_by=GroupClause.create(*_as_tuple(group_by)) if group_by else None,
        having=HavingClause.create(*_as_tuple(having)) if having else None,
        order_by=OrderClause.create(*_as_tuple(order_by)) if order_by else None,
        limit_offset=LimitOffsetClauses.create(limit, offset)
        if limit is not None or offset is not None
        else None,
    )


def _as_tuple(value: object) -> tuple:
    if value is None:
        return ()
    return tuple(value) if isinstance(value, (list, tuple)) else (value,)


def select(
    *variables: object,
    where: object = None,
    distinct: bool = False,
    reduced: bool = False,
    group_by: object = None,
    having: object = None,
    order_by: object = None,
    limit: int | None = None,
    offset: int | None = None,
    from_: object = None,
    from_named: object = None,
    prefixes: dict[str, str] | None = None,
) -> SelectQuery | QueryUnit:
    """A SELECT query.

        select(var("s"), where=[triple("?s", "a", iri("http://C"))], limit=10)

    Pass no variables for ``SELECT *``. With ``prefixes``, returns a ``QueryUnit``
    carrying the prologue; otherwise a bare ``SelectQuery``.
    """
    query = SelectQuery(
        SelectClause.create(
            *[var(v) if isinstance(v, str) else v for v in variables],
            distinct=distinct,
            reduced=reduced,
        ),
        WhereClause(_to_ggp(where if where is not None else [])),
        _solution_modifier(group_by, having, order_by, limit, offset),
        _dataset_clauses(from_, from_named),
    )
    return _maybe_unit(query, prefixes)


def construct(
    template: object,
    where: object = None,
    *,
    order_by: object = None,
    limit: int | None = None,
    offset: int | None = None,
    from_: object = None,
    from_named: object = None,
    prefixes: dict[str, str] | None = None,
) -> ConstructQuery | QueryUnit:
    """A CONSTRUCT query.

        construct([(var("s"), "a", iri("http://C"))], where=[...])

    ``where`` defaults to the template, giving ``CONSTRUCT { t } WHERE { t }``.
    """
    if isinstance(template, ConstructTemplate):
        construct_template = template
    elif isinstance(template, ConstructTriples):
        construct_template = ConstructTemplate(template)
    else:
        construct_template = ConstructTemplate(
            ConstructTriples(
                [t if isinstance(t, TriplesSameSubject) else tss(*t) for t in template]
            )
        )
    if where is None:
        where = _template_as_patterns(construct_template)
    query = ConstructQuery(
        construct_template,
        WhereClause(_to_ggp(where)),
        _solution_modifier(None, None, order_by, limit, offset),
        _dataset_clauses(from_, from_named),
    )
    return _maybe_unit(query, prefixes)


def _template_as_patterns(template: ConstructTemplate) -> list:
    """Reuse a CONSTRUCT template as its own WHERE clause."""
    if template.construct_triples is None:
        return []
    return [
        TriplesSameSubjectPath(t.subject, _as_path_property_list(t.property_list))
        for t in template.construct_triples.triples
    ]


def _as_path_property_list(property_list: Node) -> Node:
    from .grammar import ObjectListPath, PropertyListPathNotEmpty

    pairs = []
    for verb, object_list in property_list.pairs:
        objects = [o.graph_node for o in object_list.objects]
        pairs.append(
            PropertyListPathNotEmpty.create(verb, *objects).pairs[0]
            if len(objects) == 1
            else (verb, ObjectListPath.create(*objects))
        )
    return PropertyListPathNotEmpty(pairs)


def subselect(
    *variables: object,
    where: object = None,
    distinct: bool = False,
    group_by: object = None,
    having: object = None,
    order_by: object = None,
    limit: int | None = None,
    offset: int | None = None,
) -> SubSelect:
    """A subselect, for nesting inside a graph pattern."""
    return SubSelect(
        SelectClause.create(
            *[var(v) if isinstance(v, str) else v for v in variables], distinct=distinct
        ),
        WhereClause(_to_ggp(where if where is not None else [])),
        _solution_modifier(group_by, having, order_by, limit, offset),
    )


def _dataset_clauses(from_: object, from_named: object) -> list:
    clauses = [DatasetClause.create(term(g)) for g in _as_tuple(from_)]
    clauses += [DatasetClause.create(term(g), named=True) for g in _as_tuple(from_named)]
    return clauses


def _maybe_unit(query: Node, prefixes: dict[str, str] | None) -> Node:
    if not prefixes:
        return query
    return QueryUnit(Query(query, Prologue.from_prefixes(prefixes)))


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def _quads(data: object) -> Quads:
    if isinstance(data, Quads):
        return data
    return Quads.from_tss_list(
        [t if isinstance(t, TriplesSameSubject) else tss(*t) for t in data]
    )


def insert_data(data: object, prefixes: dict[str, str] | None = None) -> Node:
    """``INSERT DATA { ... }``"""
    from .update import QuadData

    operation = InsertData(QuadData(_quads(data)))
    return _maybe_update_unit(operation, prefixes)


def delete_data(data: object, prefixes: dict[str, str] | None = None) -> Node:
    """``DELETE DATA { ... }``"""
    from .update import QuadData

    operation = DeleteData(QuadData(_quads(data)))
    return _maybe_update_unit(operation, prefixes)


def delete_where(data: object, prefixes: dict[str, str] | None = None) -> Node:
    """``DELETE WHERE { ... }``"""
    operation = DeleteWhere(QuadPattern(_quads(data)))
    return _maybe_update_unit(operation, prefixes)


def modify(
    where: object,
    delete: object = None,
    insert: object = None,
    with_graph: object = None,
    prefixes: dict[str, str] | None = None,
) -> Node:
    """``[WITH <g>] [DELETE { ... }] [INSERT { ... }] WHERE { ... }``"""
    operation = Modify(
        where=_to_ggp(where),
        delete_clause=DeleteClause(QuadPattern(_quads(delete))) if delete else None,
        insert_clause=InsertClause(QuadPattern(_quads(insert))) if insert else None,
        with_iri=term(with_graph) if with_graph is not None else None,
    )
    return _maybe_update_unit(operation, prefixes)


def update(*operations: object, prefixes: dict[str, str] | None = None) -> UpdateUnit:
    """Several update operations in one request, joined with ``;``."""
    unwrapped = [
        op.update.operations[0] if isinstance(op, UpdateUnit) else op
        for op in operations
    ]
    return UpdateUnit(
        Update(list(unwrapped), Prologue.from_prefixes(prefixes) if prefixes else None)
    )


def _maybe_update_unit(operation: Node, prefixes: dict[str, str] | None) -> Node:
    if not prefixes:
        return operation
    return UpdateUnit(Update([operation], Prologue.from_prefixes(prefixes)))
