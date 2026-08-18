"""Pretty-print a grammar tree as indented, readable SPARQL.

``to_string()`` produces canonical output: correct, compact, and cheap, because it
appends into a single buffer with no layout decisions. That is what you want when the
query is going straight to an endpoint.

``format_sparql()`` is the other mode - for queries a person is going to read, in
logs, docs, tests or a terminal. It walks the tree structurally rather than
post-processing text, so nesting depth is always known and indentation is always
consistent:

    >>> from sparql_grammar import format_sparql, iri, select, optional
    >>> print(format_sparql(select("?s", where=[
    ...     ("?s", "a", iri("http://ex/C")),
    ...     optional(("?s", iri("http://ex/p"), "?o")),
    ... ])))
    SELECT ?s
    WHERE {
      ?s a <http://ex/C>
      OPTIONAL {
        ?s <http://ex/p> ?o
      }
    }

Layout is applied to the productions that introduce a block or a clause; everything
else is rendered inline by its own ``to_string()``. Anything this module does not know
about therefore still formats correctly, just without internal line breaks.
"""

from __future__ import annotations

from ._base import Node

__all__ = ["format_sparql"]


def format_sparql(node: Node, indent: str = "  ", width: int = 0) -> str:
    """Render ``node`` as indented SPARQL.

    ``indent`` is the string used per nesting level. ``width``, when non-zero, is the
    column past which a triple's object list is broken onto its own lines.
    """
    lines: list[str] = []
    _Formatter(indent, width).write(node, 0, lines)
    return "\n".join(lines)


class _Formatter:
    """Emits one list entry per output line."""

    def __init__(self, indent: str, width: int) -> None:
        self.indent = indent
        self.width = width

    # -- helpers -----------------------------------------------------------

    def _emit(self, depth: int, text: str, out: list[str]) -> None:
        if text:
            out.append(f"{self.indent * depth}{text}")

    def _inline(self, node: object) -> str:
        """Render a node as-is, on one line where it has no internal blocks.

        Deliberately does NOT normalise whitespace: a long string literal may
        legitimately contain newlines, and collapsing them would rewrite the
        literal's value. Constructs that introduce their own line breaks are laid
        out by the handlers below instead, so the text that reaches here is already
        single-line in practice.
        """
        if node is None:
            return ""
        return node.to_string() if isinstance(node, Node) else str(node)

    def write(self, node: object, depth: int, out: list[str]) -> None:
        handler = _HANDLERS.get(type(node).__name__)
        if handler is None:
            self._emit(depth, self._inline(node), out)
        else:
            handler(self, node, depth, out)

    # -- top level ---------------------------------------------------------

    def query_unit(self, node, depth, out) -> None:
        self.write(node.query, depth, out)

    def update_unit(self, node, depth, out) -> None:
        self.write(node.update, depth, out)

    def query(self, node, depth, out) -> None:
        self.prologue(node.prologue, depth, out)
        self.write(node.query, depth, out)
        if node.values_clause is not None and node.values_clause.data_block is not None:
            self._emit(depth, f"VALUES {self._inline(node.values_clause.data_block)}", out)

    def prologue(self, node, depth, out) -> None:
        for decl in node.decls:
            self._emit(depth, self._inline(decl), out)

    def update(self, node, depth, out) -> None:
        self.prologue(node.prologue, depth, out)
        for i, operation in enumerate(node.operations):
            if i:
                out[-1] = f"{out[-1]} ;"
            self.write(operation, depth, out)

    # -- query forms -------------------------------------------------------

    def select_query(self, node, depth, out) -> None:
        self._emit(depth, self._inline(node.select_clause), out)
        self._datasets(node.dataset_clauses, depth, out)
        self.where_clause(node.where_clause, depth, out)
        self.solution_modifier(node.solution_modifier, depth, out)

    def sub_select(self, node, depth, out) -> None:
        self._emit(depth, self._inline(node.select_clause), out)
        self.where_clause(node.where_clause, depth, out)
        self.solution_modifier(node.solution_modifier, depth, out)
        if node.values_clause is not None and node.values_clause.data_block is not None:
            self._emit(depth, f"VALUES {self._inline(node.values_clause.data_block)}", out)

    def construct_query(self, node, depth, out) -> None:
        if node.construct_template is not None:
            self._emit(depth, "CONSTRUCT {", out)
            self._triples_of(node.construct_template.construct_triples, depth + 1, out)
            self._emit(depth, "}", out)
            self._datasets(node.dataset_clauses, depth, out)
            self.where_clause(node.where_clause, depth, out)
        else:
            self._emit(depth, "CONSTRUCT", out)
            self._datasets(node.dataset_clauses, depth, out)
            self._emit(depth, "WHERE {", out)
            if node.where_template is not None:
                self._triples_of(node.where_template.construct_triples, depth + 1, out)
            self._emit(depth, "}", out)
        self.solution_modifier(node.solution_modifier, depth, out)

    def describe_query(self, node, depth, out) -> None:
        targets = " ".join(self._inline(v) for v in node.variables) or "*"
        self._emit(depth, f"DESCRIBE {targets}", out)
        self._datasets(node.dataset_clauses, depth, out)
        if node.where_clause is not None:
            self.where_clause(node.where_clause, depth, out)
        self.solution_modifier(node.solution_modifier, depth, out)

    def ask_query(self, node, depth, out) -> None:
        self._emit(depth, "ASK", out)
        self._datasets(node.dataset_clauses, depth, out)
        self.where_clause(node.where_clause, depth, out)
        self.solution_modifier(node.solution_modifier, depth, out)

    def _datasets(self, clauses, depth, out) -> None:
        for clause in clauses or ():
            self._emit(depth, self._inline(clause), out)

    def where_clause(self, node, depth, out) -> None:
        if node is None:
            return
        self._block("WHERE {", node.group_graph_pattern.content, depth, out)

    def solution_modifier(self, node, depth, out) -> None:
        if node is None:
            return
        for part in (node.group_by, node.having, node.order_by, node.limit_offset):
            if part is not None:
                self._emit(depth, self._inline(part), out)

    # -- graph patterns ----------------------------------------------------

    def _block(self, opening: str, content: object, depth: int, out: list[str]) -> None:
        """Emit ``opening`` then ``content`` indented then a closing brace."""
        self._emit(depth, opening, out)
        self.write(content, depth + 1, out)
        self._emit(depth, "}", out)

    def group_graph_pattern(self, node, depth, out) -> None:
        self._block("{", node.content, depth, out)

    def group_graph_pattern_sub(self, node, depth, out) -> None:
        for pattern in node.patterns:
            self.write(pattern, depth, out)

    def triples_block(self, node, depth, out) -> None:
        last = len(node.triples) - 1
        for i, triple in enumerate(node.triples):
            self._triple(triple, depth, out, terminator="" if i == last else " .")

    def _triples_of(self, block, depth, out) -> None:
        if block is None:
            return
        last = len(block.triples) - 1
        for i, triple in enumerate(block.triples):
            self._triple(triple, depth, out, terminator="" if i == last else " .")

    def _triple(self, triple, depth, out, terminator: str = "") -> None:
        text = self._inline(triple)
        if self.width and len(text) + len(self.indent) * depth > self.width:
            broken = self._break_triple(triple, depth, out)
            if broken:
                if terminator:
                    out[-1] = f"{out[-1]}{terminator}"
                return
        self._emit(depth, f"{text}{terminator}", out)

    def _break_triple(self, triple, depth, out) -> bool:
        """Put each predicate-object pair of a long triple on its own line."""
        property_list = getattr(triple, "property_list_path", None) or getattr(
            triple, "property_list", None
        )
        if property_list is None or len(getattr(property_list, "pairs", ())) < 2:
            return False
        self._emit(depth, self._inline(triple.subject), out)
        last = len(property_list.pairs) - 1
        for i, (verb, objects) in enumerate(property_list.pairs):
            verb_text = "a" if verb == "a" else self._inline(verb)
            suffix = "" if i == last else " ;"
            self._emit(depth + 1, f"{verb_text} {self._inline(objects)}{suffix}", out)
        return True

    def optional_graph_pattern(self, node, depth, out) -> None:
        self._block("OPTIONAL {", node.group_graph_pattern.content, depth, out)

    def minus_graph_pattern(self, node, depth, out) -> None:
        self._block("MINUS {", node.group_graph_pattern.content, depth, out)

    def graph_graph_pattern(self, node, depth, out) -> None:
        self._block(
            f"GRAPH {self._inline(node.varoriri)} {{",
            node.group_graph_pattern.content,
            depth,
            out,
        )

    def service_graph_pattern(self, node, depth, out) -> None:
        silent = "SILENT " if node.silent else ""
        self._block(
            f"SERVICE {silent}{self._inline(node.varoriri)} {{",
            node.group_graph_pattern.content,
            depth,
            out,
        )

    def group_or_union_graph_pattern(self, node, depth, out) -> None:
        for i, pattern in enumerate(node.group_graph_patterns):
            if i:
                self._emit(depth, "UNION", out)
            self.write(pattern, depth, out)

    def filter_(self, node, depth, out) -> None:
        constraint = node.constraint
        inner = getattr(constraint, "group_graph_pattern", None)
        if inner is not None:  # FILTER EXISTS / NOT EXISTS
            keyword = "NOT EXISTS" if type(constraint).__name__ == "NotExistsFunc" else "EXISTS"
            self._block(f"FILTER {keyword} {{", inner.content, depth, out)
            return
        self._emit(depth, self._inline(node), out)

    # -- update ------------------------------------------------------------

    def modify(self, node, depth, out) -> None:
        if node.with_iri is not None:
            self._emit(depth, f"WITH {self._inline(node.with_iri)}", out)
        for clause, keyword in (
            (node.delete_clause, "DELETE"),
            (node.insert_clause, "INSERT"),
        ):
            if clause is not None:
                self._block(f"{keyword} {{", clause.quad_pattern.quads, depth, out)
        for using in node.using_clauses:
            self._emit(depth, self._inline(using), out)
        self._block("WHERE {", node.where.content, depth, out)

    def _data_operation(self, keyword: str, quads, depth, out) -> None:
        self._block(f"{keyword} {{", quads, depth, out)

    def insert_data(self, node, depth, out) -> None:
        self._data_operation("INSERT DATA", node.quad_data.quads, depth, out)

    def delete_data(self, node, depth, out) -> None:
        self._data_operation("DELETE DATA", node.quad_data.quads, depth, out)

    def delete_where(self, node, depth, out) -> None:
        self._data_operation("DELETE WHERE", node.quad_pattern.quads, depth, out)

    def quads(self, node, depth, out) -> None:
        for part in node.parts:
            self.write(part, depth, out)

    def quads_not_triples(self, node, depth, out) -> None:
        self._emit(depth, f"GRAPH {self._inline(node.varoriri)} {{", out)
        if node.triples_template is not None:
            self._triples_of(node.triples_template, depth + 1, out)
        self._emit(depth, "}", out)

    def triples_template(self, node, depth, out) -> None:
        self._triples_of(node, depth, out)

    def construct_triples(self, node, depth, out) -> None:
        self._triples_of(node, depth, out)


_HANDLERS = {
    "QueryUnit": _Formatter.query_unit,
    "UpdateUnit": _Formatter.update_unit,
    "Query": _Formatter.query,
    "Update": _Formatter.update,
    "Prologue": _Formatter.prologue,
    "SelectQuery": _Formatter.select_query,
    "SubSelect": _Formatter.sub_select,
    "ConstructQuery": _Formatter.construct_query,
    "DescribeQuery": _Formatter.describe_query,
    "AskQuery": _Formatter.ask_query,
    "WhereClause": _Formatter.where_clause,
    "SolutionModifier": _Formatter.solution_modifier,
    "GroupGraphPattern": _Formatter.group_graph_pattern,
    "GroupGraphPatternSub": _Formatter.group_graph_pattern_sub,
    "TriplesBlock": _Formatter.triples_block,
    "ConstructTriples": _Formatter.construct_triples,
    "TriplesTemplate": _Formatter.triples_template,
    "OptionalGraphPattern": _Formatter.optional_graph_pattern,
    "MinusGraphPattern": _Formatter.minus_graph_pattern,
    "GraphGraphPattern": _Formatter.graph_graph_pattern,
    "ServiceGraphPattern": _Formatter.service_graph_pattern,
    "GroupOrUnionGraphPattern": _Formatter.group_or_union_graph_pattern,
    "Filter": _Formatter.filter_,
    "Modify": _Formatter.modify,
    "InsertData": _Formatter.insert_data,
    "DeleteData": _Formatter.delete_data,
    "DeleteWhere": _Formatter.delete_where,
    "Quads": _Formatter.quads,
    "QuadsNotTriples": _Formatter.quads_not_triples,
}
