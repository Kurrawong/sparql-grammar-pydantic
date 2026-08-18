"""Query, graph pattern, and triple productions, plus the SPARQL 1.2 reification family.

Recursive productions (``TriplesBlock``, ``ConstructTriples``, ``TriplesTemplate``,
``Quads``, ``GroupGraphPatternSub``) are modelled as **flat lists** rather than the
right-recursion the grammar is written with. The class names still match the spec
one-for-one; only the field shape differs, and each docstring says so. The reason is
measured: the linked-list form makes rendering quadratic and blows the recursion limit
somewhere past a thousand triples, while a flat list renders in linear time with no
ceiling.
"""

from __future__ import annotations

from enum import Enum
from typing import Union

from ._base import Add, Node, alias, production
from .expressions import (
    ArgList,
    BrackettedExpression,
    BuiltInCall,
    ConditionalOrExpression,
    Constraint,
    ExistsFunc,
    FunctionCall,
    NotExistsFunc,
)
from .paths import PathAlternative, RDF_TYPE
from .terminals import (
    ANON,
    BLANK_NODE_LABEL,
    INTEGER,
    IRIREF,
    NIL,
    PNAME_LN,
    PNAME_NS,
    STRING_LITERAL1,
    STRING_LITERAL2,
)
from .terms import IRI, BooleanLiteral, RDFLiteral, Var

__all__ = [
    # top level
    "QueryUnit", "Query", "Prologue", "BaseDecl", "PrefixDecl", "VersionDecl",
    "VersionSpecifier",
    # query forms
    "SelectQuery", "SubSelect", "SelectClause", "SelectModifier", "ConstructQuery",
    "DescribeQuery", "AskQuery", "DatasetClause", "DefaultGraphClause",
    "NamedGraphClause", "SourceSelector", "WhereClause",
    # solution modifiers
    "SolutionModifier", "GroupClause", "GroupCondition", "HavingClause",
    "HavingCondition", "OrderClause", "OrderCondition", "OrderDirection",
    "LimitOffsetClauses", "LimitClause", "OffsetClause", "ValuesClause",
    # graph patterns
    "GroupGraphPattern", "GroupGraphPatternSub", "GraphPatternNotTriples",
    "OptionalGraphPattern", "GraphGraphPattern", "ServiceGraphPattern",
    "MinusGraphPattern", "GroupOrUnionGraphPattern", "Filter", "Bind",
    # inline data
    "InlineData", "DataBlock", "InlineDataOneVar", "InlineDataFull", "DataBlockValue",
    "UNDEF",
    # triples
    "ConstructTemplate", "ConstructTriples", "TriplesBlock", "TriplesTemplate",
    "TriplesSameSubject", "TriplesSameSubjectPath", "PropertyList",
    "PropertyListNotEmpty", "PropertyListPath", "PropertyListPathNotEmpty",
    "Verb", "VerbPath", "VerbSimple", "ObjectList", "Object", "ObjectListPath",
    "ObjectPath", "TriplesNode", "TriplesNodePath", "BlankNodePropertyList",
    "BlankNodePropertyListPath", "Collection", "CollectionPath", "GraphNode",
    "GraphNodePath",
    # SPARQL 1.2 reification
    "ReifiedTriple", "ReifiedTripleSubject", "ReifiedTripleObject",
    "ReifiedTripleBlock", "ReifiedTripleBlockPath", "Reifier", "VarOrReifierId",
    "TripleTerm", "TripleTermSubject", "TripleTermObject", "TripleTermData",
    "TripleTermDataSubject", "TripleTermDataObject", "Annotation", "AnnotationBlock",
    "AnnotationPath", "AnnotationBlockPath",
]

#: The ``UNDEF`` marker permitted in a VALUES data block.
UNDEF = "UNDEF"

IRIish = Union[IRI, PNAME_LN, PNAME_NS]


# ---------------------------------------------------------------------------
# Prologue
# ---------------------------------------------------------------------------


@production(rule="BaseDecl")
class BaseDecl(Node):
    """BaseDecl ::= 'BASE' IRIREF"""

    iriref: IRIREF

    def render(self, add: Add) -> None:
        add("BASE ")
        self.iriref.render(add)


@production(rule="PrefixDecl")
class PrefixDecl(Node):
    """PrefixDecl ::= 'PREFIX' PNAME_NS IRIREF"""

    pname_ns: PNAME_NS
    iriref: IRIREF

    def render(self, add: Add) -> None:
        add("PREFIX ")
        self.pname_ns.render(add)
        add(" ")
        self.iriref.render(add)

    @classmethod
    def create(cls, prefix: str, iri: str) -> PrefixDecl:
        """``PrefixDecl.create("skos", "http://...")``"""
        return cls(PNAME_NS(prefix), IRIREF.from_string(iri))


#: VersionSpecifier ::= STRING_LITERAL1 | STRING_LITERAL2
VersionSpecifier = alias("VersionSpecifier", Union[STRING_LITERAL1, STRING_LITERAL2])


@production(rule="VersionDecl")
class VersionDecl(Node):
    """VersionDecl ::= 'VERSION' VersionSpecifier

    New in SPARQL 1.2.
    """

    version: object

    def render(self, add: Add) -> None:
        add("VERSION ")
        if isinstance(self.version, str):
            add('"')
            add(self.version)
            add('"')
        else:
            self.version.render(add)


@production(rule="Prologue")
class Prologue(Node):
    """Prologue ::= ( BaseDecl | PrefixDecl | VersionDecl )*"""

    decls: list = None

    def __post_init__(self) -> None:
        if self.decls is None:
            self.decls = []

    def render(self, add: Add) -> None:
        for decl in self.decls:
            decl.render(add)
            add("\n")

    @classmethod
    def from_prefixes(cls, prefixes: dict[str, str]) -> Prologue:
        """``Prologue.from_prefixes({"skos": "http://..."})``"""
        return cls([PrefixDecl.create(p, iri) for p, iri in prefixes.items()])


# ---------------------------------------------------------------------------
# Triples
# ---------------------------------------------------------------------------

#: VerbPath ::= Path
VerbPath = alias("VerbPath", PathAlternative)

#: VerbSimple ::= Var
VerbSimple = alias("VerbSimple", Var)

#: Verb ::= VarOrIri | 'a'  (the string ``"a"`` stands for rdf:type)
Verb = alias("Verb", Union[Var, IRI, PNAME_LN, PNAME_NS, str])


def _render_verb(verb: object, add: Add) -> None:
    """Render a verb slot, honouring the ``a`` shorthand for rdf:type."""
    if verb == RDF_TYPE:
        add("a")
    else:
        verb.render(add)


@production(rule="Object")
class Object(Node):
    """Object ::= GraphNode Annotation"""

    graph_node: object
    annotation: Annotation | None = None

    def render(self, add: Add) -> None:
        self.graph_node.render(add)
        if self.annotation is not None:
            self.annotation.render(add)


@production(rule="ObjectList")
class ObjectList(Node):
    """ObjectList ::= Object ( ',' Object )*"""

    objects: list

    def render(self, add: Add) -> None:
        for i, obj in enumerate(self.objects):
            if i:
                add(", ")
            obj.render(add)

    @classmethod
    def create(cls, *nodes: object) -> ObjectList:
        """Wrap bare terms as objects."""
        return cls([n if isinstance(n, Object) else Object(n) for n in nodes])


@production(rule="ObjectPath")
class ObjectPath(Node):
    """ObjectPath ::= GraphNodePath AnnotationPath"""

    graph_node_path: object
    annotation_path: AnnotationPath | None = None

    def render(self, add: Add) -> None:
        self.graph_node_path.render(add)
        if self.annotation_path is not None:
            self.annotation_path.render(add)


@production(rule="ObjectListPath")
class ObjectListPath(Node):
    """ObjectListPath ::= ObjectPath ( ',' ObjectPath )*"""

    object_paths: list

    def render(self, add: Add) -> None:
        for i, obj in enumerate(self.object_paths):
            if i:
                add(", ")
            obj.render(add)

    @classmethod
    def create(cls, *nodes: object) -> ObjectListPath:
        return cls([n if isinstance(n, ObjectPath) else ObjectPath(n) for n in nodes])


@production(rule="PropertyListNotEmpty")
class PropertyListNotEmpty(Node):
    """PropertyListNotEmpty ::= Verb ObjectList ( ';' ( Verb ObjectList )? )*

    ``pairs`` is a flat list of ``(verb, object_list)`` tuples.
    """

    pairs: list

    def render(self, add: Add) -> None:
        for i, (verb, object_list) in enumerate(self.pairs):
            if i:
                add(" ; ")
            _render_verb(verb, add)
            add(" ")
            object_list.render(add)

    @classmethod
    def create(cls, verb: object, *objects: object) -> PropertyListNotEmpty:
        return cls([(verb, ObjectList.create(*objects))])


#: PropertyList ::= PropertyListNotEmpty?
PropertyList = alias("PropertyList", PropertyListNotEmpty)


@production(rule="PropertyListPathNotEmpty")
class PropertyListPathNotEmpty(Node):
    """PropertyListPathNotEmpty ::= ( VerbPath | VerbSimple ) ObjectListPath ( ';' ( ( VerbPath | VerbSimple ) ObjectListPath )? )*

    ``pairs`` is a flat list of ``(verb, object_list_path)`` tuples, where each verb
    is a ``PathAlternative`` (VerbPath) or a ``Var`` (VerbSimple).
    """

    pairs: list

    def render(self, add: Add) -> None:
        for i, (verb, object_list) in enumerate(self.pairs):
            if i:
                add(" ; ")
            _render_verb(verb, add)
            add(" ")
            object_list.render(add)

    @classmethod
    def create(cls, verb: object, *objects: object) -> PropertyListPathNotEmpty:
        """``verb`` may be a path, a Var, an IRI, or ``"a"`` (coerced to a path)."""
        return cls([(_coerce_verb_path(verb), ObjectListPath.create(*objects))])


#: PropertyListPath ::= PropertyListPathNotEmpty?
PropertyListPath = alias("PropertyListPath", PropertyListPathNotEmpty)


def _coerce_verb_path(verb: object) -> object:
    """A path verb must be a Path or a Var; lift a bare IRI or ``"a"`` into a path."""
    if isinstance(verb, (PathAlternative, Var)):
        return verb
    return PathAlternative.iri(verb)


@production(rule="TriplesSameSubject")
class TriplesSameSubject(Node):
    """TriplesSameSubject ::= VarOrTerm PropertyListNotEmpty | TriplesNode PropertyList | ReifiedTripleBlock"""

    subject: object
    property_list: PropertyListNotEmpty

    def render(self, add: Add) -> None:
        self.subject.render(add)
        add(" ")
        self.property_list.render(add)

    @classmethod
    def from_spo(cls, subject: object, predicate: object, obj: object) -> TriplesSameSubject:
        """One triple. ``predicate`` may be an IRI, a Var, or ``"a"``."""
        return cls(subject, PropertyListNotEmpty.create(predicate, obj))


@production(rule="TriplesSameSubjectPath")
class TriplesSameSubjectPath(Node):
    """TriplesSameSubjectPath ::= VarOrTerm PropertyListPathNotEmpty | TriplesNodePath PropertyListPath | ReifiedTripleBlockPath"""

    subject: object
    property_list_path: PropertyListPathNotEmpty

    def render(self, add: Add) -> None:
        self.subject.render(add)
        add(" ")
        self.property_list_path.render(add)

    @classmethod
    def from_spo(
        cls, subject: object, predicate: object, obj: object
    ) -> TriplesSameSubjectPath:
        """One triple pattern. ``predicate`` may be a path, IRI, Var, or ``"a"``."""
        return cls(subject, PropertyListPathNotEmpty.create(predicate, obj))


@production(rule="TriplesBlock")
class TriplesBlock(Node):
    """TriplesBlock ::= TriplesSameSubjectPath ( '.' TriplesBlock? )?

    Flattened: ``triples`` is a list, not a nested tail. Renders ``.``-separated.
    """

    triples: list = None

    def __post_init__(self) -> None:
        if self.triples is None:
            self.triples = []

    def render(self, add: Add) -> None:
        for i, triple in enumerate(self.triples):
            if i:
                add(" .\n")
            triple.render(add)

    @classmethod
    def from_tssp_list(cls, triples: list | None) -> TriplesBlock:
        """Accepted in source order, unlike the old linked-list builder."""
        return cls(list(triples) if triples else [])

    @classmethod
    def from_spo_list(cls, spo_list: list) -> TriplesBlock:
        """Build from ``(subject, predicate, object)`` tuples."""
        return cls([TriplesSameSubjectPath.from_spo(*spo) for spo in spo_list])

    def append(self, triple: TriplesSameSubjectPath) -> TriplesBlock:
        self.triples.append(triple)
        return self

    def extend(self, triples: list) -> TriplesBlock:
        self.triples.extend(triples)
        return self


@production(rule="ConstructTriples")
class ConstructTriples(Node):
    """ConstructTriples ::= TriplesSameSubject ( '.' ConstructTriples? )?

    Flattened, as with ``TriplesBlock``.
    """

    triples: list = None

    def __post_init__(self) -> None:
        if self.triples is None:
            self.triples = []

    def render(self, add: Add) -> None:
        for i, triple in enumerate(self.triples):
            if i:
                add(" .\n")
            triple.render(add)

    @classmethod
    def from_tss_list(cls, triples: list | None) -> ConstructTriples:
        return cls(list(triples) if triples else [])

    @classmethod
    def from_spo_list(cls, spo_list: list) -> ConstructTriples:
        return cls([TriplesSameSubject.from_spo(*spo) for spo in spo_list])

    def to_tss_list(self) -> list:
        return list(self.triples)

    def merge(self, other: ConstructTriples) -> ConstructTriples:
        """Combine two templates, dropping duplicates but keeping order."""
        seen = set()
        merged = []
        for triple in [*self.triples, *other.triples]:
            if triple not in seen:
                seen.add(triple)
                merged.append(triple)
        return ConstructTriples(merged)


@production(rule="TriplesTemplate")
class TriplesTemplate(Node):
    """TriplesTemplate ::= TriplesSameSubject ( '.' TriplesTemplate? )?

    Flattened, as with ``TriplesBlock``.
    """

    triples: list = None

    def __post_init__(self) -> None:
        if self.triples is None:
            self.triples = []

    def render(self, add: Add) -> None:
        for i, triple in enumerate(self.triples):
            if i:
                add(" .\n")
            triple.render(add)

    @classmethod
    def from_tss_list(cls, triples: list | None) -> TriplesTemplate:
        return cls(list(triples) if triples else [])


@production(rule="ConstructTemplate")
class ConstructTemplate(Node):
    """ConstructTemplate ::= '{' ConstructTriples? '}'"""

    construct_triples: ConstructTriples | None = None

    def render(self, add: Add) -> None:
        add("{\n")
        if self.construct_triples is not None:
            self.construct_triples.render(add)
            add("\n")
        add("}")


@production(rule="BlankNodePropertyList")
class BlankNodePropertyList(Node):
    """BlankNodePropertyList ::= '[' PropertyListNotEmpty ']'"""

    property_list: PropertyListNotEmpty

    def render(self, add: Add) -> None:
        add("[ ")
        self.property_list.render(add)
        add(" ]")


@production(rule="BlankNodePropertyListPath")
class BlankNodePropertyListPath(Node):
    """BlankNodePropertyListPath ::= '[' PropertyListPathNotEmpty ']'"""

    property_list_path: PropertyListPathNotEmpty

    def render(self, add: Add) -> None:
        add("[ ")
        self.property_list_path.render(add)
        add(" ]")


@production(rule="Collection")
class Collection(Node):
    """Collection ::= '(' GraphNode+ ')'"""

    graph_nodes: list

    def render(self, add: Add) -> None:
        add("( ")
        for i, node in enumerate(self.graph_nodes):
            if i:
                add(" ")
            node.render(add)
        add(" )")


@production(rule="CollectionPath")
class CollectionPath(Node):
    """CollectionPath ::= '(' GraphNodePath+ ')'"""

    graph_node_paths: list

    def render(self, add: Add) -> None:
        add("( ")
        for i, node in enumerate(self.graph_node_paths):
            if i:
                add(" ")
            node.render(add)
        add(" )")


#: TriplesNode ::= Collection | BlankNodePropertyList
TriplesNode = alias("TriplesNode", Union[Collection, BlankNodePropertyList])

#: TriplesNodePath ::= CollectionPath | BlankNodePropertyListPath
TriplesNodePath = alias(
    "TriplesNodePath", Union[CollectionPath, BlankNodePropertyListPath]
)


# ---------------------------------------------------------------------------
# SPARQL 1.2 reification and triple terms
# ---------------------------------------------------------------------------


@production(rule="VarOrReifierId")
class VarOrReifierId(Node):
    """VarOrReifierId ::= Var | iri | BlankNode

    Modelled as a class rather than an alias so ``Reifier`` can hold it directly.
    """

    value: object

    def render(self, add: Add) -> None:
        self.value.render(add)


@production(rule="Reifier")
class Reifier(Node):
    """Reifier ::= '~' VarOrReifierId?

    New in SPARQL 1.2.
    """

    reifier_id: object = None

    def render(self, add: Add) -> None:
        add("~")
        if self.reifier_id is not None:
            self.reifier_id.render(add)


@production(rule="TripleTerm")
class TripleTerm(Node):
    """TripleTerm ::= '<<(' TripleTermSubject Verb TripleTermObject ')>>'

    New in SPARQL 1.2.
    """

    subject: object
    verb: object
    object: object

    def render(self, add: Add) -> None:
        add("<<(")
        self.subject.render(add)
        add(" ")
        _render_verb(self.verb, add)
        add(" ")
        self.object.render(add)
        add(")>>")


@production(rule="TripleTermData")
class TripleTermData(Node):
    """TripleTermData ::= '<<(' TripleTermDataSubject ( iri | 'a' ) TripleTermDataObject ')>>'

    The ground form of a triple term, permitted in VALUES data blocks.
    """

    subject: object
    verb: object
    object: object

    def render(self, add: Add) -> None:
        add("<<(")
        self.subject.render(add)
        add(" ")
        _render_verb(self.verb, add)
        add(" ")
        self.object.render(add)
        add(")>>")


@production(rule="ReifiedTriple")
class ReifiedTriple(Node):
    """ReifiedTriple ::= '<<' ReifiedTripleSubject Verb ReifiedTripleObject Reifier? '>>'

    New in SPARQL 1.2.
    """

    subject: object
    verb: object
    object: object
    reifier: Reifier | None = None

    def render(self, add: Add) -> None:
        add("<<")
        self.subject.render(add)
        add(" ")
        _render_verb(self.verb, add)
        add(" ")
        self.object.render(add)
        if self.reifier is not None:
            add(" ")
            self.reifier.render(add)
        add(">>")


@production(rule="ReifiedTripleBlock")
class ReifiedTripleBlock(Node):
    """ReifiedTripleBlock ::= ReifiedTriple PropertyList"""

    reified_triple: ReifiedTriple
    property_list: PropertyListNotEmpty

    def render(self, add: Add) -> None:
        self.reified_triple.render(add)
        add(" ")
        self.property_list.render(add)


@production(rule="ReifiedTripleBlockPath")
class ReifiedTripleBlockPath(Node):
    """ReifiedTripleBlockPath ::= ReifiedTriple PropertyListPath"""

    reified_triple: ReifiedTriple
    property_list_path: PropertyListPathNotEmpty

    def render(self, add: Add) -> None:
        self.reified_triple.render(add)
        add(" ")
        self.property_list_path.render(add)


@production(rule="AnnotationBlock")
class AnnotationBlock(Node):
    """AnnotationBlock ::= '{|' PropertyListNotEmpty '|}'"""

    property_list: PropertyListNotEmpty

    def render(self, add: Add) -> None:
        add("{| ")
        self.property_list.render(add)
        add(" |}")


@production(rule="AnnotationBlockPath")
class AnnotationBlockPath(Node):
    """AnnotationBlockPath ::= '{|' PropertyListPathNotEmpty '|}'"""

    property_list_path: PropertyListPathNotEmpty

    def render(self, add: Add) -> None:
        add("{| ")
        self.property_list_path.render(add)
        add(" |}")


@production(rule="Annotation")
class Annotation(Node):
    """Annotation ::= ( Reifier | AnnotationBlock )*"""

    parts: list = None

    def __post_init__(self) -> None:
        if self.parts is None:
            self.parts = []

    def render(self, add: Add) -> None:
        for part in self.parts:
            add(" ")
            part.render(add)


@production(rule="AnnotationPath")
class AnnotationPath(Node):
    """AnnotationPath ::= ( Reifier | AnnotationBlockPath )*"""

    parts: list = None

    def __post_init__(self) -> None:
        if self.parts is None:
            self.parts = []

    def render(self, add: Add) -> None:
        for part in self.parts:
            add(" ")
            part.render(add)


# unions that need the reification classes -----------------------------------

_TERM_MEMBERS = (Var, IRI, PNAME_LN, PNAME_NS, RDFLiteral, BooleanLiteral)

#: TripleTermSubject ::= Var | iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | TripleTerm
TripleTermSubject = alias(
    "TripleTermSubject",
    Union[(*_TERM_MEMBERS, BLANK_NODE_LABEL, ANON, TripleTerm)],
)

#: TripleTermObject ::= Var | iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | TripleTerm
TripleTermObject = alias(
    "TripleTermObject",
    Union[(*_TERM_MEMBERS, BLANK_NODE_LABEL, ANON, TripleTerm)],
)

#: TripleTermDataSubject ::= iri
TripleTermDataSubject = alias("TripleTermDataSubject", Union[IRI, PNAME_LN, PNAME_NS])

#: TripleTermDataObject ::= iri | RDFLiteral | NumericLiteral | BooleanLiteral | TripleTermData
TripleTermDataObject = alias(
    "TripleTermDataObject",
    Union[IRI, PNAME_LN, PNAME_NS, RDFLiteral, BooleanLiteral, TripleTermData],
)

#: ReifiedTripleSubject ::= Var | iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | ReifiedTriple | TripleTerm
ReifiedTripleSubject = alias(
    "ReifiedTripleSubject",
    Union[(*_TERM_MEMBERS, BLANK_NODE_LABEL, ANON, ReifiedTriple, TripleTerm)],
)

#: ReifiedTripleObject ::= Var | iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | ReifiedTriple | TripleTerm
ReifiedTripleObject = alias(
    "ReifiedTripleObject",
    Union[(*_TERM_MEMBERS, BLANK_NODE_LABEL, ANON, ReifiedTriple, TripleTerm)],
)

#: GraphNode ::= VarOrTerm | TriplesNode | ReifiedTriple
GraphNode = alias(
    "GraphNode",
    Union[
        (*_TERM_MEMBERS, BLANK_NODE_LABEL, ANON, NIL, TripleTerm, Collection,
         BlankNodePropertyList, ReifiedTriple)
    ],
)

#: GraphNodePath ::= VarOrTerm | TriplesNodePath | ReifiedTriple
GraphNodePath = alias(
    "GraphNodePath",
    Union[
        (*_TERM_MEMBERS, BLANK_NODE_LABEL, ANON, NIL, TripleTerm, CollectionPath,
         BlankNodePropertyListPath, ReifiedTriple)
    ],
)


# ---------------------------------------------------------------------------
# Inline data (VALUES)
# ---------------------------------------------------------------------------

#: DataBlockValue ::= iri | RDFLiteral | NumericLiteral | BooleanLiteral | 'UNDEF' | TripleTermData
DataBlockValue = alias(
    "DataBlockValue",
    Union[IRI, PNAME_LN, PNAME_NS, RDFLiteral, BooleanLiteral, TripleTermData, str],
)


def _render_data_value(value: object, add: Add) -> None:
    if value == UNDEF:
        add("UNDEF")
    else:
        value.render(add)


@production(rule="InlineDataOneVar")
class InlineDataOneVar(Node):
    """InlineDataOneVar ::= Var '{' DataBlockValue* '}'"""

    variable: Var
    values: list = None

    def __post_init__(self) -> None:
        if self.values is None:
            self.values = []

    def render(self, add: Add) -> None:
        self.variable.render(add)
        add(" { ")
        for i, value in enumerate(self.values):
            if i:
                add(" ")
            _render_data_value(value, add)
        add(" }")


@production(rule="InlineDataFull")
class InlineDataFull(Node):
    """InlineDataFull ::= ( NIL | '(' Var* ')' ) '{' ( '(' DataBlockValue* ')' | NIL )* '}'

    ``rows`` is a list of value lists, one per row.
    """

    variables: list = None
    rows: list = None

    def __post_init__(self) -> None:
        if self.variables is None:
            self.variables = []
        if self.rows is None:
            self.rows = []

    def render(self, add: Add) -> None:
        if not self.variables:
            add("()")
        else:
            add("(")
            for i, variable in enumerate(self.variables):
                if i:
                    add(" ")
                variable.render(add)
            add(")")
        add(" { ")
        for i, row in enumerate(self.rows):
            if i:
                add(" ")
            if not row:
                add("()")
                continue
            add("(")
            for j, value in enumerate(row):
                if j:
                    add(" ")
                _render_data_value(value, add)
            add(")")
        add(" }")


#: DataBlock ::= InlineDataOneVar | InlineDataFull
DataBlock = alias("DataBlock", Union[InlineDataOneVar, InlineDataFull])


@production(rule="InlineData")
class InlineData(Node):
    """InlineData ::= 'VALUES' DataBlock"""

    data_block: object

    def render(self, add: Add) -> None:
        add("VALUES ")
        self.data_block.render(add)


@production(rule="ValuesClause")
class ValuesClause(Node):
    """ValuesClause ::= ( 'VALUES' DataBlock )?

    Renders nothing when empty, which is why it can sit unconditionally in
    ``Query`` and ``SubSelect``.
    """

    data_block: object = None

    def render(self, add: Add) -> None:
        if self.data_block is not None:
            add("\nVALUES ")
            self.data_block.render(add)


# ---------------------------------------------------------------------------
# Graph patterns
# ---------------------------------------------------------------------------


@production(rule="Filter")
class Filter(Node):
    """Filter ::= 'FILTER' Constraint"""

    constraint: object

    def render(self, add: Add) -> None:
        add("FILTER ")
        constraint = self.constraint
        # a bare expression needs brackets to be a legal constraint
        if isinstance(constraint, ConditionalOrExpression):
            add("(")
            constraint.render(add)
            add(")")
        else:
            constraint.render(add)


@production(rule="Bind")
class Bind(Node):
    """Bind ::= 'BIND' '(' Expression 'AS' Var ')'"""

    expression: ConditionalOrExpression
    var: Var

    def render(self, add: Add) -> None:
        add("BIND(")
        self.expression.render(add)
        add(" AS ")
        self.var.render(add)
        add(")")


@production(rule="OptionalGraphPattern")
class OptionalGraphPattern(Node):
    """OptionalGraphPattern ::= 'OPTIONAL' GroupGraphPattern"""

    group_graph_pattern: GroupGraphPattern

    def render(self, add: Add) -> None:
        add("OPTIONAL ")
        self.group_graph_pattern.render(add)


@production(rule="MinusGraphPattern")
class MinusGraphPattern(Node):
    """MinusGraphPattern ::= 'MINUS' GroupGraphPattern"""

    group_graph_pattern: GroupGraphPattern

    def render(self, add: Add) -> None:
        add("MINUS ")
        self.group_graph_pattern.render(add)


@production(rule="GraphGraphPattern")
class GraphGraphPattern(Node):
    """GraphGraphPattern ::= 'GRAPH' VarOrIri GroupGraphPattern"""

    varoriri: object
    group_graph_pattern: GroupGraphPattern

    def render(self, add: Add) -> None:
        add("GRAPH ")
        self.varoriri.render(add)
        add(" ")
        self.group_graph_pattern.render(add)


@production(rule="ServiceGraphPattern")
class ServiceGraphPattern(Node):
    """ServiceGraphPattern ::= 'SERVICE' 'SILENT'? VarOrIri GroupGraphPattern"""

    varoriri: object
    group_graph_pattern: GroupGraphPattern
    silent: bool = False

    def render(self, add: Add) -> None:
        add("SERVICE ")
        if self.silent:
            add("SILENT ")
        self.varoriri.render(add)
        add(" ")
        self.group_graph_pattern.render(add)


@production(rule="GroupOrUnionGraphPattern")
class GroupOrUnionGraphPattern(Node):
    """GroupOrUnionGraphPattern ::= GroupGraphPattern ( 'UNION' GroupGraphPattern )*"""

    group_graph_patterns: list

    def render(self, add: Add) -> None:
        for i, pattern in enumerate(self.group_graph_patterns):
            if i:
                add("\nUNION\n")
            pattern.render(add)


#: GraphPatternNotTriples ::= GroupOrUnionGraphPattern | OptionalGraphPattern | MinusGraphPattern | GraphGraphPattern | ServiceGraphPattern | Filter | Bind | InlineData
GraphPatternNotTriples = alias(
    "GraphPatternNotTriples",
    Union[
        GroupOrUnionGraphPattern,
        OptionalGraphPattern,
        MinusGraphPattern,
        GraphGraphPattern,
        ServiceGraphPattern,
        Filter,
        Bind,
        InlineData,
    ],
)


@production(rule="GroupGraphPatternSub")
class GroupGraphPatternSub(Node):
    """GroupGraphPatternSub ::= TriplesBlock? ( GraphPatternNotTriples '.'? TriplesBlock? )*

    Flattened to a single ordered ``patterns`` list holding ``TriplesBlock`` and
    ``GraphPatternNotTriples`` members in the order they should render. That is what
    makes incremental assembly (``add_triples``, ``add_pattern``) straightforward
    instead of requiring callers to manage interleaved parallel lists.
    """

    patterns: list = None

    def __post_init__(self) -> None:
        if self.patterns is None:
            self.patterns = []

    def render(self, add: Add) -> None:
        for i, pattern in enumerate(self.patterns):
            if i:
                add("\n")
            pattern.render(add)

    # -- incremental assembly ---------------------------------------------

    def add_pattern(self, pattern: object, prepend: bool = False) -> GroupGraphPatternSub:
        """Append (or prepend) a graph pattern."""
        if prepend:
            self.patterns.insert(0, pattern)
        else:
            self.patterns.append(pattern)
        return self

    def add_triples(self, triples: list, prepend: bool = False) -> GroupGraphPatternSub:
        """Add triple patterns, merging into an adjacent TriplesBlock when possible."""
        if not triples:
            return self
        if not prepend:
            for pattern in reversed(self.patterns):
                if isinstance(pattern, TriplesBlock):
                    pattern.extend(triples)
                    return self
                break
        return self.add_pattern(TriplesBlock.from_tssp_list(triples), prepend)

    def add_triple(self, triple: TriplesSameSubjectPath) -> GroupGraphPatternSub:
        return self.add_triples([triple])

    @property
    def triples(self) -> list:
        """Every triple pattern in this group, in order."""
        return [t for p in self.patterns if isinstance(p, TriplesBlock) for t in p.triples]

    def deduplicate_triples(self) -> GroupGraphPatternSub:
        """Drop duplicate triple patterns, preserving order.

        Possible because every node is hashable; the pydantic version had to
        compare rendered strings.
        """
        seen = set()
        for pattern in self.patterns:
            if isinstance(pattern, TriplesBlock):
                unique = []
                for triple in pattern.triples:
                    if triple not in seen:
                        seen.add(triple)
                        unique.append(triple)
                pattern.triples = unique
        return self


@production(rule="GroupGraphPattern")
class GroupGraphPattern(Node):
    """GroupGraphPattern ::= '{' ( SubSelect | GroupGraphPatternSub ) '}'"""

    content: object

    def render(self, add: Add) -> None:
        add("{\n")
        self.content.render(add)
        add("\n}")

    @classmethod
    def from_triples(cls, triples: list) -> GroupGraphPattern:
        return cls(GroupGraphPatternSub([TriplesBlock.from_tssp_list(triples)]))


@production(rule="WhereClause")
class WhereClause(Node):
    """WhereClause ::= 'WHERE'? GroupGraphPattern"""

    group_graph_pattern: GroupGraphPattern

    def render(self, add: Add) -> None:
        add("WHERE ")
        self.group_graph_pattern.render(add)

    @classmethod
    def from_triples(cls, triples: list) -> WhereClause:
        return cls(GroupGraphPattern.from_triples(triples))


# ---------------------------------------------------------------------------
# Solution modifiers
# ---------------------------------------------------------------------------


@production(rule="GroupCondition")
class GroupCondition(Node):
    """GroupCondition ::= BuiltInCall | FunctionCall | '(' Expression ( 'AS' Var )? ')' | Var"""

    content: object
    var: Var | None = None

    def render(self, add: Add) -> None:
        if self.var is not None:
            add("(")
            self.content.render(add)
            add(" AS ")
            self.var.render(add)
            add(")")
        elif isinstance(self.content, ConditionalOrExpression):
            add("(")
            self.content.render(add)
            add(")")
        else:
            self.content.render(add)


@production(rule="GroupClause")
class GroupClause(Node):
    """GroupClause ::= 'GROUP' 'BY' GroupCondition+"""

    conditions: list

    def render(self, add: Add) -> None:
        add("GROUP BY ")
        for i, condition in enumerate(self.conditions):
            if i:
                add(" ")
            condition.render(add)

    @classmethod
    def create(cls, *conditions: object) -> GroupClause:
        return cls(
            [c if isinstance(c, GroupCondition) else GroupCondition(c) for c in conditions]
        )


@production(rule="HavingCondition")
class HavingCondition(Node):
    """HavingCondition ::= Constraint"""

    constraint: object

    def render(self, add: Add) -> None:
        if isinstance(self.constraint, ConditionalOrExpression):
            add("(")
            self.constraint.render(add)
            add(")")
        else:
            self.constraint.render(add)


@production(rule="HavingClause")
class HavingClause(Node):
    """HavingClause ::= 'HAVING' HavingCondition+"""

    conditions: list

    def render(self, add: Add) -> None:
        add("HAVING ")
        for i, condition in enumerate(self.conditions):
            if i:
                add(" ")
            condition.render(add)

    @classmethod
    def create(cls, *constraints: object) -> HavingClause:
        return cls(
            [
                c if isinstance(c, HavingCondition) else HavingCondition(c)
                for c in constraints
            ]
        )


class OrderDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


@production(rule="OrderCondition")
class OrderCondition(Node):
    """OrderCondition ::= ( ( 'ASC' | 'DESC' ) BrackettedExpression ) | ( Constraint | Var )"""

    content: object
    direction: OrderDirection | None = None

    def render(self, add: Add) -> None:
        content = self.content
        if self.direction is not None:
            add(self.direction.value)
            if isinstance(content, BrackettedExpression):
                content.render(add)
            else:
                add("(")
                content.render(add)
                add(")")
        else:
            content.render(add)

    @classmethod
    def asc(cls, content: object) -> OrderCondition:
        return cls(content, OrderDirection.ASC)

    @classmethod
    def desc(cls, content: object) -> OrderCondition:
        return cls(content, OrderDirection.DESC)


@production(rule="OrderClause")
class OrderClause(Node):
    """OrderClause ::= 'ORDER' 'BY' OrderCondition+"""

    conditions: list

    def render(self, add: Add) -> None:
        add("ORDER BY ")
        for i, condition in enumerate(self.conditions):
            if i:
                add(" ")
            condition.render(add)

    @classmethod
    def create(cls, *conditions: object) -> OrderClause:
        return cls(
            [c if isinstance(c, OrderCondition) else OrderCondition(c) for c in conditions]
        )


@production(rule="LimitClause")
class LimitClause(Node):
    """LimitClause ::= 'LIMIT' INTEGER"""

    limit: INTEGER

    def render(self, add: Add) -> None:
        add("LIMIT ")
        self.limit.render(add)


@production(rule="OffsetClause")
class OffsetClause(Node):
    """OffsetClause ::= 'OFFSET' INTEGER"""

    offset: INTEGER

    def render(self, add: Add) -> None:
        add("OFFSET ")
        self.offset.render(add)


@production(rule="LimitOffsetClauses")
class LimitOffsetClauses(Node):
    """LimitOffsetClauses ::= LimitClause OffsetClause? | OffsetClause LimitClause?

    Both orders are legal; this renders LIMIT before OFFSET.
    """

    limit_clause: LimitClause | None = None
    offset_clause: OffsetClause | None = None

    def render(self, add: Add) -> None:
        if self.limit_clause is not None:
            self.limit_clause.render(add)
            if self.offset_clause is not None:
                add(" ")
        if self.offset_clause is not None:
            self.offset_clause.render(add)

    @classmethod
    def create(cls, limit: int | None = None, offset: int | None = None) -> LimitOffsetClauses:
        return cls(
            LimitClause(INTEGER(str(limit))) if limit is not None else None,
            OffsetClause(INTEGER(str(offset))) if offset is not None else None,
        )


@production(rule="SolutionModifier")
class SolutionModifier(Node):
    """SolutionModifier ::= GroupClause? HavingClause? OrderClause? LimitOffsetClauses?

    Every part is optional, so ``SolutionModifier()`` is a valid empty modifier.
    """

    group_by: GroupClause | None = None
    having: HavingClause | None = None
    order_by: OrderClause | None = None
    limit_offset: LimitOffsetClauses | None = None

    def render(self, add: Add) -> None:
        for part in (self.group_by, self.having, self.order_by, self.limit_offset):
            if part is not None:
                add("\n")
                part.render(add)


# ---------------------------------------------------------------------------
# Query forms
# ---------------------------------------------------------------------------


class SelectModifier(str, Enum):
    DISTINCT = "DISTINCT"
    REDUCED = "REDUCED"


@production(rule="SelectClause")
class SelectClause(Node):
    """SelectClause ::= 'SELECT' ( 'DISTINCT' | 'REDUCED' )? ( ( Var | ( '(' Expression 'AS' Var ')' ) )+ | '*' )

    ``variables`` holds ``Var`` entries, ``(expression, var)`` tuples for the
    ``(... AS ?v)`` form, or is empty for ``SELECT *``.
    """

    variables: list = None
    modifier: SelectModifier | None = None

    def __post_init__(self) -> None:
        if self.variables is None:
            self.variables = []

    def render(self, add: Add) -> None:
        add("SELECT ")
        if self.modifier is not None:
            add(self.modifier.value)
            add(" ")
        if not self.variables:
            add("*")
            return
        for i, variable in enumerate(self.variables):
            if i:
                add(" ")
            if isinstance(variable, tuple):
                expression, var = variable
                add("(")
                expression.render(add)
                add(" AS ")
                var.render(add)
                add(")")
            else:
                variable.render(add)

    @classmethod
    def create(cls, *variables: object, distinct: bool = False, reduced: bool = False) -> SelectClause:
        modifier = (
            SelectModifier.DISTINCT
            if distinct
            else SelectModifier.REDUCED
            if reduced
            else None
        )
        return cls(list(variables), modifier)


@production(rule="SourceSelector")
class SourceSelector(Node):
    """SourceSelector ::= iri"""

    iri: object

    def render(self, add: Add) -> None:
        self.iri.render(add)


@production(rule="DefaultGraphClause")
class DefaultGraphClause(Node):
    """DefaultGraphClause ::= SourceSelector"""

    source_selector: SourceSelector

    def render(self, add: Add) -> None:
        self.source_selector.render(add)


@production(rule="NamedGraphClause")
class NamedGraphClause(Node):
    """NamedGraphClause ::= 'NAMED' SourceSelector"""

    source_selector: SourceSelector

    def render(self, add: Add) -> None:
        add("NAMED ")
        self.source_selector.render(add)


@production(rule="DatasetClause")
class DatasetClause(Node):
    """DatasetClause ::= 'FROM' ( DefaultGraphClause | NamedGraphClause )"""

    content: object

    def render(self, add: Add) -> None:
        add("FROM ")
        self.content.render(add)

    @classmethod
    def create(cls, iri: object, named: bool = False) -> DatasetClause:
        selector = SourceSelector(iri)
        return cls(
            NamedGraphClause(selector) if named else DefaultGraphClause(selector)
        )


def _render_dataset_clauses(clauses: list | None, add: Add) -> None:
    for clause in clauses or ():
        add("\n")
        clause.render(add)


@production(rule="SelectQuery")
class SelectQuery(Node):
    """SelectQuery ::= SelectClause DatasetClause* WhereClause SolutionModifier"""

    select_clause: SelectClause
    where_clause: WhereClause
    solution_modifier: SolutionModifier = None
    dataset_clauses: list = None

    def __post_init__(self) -> None:
        if self.solution_modifier is None:
            self.solution_modifier = SolutionModifier()
        if self.dataset_clauses is None:
            self.dataset_clauses = []

    def render(self, add: Add) -> None:
        self.select_clause.render(add)
        _render_dataset_clauses(self.dataset_clauses, add)
        add("\n")
        self.where_clause.render(add)
        self.solution_modifier.render(add)


@production(rule="SubSelect")
class SubSelect(Node):
    """SubSelect ::= SelectClause WhereClause SolutionModifier ValuesClause"""

    select_clause: SelectClause
    where_clause: WhereClause
    solution_modifier: SolutionModifier = None
    values_clause: ValuesClause = None

    def __post_init__(self) -> None:
        if self.solution_modifier is None:
            self.solution_modifier = SolutionModifier()
        if self.values_clause is None:
            self.values_clause = ValuesClause()

    def render(self, add: Add) -> None:
        self.select_clause.render(add)
        add("\n")
        self.where_clause.render(add)
        self.solution_modifier.render(add)
        self.values_clause.render(add)


@production(rule="ConstructQuery")
class ConstructQuery(Node):
    """ConstructQuery ::= 'CONSTRUCT' ( ConstructTemplate DatasetClause* WhereClause SolutionModifier | DatasetClause* 'WHERE' ConstructTemplate SolutionModifier )

    The second branch (``CONSTRUCT WHERE { ... }``, with no explicit template) is
    selected by leaving ``construct_template`` unset and providing
    ``where_template``.
    """

    construct_template: ConstructTemplate | None = None
    where_clause: WhereClause | None = None
    solution_modifier: SolutionModifier = None
    dataset_clauses: list = None
    where_template: ConstructTemplate | None = None

    def __post_init__(self) -> None:
        if self.solution_modifier is None:
            self.solution_modifier = SolutionModifier()
        if self.dataset_clauses is None:
            self.dataset_clauses = []

    def render(self, add: Add) -> None:
        add("CONSTRUCT ")
        if self.construct_template is not None:
            self.construct_template.render(add)
            _render_dataset_clauses(self.dataset_clauses, add)
            add("\n")
            self.where_clause.render(add)
        else:
            _render_dataset_clauses(self.dataset_clauses, add)
            add("\nWHERE ")
            self.where_template.render(add)
        self.solution_modifier.render(add)


@production(rule="DescribeQuery")
class DescribeQuery(Node):
    """DescribeQuery ::= 'DESCRIBE' ( VarOrIri+ | '*' ) DatasetClause* WhereClause? SolutionModifier

    An empty ``variables`` list renders ``DESCRIBE *``.
    """

    variables: list = None
    where_clause: WhereClause | None = None
    solution_modifier: SolutionModifier = None
    dataset_clauses: list = None

    def __post_init__(self) -> None:
        if self.variables is None:
            self.variables = []
        if self.solution_modifier is None:
            self.solution_modifier = SolutionModifier()
        if self.dataset_clauses is None:
            self.dataset_clauses = []

    def render(self, add: Add) -> None:
        add("DESCRIBE ")
        if not self.variables:
            add("*")
        else:
            for i, variable in enumerate(self.variables):
                if i:
                    add(" ")
                variable.render(add)
        _render_dataset_clauses(self.dataset_clauses, add)
        if self.where_clause is not None:
            add("\n")
            self.where_clause.render(add)
        self.solution_modifier.render(add)


@production(rule="AskQuery")
class AskQuery(Node):
    """AskQuery ::= 'ASK' DatasetClause* WhereClause SolutionModifier"""

    where_clause: WhereClause
    solution_modifier: SolutionModifier = None
    dataset_clauses: list = None

    def __post_init__(self) -> None:
        if self.solution_modifier is None:
            self.solution_modifier = SolutionModifier()
        if self.dataset_clauses is None:
            self.dataset_clauses = []

    def render(self, add: Add) -> None:
        add("ASK")
        _render_dataset_clauses(self.dataset_clauses, add)
        add("\n")
        self.where_clause.render(add)
        self.solution_modifier.render(add)


@production(rule="Query")
class Query(Node):
    """Query ::= Prologue ( SelectQuery | ConstructQuery | DescribeQuery | AskQuery ) ValuesClause"""

    query: object
    prologue: Prologue = None
    values_clause: ValuesClause = None

    def __post_init__(self) -> None:
        if self.prologue is None:
            self.prologue = Prologue()
        if self.values_clause is None:
            self.values_clause = ValuesClause()

    def render(self, add: Add) -> None:
        self.prologue.render(add)
        self.query.render(add)
        self.values_clause.render(add)


@production(rule="QueryUnit")
class QueryUnit(Node):
    """QueryUnit ::= Query"""

    query: Query

    def render(self, add: Add) -> None:
        self.query.render(add)
