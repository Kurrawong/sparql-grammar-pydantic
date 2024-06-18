from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional, Generator, Tuple

from pydantic import (
    BaseModel,
    field_validator,
    model_validator,
    ValidationError,
)

from sparql_grammar_pydantic.terminals import IRIREF, PNAME_NS, PNAME_LN, VAR1, VAR2, DECIMAL, DOUBLE, INTEGER_POSITIVE, \
    DECIMAL_POSITIVE, DOUBLE_POSITIVE, INTEGER_NEGATIVE, DECIMAL_NEGATIVE, DOUBLE_NEGATIVE, STRING_LITERAL1, \
    STRING_LITERAL2, STRING_LITERAL_LONG1, STRING_LITERAL_LONG2, BlankNodeLabel, LANGTAG, INTEGER, NIL, Anon

log = logging.getLogger(__name__)


class SPARQLGrammarBase(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    def __str__(self):
        return "".join(part for part in self.render())

    def __repr__(self):
        return f"{self.__class__.__name__} ({self})"

    def render(self):
        raise NotImplementedError("Subclasses must implement this method.")

    def to_string(self):
        return self.__str__()

    def collect_triples(self) -> List[TriplesSameSubjectPath]:
        """
        Recursively collect TriplesSameSubjectPath instances from this object.
        """
        triples = []

        # Iterate through all attributes of the object
        for attribute_name in self.model_fields:
            attribute_value = getattr(self, attribute_name)

            # Check if the attribute is a TriplesSameSubjectPath and collect it
            if isinstance(attribute_value, TriplesSameSubjectPath):
                triples.append(attribute_value)

            # If the attribute is a list, iterate through it and collect TriplesSameSubjectPath
            elif isinstance(attribute_value, list):
                for item in attribute_value:
                    if isinstance(item, TriplesSameSubjectPath):
                        triples.append(item)
                    # If the item is an instance of BaseClass, recurse into it
                    elif isinstance(item, SPARQLGrammarBase):
                        triples.extend(item.collect_triples())

            # If the attribute is an instance of BaseClass, recurse into it
            elif isinstance(attribute_value, SPARQLGrammarBase):
                triples.extend(attribute_value.collect_triples())

        # deduplicate
        triples = list(set(triples))
        return triples


class QueryUnit(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rQueryUnit
    QueryUnit	  ::=  	Query
    """

    query: Query

    def render(self) -> Generator[str, None, None]:
        yield from self.query.render()


class Query(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rQuery
    Query	  ::=  	Prologue
    ( SelectQuery | ConstructQuery | DescribeQuery | AskQuery )
    ValuesClause
    """

    prologue: Prologue
    query: SelectQuery | ConstructQuery | DescribeQuery | AskQuery
    values_clause: ValuesClause

    def render(self) -> Generator[str, None, None]:
        yield from self.prologue.render()
        yield "\n"
        yield from self.query.render()
        yield from self.values_clause.render()


class Prologue(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPrologue
    Prologue	  ::=  	( BaseDecl | PrefixDecl )*
    """

    decls: Optional[List[BaseDecl | PrefixDecl]] = None

    def render(self) -> Generator[str, None, None]:
        for decl in self.decls:
            yield from decl.render()


class BaseDecl(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rBaseDecl
    BaseDecl	  ::=  	'BASE' IRIREF
    """

    iriref: IRIREF

    def render(self) -> Generator[str, None, None]:
        yield "BASE "
        yield from self.iriref.render()


class PrefixDecl(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPrefixDecl
    PrefixDecl	  ::=  	'PREFIX' PNAME_NS IRIREF
    """

    pname_ns: PNAME_NS
    iriref: IRIREF

    def render(self) -> Generator[str, None, None]:
        yield "PREFIX "
        yield from self.pname_ns.render()
        yield from self.iriref.render()


class SelectQuery(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rSelectQuery
    SelectQuery	  ::=  	SelectClause DatasetClause* WhereClause SolutionModifier
    """

    select_clause: SelectClause
    dataset_clauses: Optional[List[DatasetClause]] = None
    where_clause: WhereClause
    solution_modifier: SolutionModifier

    def render(self) -> Generator[str, None, None]:
        yield from self.select_clause.render()
        if self.dataset_clauses:
            for dataset_clause in self.dataset_clauses:
                yield from dataset_clause.render()
        yield from self.where_clause.render()
        yield from self.solution_modifier.render()


class SubSelect(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rSubSelect
    SubSelect	  ::=  	SelectClause WhereClause SolutionModifier ValuesClause
    """

    select_clause: SelectClause
    where_clause: WhereClause
    solution_modifier: SolutionModifier
    values_clause: ValuesClause

    def render(self):
        yield from self.select_clause.render()
        yield from self.where_clause.render()
        yield from self.solution_modifier.render()
        yield from self.values_clause.render()


class Wildcard(Enum):
    WILDCARD = "*"


class DistinctReduced(Enum):
    DISTINCT = "DISTINCT"
    REDUCED = "REDUCED"


class SelectClause(BaseModel):
    """
    https://www.w3.org/TR/sparql11-query/#rSelectClause
    SelectClause	  ::=  	'SELECT' ( 'DISTINCT' | 'REDUCED' )? ( ( Var | ( '(' Expression 'AS' Var ')' ) )+ | '*' )
    """

    distinct_or_reduced: Optional[DistinctReduced] = None
    variables_or_wildcard: List[Var | Tuple[Expression | Var]] | Wildcard

    def render(self):
        yield "SELECT"
        if self.distinct_or_reduced:
            yield self.distinct_or_reduced.value
        if isinstance(self.variables_or_wildcard, Wildcard):
            yield self.variables_or_wildcard.value
        else:
            for item in self.variables_or_wildcard:
                if isinstance(item, Var):
                    yield " "
                    yield from item.render()
                elif isinstance(item, Tuple):
                    expression, as_var = item
                    yield " ("
                    yield from expression.render()
                    yield " AS "
                    yield from as_var.render()
                    yield ")"


class ConstructQuery(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rConstructQuery
    ConstructQuery	  ::=  	'CONSTRUCT' ( ConstructTemplate DatasetClause* WhereClause SolutionModifier | DatasetClause* 'WHERE' '{' TriplesTemplate? '}' SolutionModifier )

    Currently simplified to only accept a ConstructTemplate, WhereClause, and SolutionModifier.
    """

    construct_template: ConstructTemplate
    where_clause: WhereClause
    solution_modifier: SolutionModifier

    def render(self) -> Generator[str, None, None]:
        yield "CONSTRUCT "
        yield from self.construct_template.render()
        yield from self.where_clause.render()
        yield from self.solution_modifier.render()


class DescribeQuery(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rDescribeQuery
    DescribeQuery	  ::=  	'DESCRIBE' ( VarOrIri+ | '*' ) DatasetClause* WhereClause? SolutionModifier
    """

    varoriri_or_all: VarOrIri | Wildcard
    dataset_clauses: Optional[List[DatasetClause]] = None
    where_clause: Optional[WhereClause] = None
    solution_modifier: SolutionModifier

    def render(self) -> Generator[str, None, None]:
        yield "DESCRIBE "
        if isinstance(self.varoriri_or_all, str):
            yield "*"
        else:
            yield from self.varoriri_or_all.render()
        if self.dataset_clauses:
            for dataset_clause in self.dataset_clauses:
                yield from dataset_clause.render()
        if self.where_clause:
            yield from self.where_clause.render()
        yield from self.solution_modifier.render()


class AskQuery(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rAskQuery
    AskQuery	  ::=  	'ASK' DatasetClause* WhereClause SolutionModifier
    """

    dataset_clauses: Optional[List[DatasetClause]] = None
    where_clause: WhereClause
    solution_modifier: SolutionModifier

    def render(self) -> Generator[str, None, None]:
        yield "ASK "
        if self.dataset_clauses:
            for dataset_clause in self.dataset_clauses:
                yield from dataset_clause.render()
        yield from self.where_clause.render()
        yield from self.solution_modifier.render()


class DatasetClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rDatasetClause
    DatasetClause	  ::=  	'FROM' ( DefaultGraphClause | NamedGraphClause )
    """

    default_or_named_graph_clause: DefaultGraphClause | NamedGraphClause

    def render(self) -> Generator[str, None, None]:
        yield "FROM "
        yield from self.default_or_named_graph_clause.render()


class DefaultGraphClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rDefaultGraphClause
    DefaultGraphClause	  ::=  	SourceSelector
    """

    source_selector: SourceSelector

    def render(self) -> Generator[str, None, None]:
        yield from self.source_selector.render()


class NamedGraphClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rNamedGraphClause
    NamedGraphClause	  ::=  	'NAMED' SourceSelector
    """

    source_selector: SourceSelector

    def render(self) -> Generator[str, None, None]:
        yield "NAMED "
        yield from self.source_selector.render()


class SourceSelector(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rSourceSelector
    SourceSelector	  ::=  	iri
    """

    iri: iri

    def render(self) -> Generator[str, None, None]:
        yield from self.iri.render()


class WhereClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rWhereClause
    WhereClause	  ::=  	'WHERE'? GroupGraphPattern
    """

    group_graph_pattern: GroupGraphPattern

    def render(self) -> Generator[str, None, None]:
        yield "\nWHERE "
        yield from self.group_graph_pattern.render()


class SolutionModifier(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rSolutionModifier
    SolutionModifier	  ::=  	GroupClause? HavingClause? OrderClause? LimitOffsetClauses?
    """

    group_by: Optional[GroupClause] = None
    having: Optional[HavingClause]
    order_by: Optional[OrderClause] = None
    limit_offset: Optional[LimitOffsetClauses] = None

    def render(self) -> str:
        if self.order_by:
            yield from self.order_by.render()
        if self.limit_offset:
            if self.order_by:
                yield "\n"
            yield from self.limit_offset.render()
        if self.group_by:
            yield from self.group_by.render()


class GroupClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rGroupClause
    GroupClause ::= 'GROUP' 'BY' GroupCondition+
    """

    group_conditions: List["GroupCondition"]

    def render(self) -> Generator[str, None, None]:
        yield "\nGROUP BY "
        for i, condition in enumerate(self.group_conditions):
            yield from condition.render()
            if i < len(self.group_conditions) - 1:  # Check if it's not the last triple
                yield " "


class GroupCondition(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rGroupCondition
    GroupCondition ::= BuiltInCall | FunctionCall | '(' Expression ( 'AS' Var )? ')' | Var
    """

    condition: BuiltInCall | FunctionCall | Tuple[Expression, Var] | Var

    def render(self) -> Generator[str, None, None]:
        if isinstance(self.condition, Tuple):
            yield "("
            yield from self.condition[0].render()
            yield " AS "
            yield from self.condition[1].render()
            yield ")"
        else:
            yield from self.condition.render()


class HavingClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rHavingClause
    HavingClause	  ::=  	'HAVING' HavingCondition+
    """

    having_conditions: List[HavingCondition]

    def render(self) -> Generator[str, None, None]:
        yield "\nHAVING "
        for i, condition in enumerate(self.having_conditions):
            yield from condition.render()
            if i < len(self.having_conditions) - 1:  # Check if it's not the last triple
                yield " "


class HavingCondition(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rHavingCondition
    HavingCondition	  ::=  	Constraint
    """

    constraint: Constraint

    def render(self) -> Generator[str, None, None]:
        yield from self.constraint.render()


class OrderClause(SPARQLGrammarBase):
    conditions: List[OrderCondition]

    def render(self):
        yield "\nORDER BY "
        yield " ".join(
            part for condition in self.conditions for part in condition.render()
        )


class OrderCondition(SPARQLGrammarBase):
    """
    Default direction is ASC if not specified
    """

    var: Var
    direction: Optional[str] = None

    def render(self):
        if self.direction:
            yield f"{self.direction}("
            yield from self.var.render()
            yield ")"
        else:
            yield from self.var.render()


class LimitOffsetClauses(SPARQLGrammarBase):
    """
    Represents the LIMIT and OFFSET clauses in SPARQL queries.
    According to the SPARQL grammar:
    LimitOffsetClauses ::= LimitClause OffsetClause? | OffsetClause LimitClause?
    """

    limit_clause: Optional[LimitClause] = None
    offset_clause: Optional[OffsetClause] = None

    def render(self) -> Generator[str, None, None]:
        if self.limit_clause:
            yield from self.limit_clause.render()
        if self.offset_clause:
            if self.limit_clause:
                yield "\n"
            yield from self.offset_clause.render()


class LimitClause(SPARQLGrammarBase):
    limit: int

    def render(self) -> Generator[str, None, None]:
        yield f"LIMIT {self.limit}"


class OffsetClause(SPARQLGrammarBase):
    offset: int

    def render(self) -> Generator[str, None, None]:
        yield f"OFFSET {self.offset}"


class ValuesClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rValuesClause
    ValuesClause	  ::=  	( 'VALUES' DataBlock )?
    """

    data_block: Optional[DataBlock]

    def render(self) -> Generator[str, None, None]:
        if self.data_block:
            yield "\n\tVALUES "
            yield from self.data_block.render()


class Update(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rUpdate
    Update ::= Prologue ( Update1 ( ';' Update )? )?
    """

    prologue: Optional[Prologue] = None
    update1: Optional["Update1"] = None
    update: Optional["Update"] = None

    def render(self) -> Generator[str, None, None]:
        if self.prologue:
            yield from self.prologue.render()
        if self.update1:
            yield from self.update1.render()
        if self.update:
            yield "; "
            yield from self.update.render()


class Update1(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rUpdate1
    Update1 ::= Load | Clear | Drop | Add | Move | Copy | Create | InsertData | DeleteData | DeleteWhere | Modify
    """

    update1: (
        Load
        | Clear
        | Drop
        | Add
        | Move
        | Copy
        | Create
        | InsertData
        | DeleteData
        | DeleteWhere
        | Modify
    )

    def render(self) -> Generator[str, None, None]:
        yield from self.update1.render()


class Load(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rLoad
    Load ::= 'LOAD' 'SILENT'? iri ( 'INTO' GraphRef )?
    """

    silent: bool = False
    iri: iri
    graph_ref: Optional[GraphRef] = None

    def render(self) -> Generator[str, None, None]:
        yield "LOAD "
        if self.silent:
            yield "SILENT "
        yield from self.iri.render()
        if self.graph_ref:
            yield " INTO "
            yield from self.graph_ref.render()


class Clear(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rClear
    Clear ::= 'CLEAR' 'SILENT'? GraphRefAll
    """

    silent: bool = False
    graph_ref_all: GraphRefAll

    def render(self) -> Generator[str, None, None]:
        yield "CLEAR "
        if self.silent:
            yield "SILENT "
        yield from self.graph_ref_all.render()


class Drop(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rDrop
    Drop ::= 'DROP' 'SILENT'? GraphRefAll
    """

    silent: bool = False
    graph_ref_all: GraphRefAll

    def render(self) -> Generator[str, None, None]:
        yield "DROP "
        if self.silent:
            yield "SILENT "
        yield from self.graph_ref_all.render()


class Create(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rCreate
    Create ::= 'CREATE' 'SILENT'? GraphRef
    """

    silent: bool = False
    graph_ref: GraphRef

    def render(self) -> Generator[str, None, None]:
        yield "CREATE "
        if self.silent:
            yield "SILENT "
        yield from self.graph_ref.render()


class Add(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rAdd
    Add ::= 'ADD' 'SILENT'? GraphOrDefault 'TO' GraphOrDefault
    """

    silent: bool = False
    from_graph: GraphOrDefault
    to_graph: GraphOrDefault

    def render(self) -> Generator[str, None, None]:
        yield "ADD "
        if self.silent:
            yield "SILENT "
        yield from self.from_graph.render()
        yield " TO "
        yield from self.to_graph.render()


class Move(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rMove
    Move ::= 'MOVE' 'SILENT'? GraphOrDefault 'TO' GraphOrDefault
    """

    silent: bool = False
    from_graph: GraphOrDefault
    to_graph: GraphOrDefault

    def render(self) -> Generator[str, None, None]:
        yield "MOVE "
        if self.silent:
            yield "SILENT "
        yield from self.from_graph.render()
        yield " TO "
        yield from self.to_graph.render()


class Copy(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rCopy
    Copy ::= 'COPY' 'SILENT'? GraphOrDefault 'TO' GraphOrDefault
    """

    silent: bool = False
    from_graph: GraphOrDefault
    to_graph: GraphOrDefault

    def render(self) -> Generator[str, None, None]:
        yield "COPY "
        if self.silent:
            yield "SILENT "
        yield from self.from_graph.render()
        yield " TO "
        yield from self.to_graph.render()


class InsertData(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rInsertData
    InsertData ::= 'INSERT DATA' QuadData
    """

    quad_data: QuadData

    def render(self) -> Generator[str, None, None]:
        yield "INSERT DATA "
        yield from self.quad_data.render()


class DeleteData(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rDeleteData
    DeleteData ::= 'DELETE DATA' QuadData
    """

    quad_data: QuadData

    def render(self) -> Generator[str, None, None]:
        yield "DELETE DATA "
        yield from self.quad_data.render()


class DeleteWhere(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rDeleteWhere
    DeleteWhere ::= 'DELETE WHERE' QuadPattern
    """

    quad_pattern: QuadPattern

    def render(self) -> Generator[str, None, None]:
        yield "DELETE WHERE "
        yield from self.quad_pattern.render()


class Modify(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rModify
    Modify	  ::=  	( 'WITH' iri )? ( DeleteClause InsertClause? | InsertClause ) UsingClause* 'WHERE' GroupGraphPattern
    """

    with_iri: Optional[iri] = None
    delete_insert_or_insert: (
        DeleteClause | Tuple[DeleteClause, InsertClause] | InsertClause
    )
    using_clauses: Optional[List[UsingClause]] = None
    group_graph_pattern: GroupGraphPattern

    def render(self) -> Generator[str, None, None]:
        if self.with_iri:
            yield "WITH "
            yield from self.with_iri.render()
        if isinstance(self.delete_insert_or_insert, tuple):
            delete_clause, insert_clause = self.delete_insert_or_insert
            yield from delete_clause.render()
            yield from insert_clause.render()
        else:
            yield from self.delete_insert_or_insert.render()
        if self.using_clauses:
            for using_clause in self.using_clauses:
                yield from using_clause.render()
        yield "WHERE "
        yield from self.group_graph_pattern.render()


class DeleteClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rDeleteClause
    DeleteClause	  ::=  	'DELETE' QuadPattern
    """

    quad_pattern: QuadPattern

    def render(self) -> Generator[str, None, None]:
        yield "DELETE "
        yield from self.quad_pattern.render()


class InsertClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rInsertClause
    InsertClause	  ::=  	'INSERT' QuadPattern
    """

    quad_pattern: QuadPattern

    def render(self) -> Generator[str, None, None]:
        yield "INSERT "
        yield from self.quad_pattern.render()


class UsingClause(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rUsingClause
    UsingClause	  ::=  	'USING' ( iri | 'NAMED' iri )
    """

    iri: iri
    named: bool = False

    def render(self) -> Generator[str, None, None]:
        yield "USING "
        if self.named:
            yield "NAMED "
        yield from self.iri.render()


class GraphOrDefaultOptions(Enum):
    DEFAULT = "DEFAULT"
    GRAPH = "GRAPH"


class GraphOrDefault(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rGraphOrDefault
    GraphOrDefault	  ::=  	'DEFAULT' | 'GRAPH'? iri
    """

    graph_or_default: Optional[GraphOrDefaultOptions] = None
    iri: Optional[iri] = None

    def render(self) -> Generator[str, None, None]:
        if self.graph_or_default:
            yield self.graph_or_default.value
        if self.iri:
            yield from self.iri.render()


class GraphRef(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rGraphRef
    GraphRef	  ::=  	'GRAPH' iri
    """

    iri: iri

    def render(self) -> Generator[str, None, None]:
        yield "GRAPH "
        yield from self.iri.render()


class GraphRefOptions(Enum):
    DEFAULT = "DEFAULT"
    NAMED = "NAMED"
    ALL = "ALL"


class GraphRefAll(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rGraphRefAll
    GraphRefAll	  ::=  	GraphRef | 'DEFAULT' | 'NAMED' | 'ALL'
    """

    option: GraphRef | GraphRefOptions

    def render(self) -> Generator[str, None, None]:
        if isinstance(self.option, GraphRef):
            yield from self.option.render()
        else:
            yield self.option.value


class QuadPattern(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rQuadPattern
    QuadPattern	  ::=  	'{' Quads '}'
    """

    quads: Quads

    def render(self) -> Generator[str, None, None]:
        yield "{ "
        yield from self.quads.render()
        yield " }"


class QuadData(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rQuadData
    QuadData	  ::=  	'{' Quads '}'
    """

    quads: Quads

    def render(self) -> Generator[str, None, None]:
        yield "{ "
        yield from self.quads.render()
        yield " }"


class Quads(BaseModel):
    triples_templates: List[TriplesTemplate]
    quads_not_triples: Optional[List[QuadsNotTriples]] = None

    @model_validator(mode="after")
    def validate_templates_and_quads(self):
        tt_len = len(self.triples_templates)
        qnt_len = len(self.quads_not_triples)
        if tt_len < 1:
            raise ValueError("There must be at least one TriplesTemplate")
        if tt_len > 1 and qnt_len < tt_len - 1:
            raise ValueError(
                "When there is more than one TriplesTemplate there must be at least N-1 QuadsNotTriples"
            )
        return self

    def render(self) -> Generator[str, None, None]:
        if self.triples_templates:
            yield from self.triples_templates[0].render()
        for i in range(len(self.quads_not_triples)):
            yield from self.quads_not_triples[i].render()
            yield " ."
            if i + 1 < len(self.triples_templates):
                yield from self.triples_templates[i + 1].render()


class QuadsNotTriples(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rQuadsNotTriples
    QuadsNotTriples	  ::=  	'GRAPH' VarOrIri '{' TriplesTemplate? '}'
    """

    var_or_iri: VarOrIri
    triples_template: Optional[TriplesTemplate] = None

    def render(self) -> Generator[str, None, None]:
        yield "GRAPH "
        yield from self.var_or_iri.render()
        yield " {"
        if self.triples_template:
            yield from self.triples_template.render()
        yield "}"


class TriplesTemplate(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-update/#rTriplesTemplate
    TriplesTemplate	  ::=  	TriplesSameSubject ( '.' TriplesTemplate? )?
    """

    triples_same_subject: TriplesSameSubject
    triples_template: Optional[TriplesTemplate] = None

    def render(self) -> Generator[str, None, None]:
        yield from self.triples_same_subject_path.render()
        if self.triples_template:
            yield " ."
            yield from self.triples_template.render()


class GroupGraphPattern(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rGroupGraphPattern
    GroupGraphPattern	  ::=  	'{' ( SubSelect | GroupGraphPatternSub ) '}'
    """

    content: SubSelect | GroupGraphPatternSub

    def render(self) -> Generator[str, None, None]:
        yield "{\n"
        yield from self.content.render()
        yield "\n}"


class GroupGraphPatternSub(BaseModel):
    """
    https://www.w3.org/TR/sparql11-query/#rGroupGraphPatternSub
    GroupGraphPatternSub	  ::=  	TriplesBlock? ( GraphPatternNotTriples '.'? TriplesBlock? )*
    """

    triples_blocks: List[TriplesBlock]
    graph_patterns_not_triples: Optional[List[GraphPatternNotTriples]] = None

    @model_validator(mode="after")
    def validate_blocks_and_patterns(self):
        tb_len = len(self.triples_blocks)
        gpnt_len = len(self.graph_patterns_not_triples)
        if tb_len < 1:
            raise ValueError("There must be at least one TriplesBlock")
        if tb_len > 1 and gpnt_len < tb_len - 1:
            raise ValueError(
                "When there is more than one TriplesBlock there must be at least N-1 GraphPatternNotTriples"
            )
        return self

    def render(self) -> Generator[str, None, None]:
        if self.triples_blocks:
            yield from self.triples_blocks[0].render()
        if self.graph_patterns_not_triples:
            for i in range(len(self.graph_patterns_not_triples)):
                yield from self.graph_patterns_not_triples[i].render()
                yield " ."
                if i + 1 < len(self.triples_blocks):
                    yield from self.triples_blocks[i + 1].render()


class TriplesBlock(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rTriplesBlock
    TriplesBlock	  ::=  	TriplesSameSubjectPath ( '.' TriplesBlock? )?
    """

    triples: TriplesSameSubjectPath = None
    triples_block: Optional[TriplesBlock] = None

    def render(self) -> Generator[str, None, None]:
        if isinstance(self.triples, list):
            for i, triple in enumerate(self.triples):
                yield from triple.render()
                # if i < len(self.triples) - 1:  # Check if it's not the last triple
                yield "\n"
        else:
            yield from self.triples.render()
            if self.triples_block:
                yield " .\n"
                yield from self.triples_block.render()
                yield "\n"

    # TODO check if subject is same, if so, absorb into existing triples same subject path
    @classmethod
    def from_tssp_list(cls, tssp_list: Optional[List[TriplesSameSubjectPath]]):
        if tssp_list:
            tssp_iter = iter(tssp_list)
            first_tssp = next(tssp_iter)
            tb = cls(triples=first_tssp)
            for tssp in tssp_iter:
                tb = cls(triples=tssp, triples_block=tb)
            return tb


class GraphPatternNotTriples(SPARQLGrammarBase):
    """
    Partially implemented
    https://www.w3.org/TR/sparql11-query/#rGraphPatternNotTriples
    GraphPatternNotTriples	  ::=  	GroupOrUnionGraphPattern | OptionalGraphPattern | MinusGraphPattern | GraphGraphPattern | ServiceGraphPattern | Filter | Bind | InlineData
    """

    content: (
        GroupOrUnionGraphPattern | OptionalGraphPattern | Filter | Bind | InlineData
    )


def render(self) -> Generator[str, None, None]:
    yield "\n"
    yield from self.content.render()


class OptionalGraphPattern(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rOptionalGraphPattern
    OptionalGraphPattern	  ::=  	'OPTIONAL' GroupGraphPattern
    """

    group_graph_pattern: GroupGraphPattern

    def render(self) -> Generator[str, None, None]:
        yield "\nOPTIONAL "
        yield from self.group_graph_pattern.render()


class GraphGraphPattern(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rGraphGraphPattern
    GraphGraphPattern	  ::=  	'GRAPH' VarOrIri GroupGraphPattern
    """

    var_or_iri: VarOrIri
    group_graph_pattern: GroupGraphPattern

    def render(self) -> Generator[str, None, None]:
        yield "\nGRAPH "
        yield from self.var_or_iri.render()
        yield from self.group_graph_pattern.render()


class ServiceGraphPattern(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rServiceGraphPattern
    ServiceGraphPattern	  ::=  	'SERVICE' 'SILENT'? VarOrIri GroupGraphPattern
    """

    silent: bool = False
    var_or_iri: VarOrIri
    group_graph_pattern: GroupGraphPattern

    def render(self) -> Generator[str, None, None]:
        yield "SERVICE "
        if self.silent:
            yield "SILENT "
        yield from self.var_or_iri.render()
        yield from self.group_graph_pattern.render()


class Bind(SPARQLGrammarBase):
    """
    Bind	  ::=  	'BIND' '(' Expression 'AS' Var ')'
    https://www.w3.org/TR/sparql11-query/#rBind
    """

    expression: Expression
    var: Var

    def render(self) -> Generator[str, None, None]:
        yield f"BIND("
        yield from self.expression.render()
        yield f" AS "
        yield from self.var.render()
        yield ")"


class InlineData(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rInlineData
    InlineData	  ::=  	'VALUES' DataBlock
    """

    data_block: DataBlock

    def render(self) -> Generator[str, None, None]:
        yield "\n\tVALUES "
        yield from self.data_block.render()


class DataBlock(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rDataBlock
    DataBlock	  ::=  	InlineDataOneVar | InlineDataFull
    """

    block: InlineDataOneVar | InlineDataFull

    def render(self) -> Generator[str, None, None]:
        yield from self.block.render()


class InlineDataOneVar(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rInlineDataOneVar
    InlineDataOneVar	  ::=  	Var '{' DataBlockValue* '}'
    """

    variable: Var
    datablockvalues: List[DataBlockValue]

    def render(self) -> Generator[str, None, None]:
        yield from self.variable.render()
        yield "{ "
        for value in self.datablockvalues:
            yield from value.render()
            yield " "
        yield " }"


class InlineDataFull(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rInlineDataFull
    ( NIL | '(' Var* ')' ) '{' ( '(' DataBlockValue* ')' | NIL )* '}'
    """

    vars: NIL | List[Var]
    datablocks: List[List[DataBlockValue] | NIL]

    def render(self) -> Generator[str, None, None]:
        if self.vars:
            yield "("
            for var in self.vars:
                yield from var.render()
                yield " "
            yield ") {"
        else:
            yield "{"

        if self.datablocks is None:
            yield "()"
        else:
            for data_block in self.datablocks:
                if data_block:
                    yield "("
                    for value in data_block:
                        yield from value.render()
                        yield " "
                    yield ")"
                    yield "\n"
                else:
                    yield "()"
        yield "}"


class UndefEnum(Enum):
    UNDEF = "UNDEF"


class DataBlockValue(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rDataBlockValue
    DataBlockValue	  ::=  	iri | RDFLiteral | NumericLiteral | BooleanLiteral | 'UNDEF'
    """

    value: iri | RDFLiteral | NumericLiteral | BooleanLiteral | UndefEnum

    def render(self) -> Generator[str, None, None]:
        if isinstance(self.value, UndefEnum):
            yield self.value
        else:
            yield from self.value.render()


class MinusGraphPattern(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rMinusGraphPattern
    MinusGraphPattern	  ::=  	'MINUS' GroupGraphPattern
    """

    group_graph_pattern: GroupGraphPattern

    def render(self) -> Generator[str, None, None]:
        yield "MINUS "
        yield from self.group_graph_pattern.render()


class GroupOrUnionGraphPattern(SPARQLGrammarBase):
    """
    For UNION statements
    https://www.w3.org/TR/sparql11-query/#rGroupOrUnionGraphPattern
    GroupOrUnionGraphPattern	  ::=  	GroupGraphPattern ( 'UNION' GroupGraphPattern )*
    """

    group_graph_patterns: List[GroupGraphPattern]

    def render(self) -> Generator[str, None, None]:
        ggps_iter = iter(self.group_graph_patterns)
        first_ggp = next(ggps_iter)

        yield "\n"
        yield from first_ggp.render()
        for ggp in ggps_iter:  # UNION goes between 2:N group graph patterns
            yield "\nUNION\n"
            yield from ggp.render()


class Filter(SPARQLGrammarBase):
    """
    Represents a SPARQL FILTER clause.
    Filter ::= 'FILTER' Constraint
    """

    constraint: Constraint

    def render(self) -> Generator[str, None, None]:
        yield "FILTER "
        yield from self.constraint.render()

    @classmethod
    def filter_relational(
        cls,
        focus: PrimaryExpression,
        comparators: PrimaryExpression | List[PrimaryExpression],
        operator: str,
    ) -> Filter:
        """
        Convenience method to create a FILTER clause to compare the focus node to comparators.
        """
        # Wrap the focus in an NumericExpression
        numeric_left = NumericExpression(
            additive_expression=AdditiveExpression(
                base_expression=MultiplicativeExpression(
                    base_expression=UnaryExpression(primary_expression=focus)
                )
            )
        )
        # for operators in '=', '!=', '<', '>', '<=', '>='
        if isinstance(comparators, PrimaryExpression):
            assert operator not in [
                "IN",
                "NOT IN",
            ], "an ExpressionList must be supplied for 'IN' or 'NOT IN'"
            expression_rhs = NumericExpression(
                additive_expression=AdditiveExpression(
                    base_expression=MultiplicativeExpression(
                        base_expression=UnaryExpression(primary_expression=comparators)
                    )
                )
            )
        else:  # for operators 'IN' and 'NOT IN'
            # Wrap each comparator in an Expression
            assert operator in ["IN", "NOT IN"]
            comparator_exprs = [
                Expression.from_primary_expression(comp) for comp in comparators
            ]
            expression_rhs = ExpressionList(expressions=comparator_exprs)
        # Build the RelationalExpression
        relational_expr = RelationalExpression(
            left=numeric_left, operator=operator, right=expression_rhs
        )
        # Build the ValueLogical to wrap the RelationalExpression
        value_logical = ValueLogical(relational_expression=relational_expr)
        # Build the ConditionalAndExpression to wrap the ValueLogical
        conditional_and_expr = ConditionalAndExpression(value_logicals=[value_logical])
        # Build the ConditionalOrExpression to wrap the ConditionalAndExpression
        conditional_or_expr = ConditionalOrExpression(
            conditional_and_expressions=[conditional_and_expr]
        )
        expression = Expression(conditional_or_expression=conditional_or_expr)
        # Create and return the Filter
        bracketted_expr = BrackettedExpression(expression=expression)
        return cls(constraint=Constraint(content=bracketted_expr))


class Constraint(SPARQLGrammarBase):
    """
    Represents a SPARQL Constraint.
    Constraint ::= BrackettedExpression | BuiltInCall | FunctionCall
    """

    content: BrackettedExpression | BuiltInCall | FunctionCall

    def render(self) -> Generator[str, None, None]:
        yield from self.content.render()


class FunctionCall(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rFunctionCall
    FunctionCall	  ::=  	iri ArgList
    """

    iri: iri
    arg_list: ArgList

    def render(self) -> Generator[str, None, None]:
        yield from self.iri.render()
        yield from self.arg_list.render()


class ArgList(SPARQLGrammarBase):
    """
    Represents a SPARQL ArgList.
    ArgList ::= NIL | '(' 'DISTINCT'? Expression ( ',' Expression )* ')'
    """

    expressions: Optional[NIL | List[Expression]]
    distinct: bool = False

    def render(self) -> Generator[str, None, None]:
        if isinstance(self.expressions, NIL):
            yield from self.expressions.render()
        else:
            if self.distinct:
                yield "DISTINCT "
            yield "("
            for i, expr in enumerate(self.expressions):
                yield from expr.render()
                if i < len(self.expressions) - 1:
                    yield ", "
            yield ")"


class ExpressionList(SPARQLGrammarBase):
    expressions: Optional[List[Expression]] = []

    def render(self) -> Generator[str, None, None]:
        if not self.expressions:
            yield "()"
        else:
            yield "("
            for i, expression in enumerate(self.expressions):
                yield from expression.render()
                if i < len(self.expressions) - 1:
                    yield ", "
            yield ")"


class ConstructTemplate(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rConstructTemplate
    ConstructTemplate	  ::=  	'{' ConstructTriples? '}'
    """

    construct_triples: Optional[ConstructTriples] = None

    def render(self) -> Generator[str, None, None]:
        if self.construct_triples:
            yield "{\n"
            yield from self.construct_triples.render()
            yield "\n}"

    def __hash__(self):
        return hash(self.construct_triples)


class ConstructTriples(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rConstructTriples
    ConstructTriples	  ::=  	TriplesSameSubject ( '.' ConstructTriples? )?
    """

    triples: TriplesSameSubject
    construct_triples: Optional[ConstructTriples] = None

    def render(self) -> Generator[str, None, None]:
        yield from self.triples.render()
        if self.construct_triples:
            yield " .\n"
            yield from self.construct_triples.render()

    @classmethod
    def from_tss_list(cls, tss_list: List[TriplesSameSubject]):
        tss_iter = iter(tss_list)
        first_tss = next(tss_iter)
        ct = cls(triples=first_tss)
        for tss in tss_iter:
            ct = cls(triples=tss, construct_triples=ct)
        return ct

    def to_tss_list(self):
        tss_list = []
        ct = self
        while ct:
            tss_list.append(ct.triples)
            ct = ct.construct_triples
        return tss_list

    @classmethod
    def merge_ct(cls, ct_list: List[ConstructTriples]):
        """
        Merges a list of ConstructTriples objects into a single ConstructTriples.
        """
        ct_iter = iter(ct_list)
        try:
            first_ct = next(
                ct_iter
            )  # Start with the first ConstructTriples in the list
        except StopIteration:
            return None  # Return None if the list is empty

        current_ct = first_ct
        for next_ct in ct_iter:
            # Traverse to the last construct_triples that does not have a nested construct_triples
            while current_ct.construct_triples is not None:
                current_ct = current_ct.construct_triples
            # Link the next ConstructTriples in the list to the bottom of the current tree
            current_ct.construct_triples = next_ct
            current_ct = next_ct  # Move the pointer to the newly added ConstructTriples

        return first_ct


class TriplesSameSubject(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rTriplesSameSubject
    TriplesSameSubject	  ::=  	VarOrTerm PropertyListNotEmpty | TriplesNode PropertyList
    """

    content: Tuple[VarOrTerm, PropertyListNotEmpty] | Tuple[TriplesNode, PropertyList]

    def render(self):
        yield from self.content[0].render()
        yield " "
        yield from self.content[1].render()

    def __hash__(self):
        return hash(self.content)

    @classmethod
    def from_spo(
        cls,
        subject: Var | iri | BlankNode,
        predicate: Var | iri,
        object: Var | iri | BlankNode,
    ):
        """
        Convenience method to create a TriplesSameSubject from a subject, predicate, and object.
        Currently supports only Var and iri types for subject, predicate, and object.
        """
        # Handle subjects
        if isinstance(subject, Var):
            s_vot = VarOrTerm(varorterm=subject)
        elif isinstance(subject, (iri, BlankNode)):
            s_vot = VarOrTerm(varorterm=GraphTerm(content=subject))
        else:
            raise ValueError("s must be a Var, iri or BlankNode")

        # Handle predicates
        if isinstance(predicate, (Var, iri)):
            verb = Verb(varoriri=VarOrIri(varoriri=predicate))
        else:
            raise ValueError("p must be a Var or iri")

        # Handle objects
        if isinstance(object, Var):
            o_vot = VarOrTerm(varorterm=object)
        elif isinstance(object, (iri, BlankNode)):
            o_vot = VarOrTerm(varorterm=GraphTerm(content=object))
        else:
            raise ValueError("o must be a Var, iri or BlankNode")

        return cls(
            content=(
                s_vot,
                PropertyListNotEmpty(
                    verb_objectlist=[
                        (
                            verb,
                            ObjectList(
                                list_object=[
                                    Object(
                                        graphnode=GraphNode(
                                            varorterm_or_triplesnode=o_vot
                                        )
                                    )
                                ]
                            ),
                        )
                    ]
                ),
            )
        )


class PropertyList(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPropertyList
    PropertyList	  ::=  	PropertyListNotEmpty?
    """

    plne: Optional[PropertyListNotEmpty] = None

    def render(self):
        if self.plne:
            yield from self.plne.render()

    def __hash__(self):
        return hash(self.plne)


class PropertyListNotEmpty(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPropertyListNotEmpty
    PropertyListNotEmpty	  ::=  	Verb ObjectList ( ';' ( Verb ObjectList )? )*
    """

    verb_objectlist: List[Tuple[Verb, ObjectList]]

    def render(self):
        vo_iter = iter(self.verb_objectlist)
        first_vo = next(vo_iter)
        yield from first_vo[0].render()  # verb
        yield " "
        yield from first_vo[1].render()  # objectlist
        for item in vo_iter:
            yield ";"
            yield from item[0].render()  # verb
            yield " "
            yield from item[1].render()  # objectlist


class VerbRDFType(Enum):
    A = "a"


class Verb(SPARQLGrammarBase):
    varoriri_or_a: VarOrIri | VerbRDFType

    def render(self):
        if isinstance(self.varoriri_or_a, VarOrIri):
            yield from self.varoriri_or_a.render()
        else:
            yield self.varoriri_or_a.value


class ObjectList(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rObjectList
    ObjectList	  ::=  	Object ( ',' Object )*
    """

    list_object: List[Object]

    def render(self):
        object_iter = iter(self.list_object)
        first_o = next(object_iter)
        yield from first_o.render()
        for item in object_iter:
            yield ","
            yield from item.render()

    def __hash__(self):
        return hash(tuple(self.list_object))


class Object(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rObject
    Object	  ::=  	GraphNode
    """

    graphnode: GraphNode

    def render(self):
        yield from self.graphnode.render()


class TriplesSameSubjectPath(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rTriplesSameSubjectPath
    TriplesSameSubjectPath	  ::=  	VarOrTerm PropertyListPathNotEmpty | TriplesNodePath PropertyListPath
    """

    content: (
        Tuple[VarOrTerm, PropertyListPathNotEmpty]
        | Tuple[TriplesNodePath, PropertyListPath]
    )

    def render(self):
        yield from self.content[0].render()
        yield " "
        yield from self.content[1].render()

    def __hash__(self):
        return hash(self.content)

    @classmethod
    def from_spo(
        cls,
        subject: Var | iri | BlankNode,
        predicate: Var | iri,
        object: Var | iri | BlankNode,
    ):
        """
        Convenience method to create a TriplesSameSubjectPath from a subject, predicate, and object.
        Currently supports only Var and iri types for subject, predicate, and object.
        """
        # Handle subjects
        if isinstance(subject, Var):
            s_vot = VarOrTerm(varorterm=subject)
        elif isinstance(subject, (iri, BlankNode)):
            s_vot = VarOrTerm(varorterm=GraphTerm(content=subject))
        else:
            raise ValueError("s must be a Var, iri or BlankNode")

        # Handle predicates
        if isinstance(predicate, Var):
            verb = VerbSimple(var=predicate)
        elif isinstance(predicate, iri):
            verb = VerbPath(
                path=SG_Path(
                    path_alternative=PathAlternative(
                        sequence_paths=[
                            PathSequence(
                                list_path_elt_or_inverse=[
                                    PathEltOrInverse(
                                        path_elt=PathElt(
                                            path_primary=PathPrimary(
                                                value=predicate,
                                            )
                                        )
                                    )
                                ]
                            )
                        ]
                    )
                )
            )
        else:
            raise ValueError("p must be a Var or iri")

        # Handle objects
        if isinstance(object, Var):
            o_vot = VarOrTerm(varorterm=object)
        elif isinstance(object, (iri, BlankNode)):
            o_vot = VarOrTerm(varorterm=GraphTerm(content=object))
        else:
            raise ValueError("o must be a Var, iri or BlankNode")

        return cls(
            content=(
                s_vot,
                PropertyListPathNotEmpty(
                    first_pair=(
                        verb,
                        ObjectListPath(
                            object_paths=[
                                ObjectPath(
                                    graph_node_path=GraphNodePath(
                                        varorterm_or_triplesnodepath=o_vot
                                    )
                                )
                            ]
                        ),
                    )
                ),
            )
        )


class PropertyListPath(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPropertyListPath
    PropertyListPath	  ::=  	PropertyListPathNotEmpty?
    """

    plpne: Optional[PropertyListPathNotEmpty] = None

    def render(self):
        if self.plpne:
            yield from self.plpne.render()


class PropertyListPathNotEmpty(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPropertyListPathNotEmpty
    PropertyListPathNotEmpty	  ::=  	( VerbPath | VerbSimple ) ObjectListPath ( ';' ( ( VerbPath | VerbSimple ) ObjectList )? )*
    """

    first_pair: Tuple[VerbPath | VerbSimple, ObjectListPath]
    other_pairs: Optional[List[Tuple[VerbPath | VerbSimple, ObjectList]]] = None

    def render(self):
        yield from self.first_pair[0].render()
        yield " "
        yield from self.first_pair[1].render()
        if self.other_pairs:
            for pair in self.other_pairs:
                yield ";"
                yield from pair[0].render()
                yield " "
                yield from pair[1].render()

    def __hash__(self):
        return hash((self.first_pair, self.other_pairs))


class VerbPath(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rVerbPath
    VerbPath	  ::=  	Path
    """

    path: SG_Path

    def render(self) -> Generator[str, None, None]:
        yield from self.path.render()

    def __hash__(self):
        return hash(self.path)


class VerbSimple(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rVerbSimple
    VerbSimple	  ::=  	Var
    """

    var: Var

    def render(self) -> Generator[str, None, None]:
        yield from self.var.render()

    def __hash__(self):
        return hash(self.var)


class ObjectListPath(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rObjectListPath
    ObjectListPath	  ::=  	ObjectPath ( ',' ObjectPath )*
    """

    object_paths: List[ObjectPath]

    def render(self):
        op_iter = iter(self.object_paths)
        first = next(op_iter)
        yield from first.render()
        for op in op_iter:
            yield ","
            yield from op.render()

    def __hash__(self):
        return hash(tuple(self.object_paths))


class ObjectPath(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rObjectPath
    ObjectPath	  ::=  	GraphNodePath
    """

    graph_node_path: GraphNodePath

    def render(self) -> Generator[str, None, None]:
        yield from self.graph_node_path.render()

    def __hash__(self):
        return hash(self.graph_node_path)


class SG_Path(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPath
    Path	  ::=  	PathAlternative
    """

    path_alternative: PathAlternative

    def render(self) -> Generator[str, None, None]:
        yield from self.path_alternative.render()

    def __hash__(self):
        return hash(self.path_alternative)


class PathAlternative(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathAlternative
    PathAlternative	  ::=  	PathSequence ( '|' PathSequence )*
    """

    sequence_paths: List[PathSequence]

    @field_validator("sequence_paths")
    def must_contain_at_least_one_item(cls, v):
        if len(v) == 0:
            raise ValueError("sequence_paths must contain at least one item.")
        return v

    def render(self):
        sp_iter = iter(self.sequence_paths)
        first = next(sp_iter)

        yield from first.render()
        for sp in sp_iter:
            yield "|"
            yield from sp.render()

    def __hash__(self):
        return hash(tuple(self.sequence_paths))


class PathSequence(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathSequence
    PathSequence	  ::=  	PathEltOrInverse ( '/' PathEltOrInverse )*
    """

    list_path_elt_or_inverse: List[PathEltOrInverse]

    @field_validator("list_path_elt_or_inverse")
    def must_contain_at_least_one_item(cls, v):
        if len(v) == 0:
            raise ValueError("list_path_elt_or_inverse must contain at least one item.")
        return v

    def render(self):
        path_iter = iter(self.list_path_elt_or_inverse)
        first = next(path_iter)

        yield from first.render()
        for path in path_iter:
            yield "/"
            yield from path.render()

    def __hash__(self):
        return hash(tuple(self.list_path_elt_or_inverse))


class PathElt(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathElt
    PathElt	  ::=  	PathPrimary PathMod?
    """

    path_primary: PathPrimary
    path_mod: Optional[PathMod] = None

    def render(self):
        yield from self.path_primary.render()
        if self.path_mod:
            yield from self.path_mod.render()

    def __hash__(self):
        return hash((self.path_primary, self.path_mod))


class PathEltOrInverse(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathEltOrInverse
    PathEltOrInverse	  ::=  	PathElt | '^' PathElt
    """

    path_elt: PathElt
    inverse: bool = False

    def render(self):
        if self.inverse:
            yield "^"
        yield from self.path_elt.render()

    def __hash__(self):
        return hash((self.path_elt, self.inverse))


class PathMod(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathMod
    PathMod	  ::=  	'?' | '*' | '+'
    """

    pathmod: str

    def render(self):
        yield self.pathmod

    @field_validator("pathmod")
    def validate_function_name(cls, v):
        # TODO there's pydantic enumeration type that can be used on the type
        if v not in ["?", "*", "+"]:
            raise ValueError("PathMod must be one of '?', '*', '+'")
        return v

    def __hash__(self):
        return hash(self.pathmod)


class PathPrimary(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathPrimary
    PathPrimary	  ::=  	iri | 'a' | '!' PathNegatedPropertySet | '(' Path ')'
    """

    value: iri | VerbRDFType | PathNegatedPropertySet | SG_Path

    def render(self):
        if isinstance(self.value, VerbRDFType):
            yield self.value
        elif isinstance(self.value, iri):
            yield from self.value.render()
        elif isinstance(self.value, PathNegatedPropertySet):
            yield "!"
            yield from self.value.render()
        elif isinstance(self.value, SG_Path):
            yield "("
            yield from self.value.render()
            yield ")"

    def __hash__(self):
        return hash(self.value)


class PathNegatedPropertySet(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathNegatedPropertySet
    PathNegatedPropertySet	  ::=  	PathOneInPropertySet | '(' ( PathOneInPropertySet ( '|' PathOneInPropertySet )* )? ')'
    """

    first_path: PathOneInPropertySet
    other_paths: Optional[List[PathOneInPropertySet]]  # negated paths?

    def render(self):
        yield from self.first_path.render()

        if self.other_paths:
            other_paths_iter = iter(self.other_paths)
            first_other_path = next(other_paths_iter)

            yield "("
            yield from first_other_path.render()

            for path in other_paths_iter:
                yield "|"
                yield from path.render()

            yield ")"

    def __hash__(self):
        return hash((self.first_path, self.other_paths))


class PathOneInPropertySet(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPathOneInPropertySet
    PathOneInPropertySet	  ::=  	iri | 'a' | '^' ( iri | 'a' )
    """

    path: iri | VerbRDFType
    negated: bool = False

    def render(self):
        if self.negated:
            yield "^"
        if isinstance(self.path, iri):
            yield from self.path.render()
        elif isinstance(self.path, VerbRDFType):
            yield self.path.value

    def __hash__(self):
        return hash((self.path, self.negated))


class Integer(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rInteger
    Integer	  ::=  	INTEGER
    """

    integer: INTEGER

    def render(self):
        yield from self.integer.render()


class TriplesNode(SPARQLGrammarBase):
    coll_or_bnpl: SG_Collection | BlankNodePropertyList

    def render(self):
        yield from self.coll_or_bnpl.render()


class BlankNodePropertyList(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rBlankNodePropertyList
    BlankNodePropertyList	  ::=  	'[' PropertyListNotEmpty ']'
    """

    plne: PropertyListNotEmpty

    def render(self):
        yield "["
        yield from self.plne.render()
        yield "]"


class TriplesNodePath(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rTriplesNodePath
    TriplesNodePath	  ::=  	CollectionPath | BlankNodePropertyListPath
    """

    coll_path_or_bnpl_path: CollectionPath | BlankNodePropertyListPath

    def render(self):
        yield from self.coll_path_or_bnpl_path.render()

    def __hash__(self):
        return hash(self.coll_path_or_bnpl_path)


class BlankNodePropertyListPath(SPARQLGrammarBase):
    plpne: PropertyListPathNotEmpty

    def render(self):
        yield "["
        yield from self.plpne.render()
        yield "]"

    def __hash__(self):
        return hash(self.plpne)


class SG_Collection(SPARQLGrammarBase):
    graphnode_list: List[GraphNode]

    def render(self):
        yield "("
        for node in self.graphnode_list:
            yield from node.render()
        yield ")"


class CollectionPath(SPARQLGrammarBase):
    graphnodepath_list: List[GraphNodePath]

    def render(self):
        yield "("
        for node in self.graphnodepath_list:
            yield from node.render()
        yield ")"

    def __hash__(self):
        return hash(tuple(self.graphnodepath_list))


class GraphNode(SPARQLGrammarBase):
    varorterm_or_triplesnode: VarOrTerm | TriplesNode

    def render(self):
        yield from self.varorterm_or_triplesnode.render()


class GraphNodePath(SPARQLGrammarBase):
    varorterm_or_triplesnodepath: VarOrTerm | TriplesNodePath

    def render(self):
        yield from self.varorterm_or_triplesnodepath.render()

    def __hash__(self):
        return hash(self.varorterm_or_triplesnodepath)


class VarOrTerm(SPARQLGrammarBase):
    varorterm: Var | GraphTerm

    def render(self):
        yield from self.varorterm.render()

    def __hash__(self):
        return hash(self.varorterm)


class VarOrIri(SPARQLGrammarBase):
    varoriri: Var | iri

    def render(self):
        yield from self.varoriri.render()


class Var(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rVar
    Var	  ::=  	VAR1 | VAR2
    """

    value: VAR1 | VAR2

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    @classmethod
    def from_string(cls, string):
        try:
            return cls(value=VAR1(value=string))
        except ValidationError:
            raise

    def __hash__(self):
        return hash(self.value)


class GraphTerm(SPARQLGrammarBase):
    """
    Represents a SPARQL GraphTerm.
    GraphTerm ::= iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | NIL
    """

    content: iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode | NIL

    def render(self) -> Generator[str, None, None]:
        yield from self.content.render()

    def __hash__(self):
        return hash(self.content)


class Expression(SPARQLGrammarBase):
    """
    Expression	  ::=  	ConditionalOrExpression
    """

    conditional_or_expression: ConditionalOrExpression

    def render(self) -> Generator[str, None, None]:
        yield from self.conditional_or_expression.render()

    @classmethod
    def from_primary_expression(
        cls, primary_expression: PrimaryExpression
    ) -> Expression:
        """
        Convenience method to create an Expression directly from a Var, wrapped in a PrimaryExpression.
        """
        return cls(
            conditional_or_expression=ConditionalOrExpression(
                conditional_and_expressions=[
                    ConditionalAndExpression(
                        value_logicals=[
                            ValueLogical(
                                relational_expression=RelationalExpression(
                                    left=NumericExpression(
                                        additive_expression=AdditiveExpression(
                                            base_expression=MultiplicativeExpression(
                                                base_expression=UnaryExpression(
                                                    primary_expression=primary_expression
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        ]
                    )
                ]
            )
        )

    @classmethod
    def create_in_expression(
        cls,
        left_primary_expression: PrimaryExpression,
        operator: str,  # "IN" or "NOT IN"
        right_primary_expressions: List[PrimaryExpression],
    ) -> Expression:
        """ """
        return cls(
            conditional_or_expression=ConditionalOrExpression(
                conditional_and_expressions=[
                    ConditionalAndExpression(
                        value_logicals=[
                            ValueLogical(
                                relational_expression=RelationalExpression(
                                    left=NumericExpression(
                                        additive_expression=AdditiveExpression(
                                            base_expression=MultiplicativeExpression(
                                                base_expression=UnaryExpression(
                                                    primary_expression=left_primary_expression
                                                )
                                            )
                                        )
                                    ),
                                    operator=operator,
                                    right=ExpressionList(
                                        expressions=[
                                            Expression.from_primary_expression(expr)
                                            for expr in right_primary_expressions
                                        ]
                                    ),
                                )
                            )
                        ]
                    )
                ]
            )
        )


class ConditionalOrExpression(SPARQLGrammarBase):
    """
    ConditionalOrExpression	  ::=  	ConditionalAndExpression ( '||' ConditionalAndExpression )*
    """

    conditional_and_expressions: List[ConditionalAndExpression]

    def render(self) -> Generator[str, None, None]:
        for i, conditional_and_expression in enumerate(
            self.conditional_and_expressions
        ):
            yield from conditional_and_expression.render()
            if i < len(self.conditional_and_expressions) - 1:
                yield " || "


class ConditionalAndExpression(SPARQLGrammarBase):
    """
    ConditionalAndExpression	  ::=  	ValueLogical ( '&&' ValueLogical )*
    """

    value_logicals: List[ValueLogical]

    def render(self) -> Generator[str, None, None]:
        for i, value_logical in enumerate(self.value_logicals):
            yield from value_logical.render()
            if i < len(self.value_logicals) - 1:
                yield " && "


class ValueLogical(SPARQLGrammarBase):
    relational_expression: RelationalExpression

    def render(self) -> Generator[str, None, None]:
        yield from self.relational_expression.render()


class RelationalExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rRelationalExpression
    RelationalExpression	  ::=  	NumericExpression ( '=' NumericExpression | '!=' NumericExpression | '<' NumericExpression | '>' NumericExpression | '<=' NumericExpression | '>=' NumericExpression | 'IN' ExpressionList | 'NOT' 'IN' ExpressionList )?
    """

    left: NumericExpression
    operator: Optional[str] = None  # '=', '!=', '<', '>', '<=', '>=', 'IN' and 'NOT IN'
    right: Optional[NumericExpression | ExpressionList] = None

    def render(self) -> Generator[str, None, None]:
        yield from self.left.render()
        if self.operator:
            yield f" {self.operator} "
            if self.right:
                yield from self.right.render()


class NumericExpression(SPARQLGrammarBase):
    additive_expression: AdditiveExpression

    def render(self) -> Generator[str, None, None]:
        yield from self.additive_expression.render()


class MultiplyDivideOperators(Enum):
    MULTIPLY = "*"
    DIVIDE = "/"


class AdditiveExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rAdditiveExpression
    AdditiveExpression	  ::=  	MultiplicativeExpression (
        '+' MultiplicativeExpression | '-' MultiplicativeExpression | (
            NumericLiteralPositive | NumericLiteralNegative
            )
            (
                ( '*' UnaryExpression ) | ( '/' UnaryExpression )
            )*
        )*
    """

    base_expression: MultiplicativeExpression
    additional_expressions: Optional[
        List[
            Tuple[MultiplacativeOperator, MultiplicativeExpression]
            | NumericLiteralPositive
            | NumericLiteralNegative,
            Optional[List[Tuple[MultiplyDivideOperators, UnaryExpression]]],
        ]
    ] = []

    def render(self) -> Generator[str, None, None]:
        yield from self.base_expression.render()
        for operator, expression in self.additional_expressions:
            if isinstance(operator, (NumericLiteralPositive, NumericLiteralNegative)):
                yield from operator.render()
            else:
                yield f" {operator} "
                yield from expression[
                    0
                ].render()  # MultiplicativeExpression or UnaryExpression
                if expression[1]:  # If there's an additional list of UnaryExpressions
                    for unary_operator, unary_expression in expression[1]:
                        yield f" {unary_operator} "
                        yield from unary_expression.render()


class MultiplacativeOperator(Enum):
    MULTIPLY = "*"
    DIVIDE = "/"


class MultiplicativeExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rMultiplicativeExpression
    MultiplicativeExpression	  ::=  	UnaryExpression ( '*' UnaryExpression | '/' UnaryExpression )*
    """

    base_expression: UnaryExpression
    additional_expressions: Optional[
        List[Tuple[MultiplacativeOperator, UnaryExpression]]
    ] = []

    def render(self) -> Generator[str, None, None]:
        yield from self.base_expression.render()
        for operator, expression in self.additional_expressions:
            yield f" {operator.value} "
            yield from expression.render()


class UnaryOperator(Enum):
    NOT = "!"
    PLUS = "+"
    MINUS = "-"


class UnaryExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rUnaryExpression
    UnaryExpression	  ::=  	  '!' PrimaryExpression
                            | '+' PrimaryExpression
                            | '-' PrimaryExpression
                            | PrimaryExpression
    """

    operator: Optional[UnaryOperator] = None
    primary_expression: PrimaryExpression

    def render(self) -> Generator[str, None, None]:
        if self.operator:
            yield self.operator.value
            yield " "
        yield from self.primary_expression.render()


class PrimaryExpression(SPARQLGrammarBase):
    """
    PrimaryExpression	  ::=  	BrackettedExpression | BuiltInCall | iriOrFunction | RDFLiteral | NumericLiteral | BooleanLiteral | Var
    """

    content: (
        BrackettedExpression
        | BuiltInCall
        | iriOrFunction
        | RDFLiteral
        | NumericLiteral
        | BooleanLiteral
        | Var
    )

    def render(self) -> Generator[str, None, None]:
        yield from self.content.render()


class BrackettedExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rBrackettedExpression
    BrackettedExpression	  ::=  	'(' Expression ')'
    """

    expression: Expression

    def render(self) -> Generator[str, None, None]:
        yield "("
        yield from self.expression.render()
        yield ")"


class BuiltInCallOptions(Enum):
    STR = "STR"
    LANG = "LANG"
    LANGMATCHES = "LANGMATCHES"
    DATATYPE = "DATATYPE"
    BOUND = "BOUND"
    IRI = "IRI"
    URI = "URI"
    BNODE = "BNODE"
    RAND = "RAND"
    ABS = "ABS"
    CEIL = "CEIL"
    FLOOR = "FLOOR"
    ROUND = "ROUND"
    CONCAT = "CONCAT"
    STRLEN = "STRLEN"
    UCASE = "UCASE"
    LCASE = "LCASE"
    ENCODE_FOR_URI = "ENCODE_FOR_URI"
    CONTAINS = "CONTAINS"
    STRSTARTS = "STRSTARTS"
    STRENDS = "STRENDS"
    STRBEFORE = "STRBEFORE"
    STRAFTER = "STRAFTER"
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    HOURS = "HOURS"
    MINUTES = "MINUTES"
    SECONDS = "SECONDS"
    TIMEZONE = "TIMEZONE"
    TZ = "TZ"
    NOW = "NOW"
    UUID = "UUID"
    STRUUID = "STRUUID"
    MD5 = "MD5"
    SHA1 = "SHA1"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"
    COALESCE = "COALESCE"
    IF = "IF"
    STRLANG = "STRLANG"
    STRDT = "STRDT"
    SAMETERM = "sameTerm"
    ISIRI = "isIRI"
    ISURI = "isURI"
    ISBLANK = "isBLANK"
    ISLITERAL = "isLITERAL"
    ISNUMERIC = "isNUMERIC"


class BuiltInCall(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rBuiltInCall
    """

    function: (
        BuiltInCallOptions  # most functions under this enum
        | Aggregate
        | SubstringExpression
        | StrReplaceExpression
        | RegexExpression
        | ExistsFunc
        | NotExistsFunc
        | NotExistsFunc
    )
    arguments: Optional[
        Expression
        | Tuple[Expression, Expression]
        | Tuple[Expression, Expression, Expression]
        | ExpressionList
        | Var
        | NIL
        ] = None

    # TODO validate the args are appropriate for function

    def render(self) -> Generator[str, None, None]:
        if isinstance(self.function, BuiltInCallOptions):
            yield self.function.value
        else:
            yield from self.function.render()
        if self.arguments:
            for i, arg in enumerate(self.arguments):
                if isinstance(arg, (tuple, Expression)):
                    yield "("
                yield from arg.render()
                if i < len(self.arguments) - 1:
                    yield ", "
                if isinstance(arg, (tuple, Expression)):
                    yield ")"

    @classmethod
    def create_with_one_expr(
        cls, function_name: str, expression: PrimaryExpression
    ) -> BuiltInCall:
        """
        Convenience method for functions that take a single PrimaryExpression as an argument.
        Uses create_with_expression_list for consistency in handling expressions.
        """
        return cls.create_with_n_expr(function_name, [expression])

    @classmethod
    def create_with_n_expr(
        cls, function_name: str, expressions: List[PrimaryExpression]
    ) -> BuiltInCall:
        """
        Convenience method for functions that take a list of PrimaryExpressions as arguments.
        Wraps each PrimaryExpression in an Expression.
        """
        wrapped_expressions = [
            Expression.from_primary_expression(pe) for pe in expressions
        ]

        # Create a BuiltInCall instance for the specified function with the list of wrapped expressions
        return cls(function_name=function_name, arguments=wrapped_expressions)


class RegexExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rRegexExpression
    RegexExpression	  ::=  	'REGEX' '(' Expression ',' Expression ( ',' Expression )? ')'
    """

    text_expression: Expression
    pattern_expression: Expression
    flags_expression: Optional[Expression] = None

    def render(self) -> Generator[str, None, None]:
        yield "REGEX("
        yield from self.text_expression.render()
        yield ", "
        yield from self.pattern_expression.render()

        if self.flags_expression:
            yield ", "
            yield from self.flags_expression.render()

        yield ")"


class SubstringExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rSubstringExpression
    SubstringExpression	  ::=  	'SUBSTR' '(' Expression ',' Expression ( ',' Expression )? ')'
    """

    source: Expression
    starting_loc: Expression
    length: Optional[Expression] = None

    def render(self) -> Generator[str, None, None]:
        yield "SUBSTR("
        yield from self.source.render()
        yield ", "
        yield from self.starting_loc.render()
        if self.length:
            yield ", "
            yield from self.length.render()
        yield ")"


class StrReplaceExpression(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rStrReplaceExpression
    StrReplaceExpression	  ::=  	'REPLACE' '(' Expression ',' Expression ',' Expression ( ',' Expression )? ')'
    """

    arg: Expression
    pattern: Expression
    replacement: Expression
    flags: Optional[Expression] = None

    def render(self) -> Generator[str, None, None]:
        yield "REPLACE("
        yield from self.arg.render()
        yield ", "
        yield from self.pattern.render()
        yield ", "
        yield from self.replacement.render()
        if self.flags:
            yield ", "
            yield from self.flags.render()
        yield ")"


class ExistsFunc(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rExistsFunc
    ExistsFunc	  ::=  	'EXISTS' GroupGraphPattern
    """

    group_graph_pattern: GroupGraphPattern

    def render(self):
        yield "EXISTS"
        yield from self.group_graph_pattern.render()


class NotExistsFunc(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rNotExistsFunc
    NotExistsFunc	  ::=  	'NOT EXISTS' GroupGraphPattern
    """

    group_graph_pattern: GroupGraphPattern

    def render(self):
        yield "NOT EXISTS"
        yield from self.group_graph_pattern.render()


class AggregateOptions(Enum):
    COUNT = "COUNT"
    SUM = "SUM"
    MIN = "MIN"
    MAX = "MAX"
    AVG = "AVG"
    SAMPLE = "SAMPLE"
    GROUP_CONCAT = "GROUP_CONCAT"


class Aggregate(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rAggregate
    Aggregate	  ::=  	  'COUNT' '(' 'DISTINCT'? ( '*' | Expression ) ')'
    | 'SUM' '(' 'DISTINCT'? Expression ')'
    | 'MIN' '(' 'DISTINCT'? Expression ')'
    | 'MAX' '(' 'DISTINCT'? Expression ')'
    | 'AVG' '(' 'DISTINCT'? Expression ')'
    | 'SAMPLE' '(' 'DISTINCT'? Expression ')'
    | 'GROUP_CONCAT' '(' 'DISTINCT'? Expression ( ';' 'SEPARATOR' '=' String )? ')'
    """

    function_name: AggregateOptions
    distinct: Optional[bool] = None
    expression: Expression | Wildcard
    separator: Optional[str] = None  # Only used for GROUP_CONCAT

    @field_validator("expression")
    def validate_expression(cls, v):
        if isinstance(v, Wildcard) and cls.function_name != "COUNT":
            raise ValueError("'*' can only be used for COUNT")
        return v

    @field_validator("separator")
    def validate_separator(cls, v):
        if cls.function_name != "GROUP_CONCAT":
            raise ValueError("'SEPARATOR' can only be used for GROUP_CONCAT")
        return v

    def render(self) -> Generator[str, None, None]:
        yield f"{self.function_name}("
        if self.distinct:
            yield "DISTINCT "
        if isinstance(self.expression, Wildcard):
            yield self.expression.value
        else:
            yield from self.expression.render()
        # Handle the separator for GROUP_CONCAT
        if self.separator:
            yield f" ; SEPARATOR='{self.separator}'"
        yield ")"


class iriOrFunction(SPARQLGrammarBase):
    """
    iriOrFunction	  ::=  	iri ArgList?
    """

    iri: iri
    arg_list: Optional[ArgList] = None

    def render(self) -> Generator[str, None, None]:
        yield from self.iri.render()
        if self.arg_list:
            yield from self.arg_list.render()


class RDFLiteral(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rRDFLiteral
    RDFLiteral	  ::=  	String ( LANGTAG | ( '^^' iri ) )?
    """

    value: String
    langtag: Optional[LANGTAG] = None
    datatype: Optional[iri] = None

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()
        if self.langtag:
            yield from self.langtag.render()
        elif self.datatype:
            yield "^^"
            yield from self.datatype.render()

    @classmethod
    def from_string(cls, string):
        try:
            return cls(
                value=String(
                    value=STRING_LITERAL2(
                        value=string
                    )
                )
            )
        except ValidationError:
            raise

    def __hash__(self):
        return hash(self.value)


class NumericLiteral(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rNumericLiteral
    NumericLiteral	  ::=  	NumericLiteralUnsigned | NumericLiteralPositive | NumericLiteralNegative
    """

    value: NumericLiteralUnsigned | NumericLiteralPositive | NumericLiteralNegative

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    def __hash__(self):
        return hash(self.value)


class NumericLiteralUnsigned(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rNumericLiteralUnsigned
    NumericLiteralUnsigned	  ::=  	INTEGER | DECIMAL | DOUBLE
    """

    value: INTEGER | DECIMAL | DOUBLE

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    def __hash__(self):
        return hash(self.value)


class NumericLiteralPositive(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rNumericLiteralPositive
    NumericLiteralPositive	  ::=  	INTEGER_POSITIVE | DECIMAL_POSITIVE | DOUBLE_POSITIVE
    """

    value: INTEGER_POSITIVE | DECIMAL_POSITIVE | DOUBLE_POSITIVE

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    def __hash__(self):
        return hash(self.value)


class NumericLiteralNegative(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rNumericLiteralNegative
    NumericLiteralNegative	  ::=  	INTEGER_NEGATIVE | DECIMAL_NEGATIVE | DOUBLE_NEGATIVE
    """

    value: INTEGER_NEGATIVE | DECIMAL_NEGATIVE | DOUBLE_NEGATIVE

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    def __hash__(self):
        return hash(self.value)


class BoolOptions(Enum):
    TRUE = "true"
    FALSE = "false"


class BooleanLiteral(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rBooleanLiteral
    BooleanLiteral	  ::=  	'true' | 'false'
    """

    value: BoolOptions

    def render(self) -> Generator[str, None, None]:
        yield from self.value.value


class String(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rString
    String	  ::=  	STRING_LITERAL1 | STRING_LITERAL2 | STRING_LITERAL_LONG1 | STRING_LITERAL_LONG2
    """

    value: (
            STRING_LITERAL1 | STRING_LITERAL2 | STRING_LITERAL_LONG1 | STRING_LITERAL_LONG2
    )

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()


class iri(SPARQLGrammarBase):
    """
    Represents a SPARQL iri.
    iri ::= IRIREF | PrefixedName
    """

    value: IRIREF | PrefixedName

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    @classmethod
    def from_string(cls, string):
        try:
            return cls(value=IRIREF(value=string))
        except ValidationError as ve1:
            try:
                return cls(value=PrefixedName(value=string))
            except ValidationError as ve2:
                raise ValueError(
                    f"Invalid IRI: {string}. Failed validations: {ve1, ve2}"
                )

    def __hash__(self):
        return hash(self.value)


class PrefixedName(SPARQLGrammarBase):
    """
    https://www.w3.org/TR/sparql11-query/#rPrefixedName
    PrefixedName	  ::=  	PNAME_LN | PNAME_NS
    """

    value: PNAME_LN | PNAME_NS

    def render(self) -> Generator[str, None, None]:
        yield from self.value.render()

    def __hash__(self):
        return hash(self.value)


class BlankNode(SPARQLGrammarBase):
    """
    BlankNode	  ::=  	BLANK_NODE_LABEL | ANON
    """

    value: BlankNodeLabel | Anon

    def render(self):
        yield from self.value.render()
        yield " "

    def __hash__(self):
        return hash(self.value)


