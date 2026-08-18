"""SPARQL Update productions: graph management and INSERT/DELETE.

None of this worked in the pydantic version - the classes existed but referenced
productions that were never defined, so a dozen of them could not even build a
schema, and no UPDATE request could be constructed.

As in ``grammar``, the recursive productions (``Quads``, ``Update``) are flat lists.
"""

from __future__ import annotations

from enum import Enum
from typing import Union

from ._base import Add, Node, alias, production
from .grammar import (
    GroupGraphPattern,
    Prologue,
    TriplesTemplate,
)

__all__ = [
    "UpdateUnit", "Update", "Update1", "Load", "Clear", "Drop", "Create", "Add_",
    "Move", "Copy", "InsertData", "DeleteData", "DeleteWhere", "Modify",
    "DeleteClause", "InsertClause", "UsingClause", "GraphOrDefault", "GraphRef",
    "GraphRefAll", "GraphRefTarget", "QuadPattern", "QuadData", "Quads",
    "QuadsNotTriples",
]


@production(rule="GraphRef")
class GraphRef(Node):
    """GraphRef ::= 'GRAPH' iri"""

    iri: object

    def render(self, add: Add) -> None:
        add("GRAPH ")
        self.iri.render(add)


class GraphRefTarget(str, Enum):
    """The keyword targets of ``GraphRefAll``."""

    DEFAULT = "DEFAULT"
    NAMED = "NAMED"
    ALL = "ALL"


@production(rule="GraphRefAll")
class GraphRefAll(Node):
    """GraphRefAll ::= GraphRef | 'DEFAULT' | 'NAMED' | 'ALL'"""

    target: object

    def render(self, add: Add) -> None:
        target = self.target
        if isinstance(target, GraphRefTarget):
            add(target.value)
        else:
            target.render(add)

    @classmethod
    def graph(cls, iri: object) -> GraphRefAll:
        return cls(GraphRef(iri))


@production(rule="GraphOrDefault")
class GraphOrDefault(Node):
    """GraphOrDefault ::= 'DEFAULT' | 'GRAPH'? iri

    ``iri`` unset means ``DEFAULT``. ``explicit_graph`` emits the optional
    ``GRAPH`` keyword.
    """

    iri: object = None
    explicit_graph: bool = False

    def render(self, add: Add) -> None:
        if self.iri is None:
            add("DEFAULT")
            return
        if self.explicit_graph:
            add("GRAPH ")
        self.iri.render(add)

    @classmethod
    def default(cls) -> GraphOrDefault:
        return cls()


@production(rule="QuadsNotTriples")
class QuadsNotTriples(Node):
    """QuadsNotTriples ::= 'GRAPH' VarOrIri '{' TriplesTemplate? '}'"""

    varoriri: object
    triples_template: TriplesTemplate | None = None

    def render(self, add: Add) -> None:
        add("GRAPH ")
        self.varoriri.render(add)
        add(" {\n")
        if self.triples_template is not None:
            self.triples_template.render(add)
            add("\n")
        add("}")


@production(rule="Quads")
class Quads(Node):
    """Quads ::= TriplesTemplate? ( QuadsNotTriples '.'? TriplesTemplate? )*

    Flattened to one ordered ``parts`` list of ``TriplesTemplate`` and
    ``QuadsNotTriples`` members.
    """

    parts: list = None

    def __post_init__(self) -> None:
        if self.parts is None:
            self.parts = []

    def render(self, add: Add) -> None:
        for i, part in enumerate(self.parts):
            if i:
                add("\n")
            part.render(add)

    @classmethod
    def from_tss_list(cls, triples: list) -> Quads:
        """Default-graph quads from a list of ``TriplesSameSubject``."""
        return cls([TriplesTemplate.from_tss_list(triples)])


@production(rule="QuadPattern")
class QuadPattern(Node):
    """QuadPattern ::= '{' Quads '}'"""

    quads: Quads

    def render(self, add: Add) -> None:
        add("{\n")
        self.quads.render(add)
        add("\n}")


@production(rule="QuadData")
class QuadData(Node):
    """QuadData ::= '{' Quads '}'

    Same shape as ``QuadPattern``, but the grammar requires ground triples here.
    """

    quads: Quads

    def render(self, add: Add) -> None:
        add("{\n")
        self.quads.render(add)
        add("\n}")


@production(rule="Load")
class Load(Node):
    """Load ::= 'LOAD' 'SILENT'? iri ( 'INTO' GraphRef )?"""

    iri: object
    into: GraphRef | None = None
    silent: bool = False

    def render(self, add: Add) -> None:
        add("LOAD ")
        if self.silent:
            add("SILENT ")
        self.iri.render(add)
        if self.into is not None:
            add(" INTO ")
            self.into.render(add)


@production(rule="Clear")
class Clear(Node):
    """Clear ::= 'CLEAR' 'SILENT'? GraphRefAll"""

    graph_ref_all: GraphRefAll
    silent: bool = False

    def render(self, add: Add) -> None:
        add("CLEAR ")
        if self.silent:
            add("SILENT ")
        self.graph_ref_all.render(add)


@production(rule="Drop")
class Drop(Node):
    """Drop ::= 'DROP' 'SILENT'? GraphRefAll"""

    graph_ref_all: GraphRefAll
    silent: bool = False

    def render(self, add: Add) -> None:
        add("DROP ")
        if self.silent:
            add("SILENT ")
        self.graph_ref_all.render(add)


@production(rule="Create")
class Create(Node):
    """Create ::= 'CREATE' 'SILENT'? GraphRef"""

    graph_ref: GraphRef
    silent: bool = False

    def render(self, add: Add) -> None:
        add("CREATE ")
        if self.silent:
            add("SILENT ")
        self.graph_ref.render(add)


class _GraphToGraph(Node):
    """Shared rendering for ADD / MOVE / COPY."""

    __slots__ = ()
    keyword: str = ""

    def render(self, add: Add) -> None:
        add(type(self).keyword)
        add(" ")
        if self.silent:
            add("SILENT ")
        self.source.render(add)
        add(" TO ")
        self.destination.render(add)


@production(rule="Add")
class Add_(_GraphToGraph):
    """Add ::= 'ADD' 'SILENT'? GraphOrDefault 'TO' GraphOrDefault

    Named ``Add_`` because ``Add`` is the render-callback type alias.
    """

    source: GraphOrDefault
    destination: GraphOrDefault
    silent: bool = False
    keyword = "ADD"


@production(rule="Move")
class Move(_GraphToGraph):
    """Move ::= 'MOVE' 'SILENT'? GraphOrDefault 'TO' GraphOrDefault"""

    source: GraphOrDefault
    destination: GraphOrDefault
    silent: bool = False
    keyword = "MOVE"


@production(rule="Copy")
class Copy(_GraphToGraph):
    """Copy ::= 'COPY' 'SILENT'? GraphOrDefault 'TO' GraphOrDefault"""

    source: GraphOrDefault
    destination: GraphOrDefault
    silent: bool = False
    keyword = "COPY"


@production(rule="InsertData")
class InsertData(Node):
    """InsertData ::= 'INSERT DATA' QuadData"""

    quad_data: QuadData

    def render(self, add: Add) -> None:
        add("INSERT DATA ")
        self.quad_data.render(add)

    @classmethod
    def from_tss_list(cls, triples: list) -> InsertData:
        return cls(QuadData(Quads.from_tss_list(triples)))


@production(rule="DeleteData")
class DeleteData(Node):
    """DeleteData ::= 'DELETE DATA' QuadData"""

    quad_data: QuadData

    def render(self, add: Add) -> None:
        add("DELETE DATA ")
        self.quad_data.render(add)

    @classmethod
    def from_tss_list(cls, triples: list) -> DeleteData:
        return cls(QuadData(Quads.from_tss_list(triples)))


@production(rule="DeleteWhere")
class DeleteWhere(Node):
    """DeleteWhere ::= 'DELETE WHERE' QuadPattern"""

    quad_pattern: QuadPattern

    def render(self, add: Add) -> None:
        add("DELETE WHERE ")
        self.quad_pattern.render(add)

    @classmethod
    def from_tss_list(cls, triples: list) -> DeleteWhere:
        return cls(QuadPattern(Quads.from_tss_list(triples)))


@production(rule="DeleteClause")
class DeleteClause(Node):
    """DeleteClause ::= 'DELETE' QuadPattern"""

    quad_pattern: QuadPattern

    def render(self, add: Add) -> None:
        add("DELETE ")
        self.quad_pattern.render(add)


@production(rule="InsertClause")
class InsertClause(Node):
    """InsertClause ::= 'INSERT' QuadPattern"""

    quad_pattern: QuadPattern

    def render(self, add: Add) -> None:
        add("INSERT ")
        self.quad_pattern.render(add)


@production(rule="UsingClause")
class UsingClause(Node):
    """UsingClause ::= 'USING' ( iri | 'NAMED' iri )"""

    iri: object
    named: bool = False

    def render(self, add: Add) -> None:
        add("USING ")
        if self.named:
            add("NAMED ")
        self.iri.render(add)


@production(rule="Modify")
class Modify(Node):
    """Modify ::= ( 'WITH' iri )? ( DeleteClause InsertClause? | InsertClause ) UsingClause* 'WHERE' GroupGraphPattern

    At least one of ``delete_clause``/``insert_clause`` is required; that is
    checked by ``validate()`` rather than at construction time.
    """

    where: GroupGraphPattern
    delete_clause: DeleteClause | None = None
    insert_clause: InsertClause | None = None
    with_iri: object = None
    using_clauses: list = None

    def __post_init__(self) -> None:
        if self.using_clauses is None:
            self.using_clauses = []

    def render(self, add: Add) -> None:
        if self.with_iri is not None:
            add("WITH ")
            self.with_iri.render(add)
            add("\n")
        if self.delete_clause is not None:
            self.delete_clause.render(add)
            add("\n")
        if self.insert_clause is not None:
            self.insert_clause.render(add)
            add("\n")
        for using in self.using_clauses:
            using.render(add)
            add("\n")
        add("WHERE ")
        self.where.render(add)

    def _check(self, level: str) -> list[str]:
        errors = super()._check(level)
        if self.delete_clause is None and self.insert_clause is None:
            errors.append("Modify: requires a DELETE clause, an INSERT clause, or both")
        return errors


#: Update1 ::= Load | Clear | Drop | Add | Move | Copy | Create | DeleteWhere | Modify | InsertData | DeleteData
Update1 = alias(
    "Update1",
    Union[
        Load,
        Clear,
        Drop,
        Add_,
        Move,
        Copy,
        Create,
        DeleteWhere,
        Modify,
        InsertData,
        DeleteData,
    ],
)


@production(rule="Update")
class Update(Node):
    """Update ::= Prologue ( Update1 ( ';' Update )? )?

    Flattened: ``operations`` is a list of ``Update1`` members joined with ``;``,
    rather than a chain of nested ``Update`` tails.
    """

    operations: list = None
    prologue: Prologue = None

    def __post_init__(self) -> None:
        if self.operations is None:
            self.operations = []
        if self.prologue is None:
            self.prologue = Prologue()

    def render(self, add: Add) -> None:
        self.prologue.render(add)
        for i, operation in enumerate(self.operations):
            if i:
                add(" ;\n")
            operation.render(add)


@production(rule="UpdateUnit")
class UpdateUnit(Node):
    """UpdateUnit ::= Update"""

    update: Update

    def render(self, add: Add) -> None:
        self.update.render(add)
