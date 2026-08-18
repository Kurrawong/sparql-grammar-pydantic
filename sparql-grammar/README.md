# sparql-grammar

Typed Python objects for the [SPARQL 1.2](https://www.w3.org/TR/sparql12-query/) grammar:
one class per production of the W3C grammar, each able to render itself back to SPARQL.
Build queries as data, manipulate them programmatically, and print them for a machine or
for a person.

No runtime dependencies. No pydantic.

**[Try it in your browser](https://kurrawong.github.io/sparql-grammar/lab/index.html)** —
notebooks running on Pyodide, nothing to install. (Live once the repository has Pages
enabled; see `demo/`.)

```python
from sparql_grammar import iri, optional, select, var

query = select(
    "?concept", "?label",
    where=[
        ("?concept", "a", iri("skos:Concept")),
        ("?concept", iri("skos:prefLabel"), "?label"),
        optional(("?concept", iri("skos:broader"), "?parent")),
    ],
    limit=10,
    prefixes={"skos": "http://www.w3.org/2004/02/skos/core#"},
)

print(query.to_pretty_string())
```

```sparql
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?concept ?label
WHERE {
  ?concept a skos:Concept .
  ?concept skos:prefLabel ?label
  OPTIONAL {
    ?concept skos:broader ?parent
  }
}
LIMIT 10
```

## Two ways in

Write the objects, or write SPARQL and get the objects:

```python
from sparql_grammar import parse            # pip install sparql-grammar[parse]

query = parse("SELECT ?s WHERE { ?s a <http://ex/C> } LIMIT 10")
query.query.query.solution_modifier.limit_offset.limit_clause.limit = INTEGER("100")
print(query)                                # ... LIMIT 100
```

Two ways out, as well. `to_string()` is the canonical, cheap rendering for sending to an
endpoint; `to_pretty_string()` indents it for a human. Layout costs nothing unless asked
for.

## Why the rebuild

This is the successor to `sparql-grammar-pydantic`. Same idea — model the grammar, not
strings — rebuilt after measuring the original under the load its main consumer actually
puts on it (building query trees on every HTTP request).

The headline turned out **not** to be pydantic. Dropping it accounts for roughly a
seventh of the improvement; the rest came from two structural fixes: rendering by
appending into one buffer instead of delegating through a chain of generators, and
modelling recursive productions as flat lists instead of linked lists.

Measured by `benchmarks/bench.py`, which renders **the same query** from both libraries
using both real class trees (a prez-shaped `CONSTRUCT` + `WHERE`):

| triples | | 0.1.11 | this | |
|---|---|---|---|---|
| 400 | build | 14.1 ms | 1.75 ms | 8.0× |
| 400 | render | 39.4 ms | 0.85 ms | 46× |
| 400 | deepcopy | 31.5 ms | 7.3 ms | 4.3× |
| 800 | render | 148.8 ms | 1.88 ms | 79× |
| 10,000 | render | 21.6 **s** | 12.7 ms | 1700× |

The speedup grows with query size because the old rendering was quadratic. Per doubling
of input, the old library's render time grew 3.3–3.7×; this one grows 1.8–2.2×, i.e.
linearly. The old library also hit `RecursionError` a little past a thousand triples;
there is no such ceiling here.

Structure is smaller too — 1.63× fewer nodes per query — because productions that are a
bare alternation (`VarOrTerm ::= Var | iri | ...`) are union type aliases rather than
wrapper classes, so a term goes straight where the grammar allows a term.

| | before | now |
|---|---|---|
| Node type | pydantic `BaseModel` | `dataclass(slots=True)` |
| Per-node memory | 80 B + `__dict__` | 40 B |
| Rendering | generator `yield from` chains | append into one buffer |
| Recursive productions | linked lists, quadratic, hard ceiling | flat lists, linear |
| Validation | always on, partly broken | opt-in, two levels |
| Hashing | hand-written on ~30 classes, most unhashable | structural, every node hashable |
| Grammar coverage | 69% of SPARQL 1.1 | 100% of SPARQL 1.2, machine-checked |
| UPDATE | declared but unconstructible | complete |

## Writing less

The grammar is verbose by nature: a `FILTER` comparison sits nine levels down the
expression tower, and a single-predicate path six levels down its own. Builders live on
the production they build, so the tower is never spelled out by hand:

```python
Expression.compare(var("count"), "=", 101)      # ?count = 101
Expression.all_of(a, b, c)                      # a && b && c
Expression.negate(is_blank("?node"))            # !isBLANK(?node)
PathAlternative.seq(iri("ex:a"), iri("ex:b"))   # ex:a/ex:b
PathAlternative.mod(iri("ex:broader"), "+")     # ex:broader+
Aggregate.count(var("x"), distinct=True)        # COUNT(DISTINCT ?x)
```

`sparql_grammar.helpers` adds the cross-production shorthands — `triple`, `values`,
`filter_`, `optional`, `union`, `graph`, `service`, `bind`, `select`, `construct`,
`modify`, and so on. Every one returns ordinary grammar nodes, so results stay
inspectable, mutable and hashable.

Coercion only interprets what is unambiguous: `?x` is a variable, `<...>` is an IRI,
`"a"` in predicate position is `rdf:type`, and anything else is a literal. A bare
`http://...` string is **not** guessed to be an IRI — use `iri()` — because that guess
silently misreads literals that look like URLs.

## Validation is opt-in

Construction never validates; that is the hot path. Ask for it when you want it:

```python
node.validate("terminals")   # terminal values against their spec regex
node.validate("full")        # terminals plus field types

with debug_validation():     # or check everything as it is constructed
    ...
```

Constraints that types cannot express are checked here rather than left unenforced:
`SEPARATOR` only on `GROUP_CONCAT`, `*` only on `COUNT`, `MODIFY` needing a `DELETE` or
`INSERT` clause. All three were broken or unenforceable before.

## Grammar coverage is a fact, not a claim

`spec/sparql.bnf` is the W3C machine-readable grammar, vendored verbatim.
`tools/audit.py` checks the implemented classes against it:

```
$ python tools/audit.py
coverage: 194/194 productions implemented (100%) - 156 classes, 38 alternation aliases

$ python tools/audit.py --lark
parser grammar: 194/194 spec productions have a rule (100%)
```

The same check covers the parser grammar, and reports every rule it adds beyond the
spec. That is deliberate: the parser grammar began life elsewhere, and this is how it
earns trust rather than being taken on faith. It has already caught nine unreachable
rules and one production that SPARQL 1.2 removed.

Field names and shapes are hand-written on purpose. EBNF names productions but not their
parts, so generated classes end up with positional, anonymous fields — precisely the
thing that made the previous API awkward to use. The grammar file proves
*completeness*; people design the *API*. (`tools/audit.py --skeleton` will still write
the boring first draft of a missing class.)

## The browser demo

`demo/` holds a [JupyterLite](https://jupyterlite.readthedocs.io/) site that runs the
library in the browser, published to GitHub Pages by
`.github/workflows/deploy-demo.yml`. It works because the package is pure Python with no
runtime dependencies, and because `lark` is pure Python too, so the `parse` extra runs
there as well.

The notebooks are written as plain Python in `demo/src/`, not as notebook JSON, so the
code can be run and tested like any other code. CI regenerates the notebooks, checks they
are not stale, and executes every cell before publishing — a demo that raises cannot go
out.

## Testing

```
pytest                       # 400+ tests
python tools/audit.py        # grammar coverage
python benchmarks/bench.py   # against 0.1.11
```

The parser is checked against the W3C syntax test suites and the specification's own
examples — 941 queries. All of them parse, all of them re-render to text that parses
back to the same tree, and all of their formatted output does too. 16 of the 27 invalid
queries in the negative suite are correctly rejected; the parser grammar is more
permissive than the spec in the rest, which is asserted in the tests so it cannot
quietly get worse.

## Installing

```shell
pip install sparql-grammar             # core, no dependencies
pip install sparql-grammar[parse]      # + SPARQL text -> objects (lark)
pip install sparql-grammar[rdflib]     # + rdflib term conversion
```

## Migrating from sparql-grammar-pydantic

Most call sites are unchanged: `Var(value="x")`, `IRI(value="...")`,
`TriplesSameSubjectPath.from_spo(...)`, `Expression.from_primary_expression(...)`,
`TriplesBlock.from_tssp_list(...)` and `GroupGraphPatternSub.add_pattern(...)` all still
work. The differences worth knowing:

| Before | Now | Why |
|---|---|---|
| `GraphTerm(content=x)` | pass `x` directly | SPARQL 1.2 removed `GraphTerm` |
| `VarOrTerm(varorterm=x)` | pass `x` directly | alternation productions are union aliases |
| `PrimaryExpression(content=x)` | pass `x` directly | same |
| `from_tssp_list` reversed its input | keeps source order | the old order was a bug |
| `TriplesBlock(triples=..., triples_block=...)` | `TriplesBlock([...])` | flat list, not a linked list |
| `collect_triples()` | `collect(TriplesSameSubjectPath)` | generalised, linear, and actually works |
| `LANGTAG` | `LANG_DIR` | renamed in SPARQL 1.2, with an optional base direction |
| `SubSelectString` | `parse()` | a real parser instead of an rdflib round-trip |
| `?a=1` | `?a = 1` | operators render spaced, matching the spec's examples |

The trailing `.` after the last triple of a block is no longer emitted; it is optional in
the grammar.

## Licence

BSD-3-Clause.
