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

concept, label, parent = var("concept"), var("label"), var("parent")

query = select(
    concept, label,
    where=[
        (concept, "a", iri("skos:Concept")),
        (concept, iri("skos:prefLabel"), label),
        optional((concept, iri("skos:broader"), parent)),
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
| 400 | build | 15.7 ms | 2.0 ms | 7.7× |
| 400 | render | 39–65 ms | 0.9 ms | 45–76× |
| 400 | deepcopy | 36.4 ms | 5.6 ms | 6.5× |
| 400 | equality | 7.2 ms | 0.8 ms | 9.2× |
| 400 | collect triples | 256 ms | 5.2 ms | 49× |
| 400 | hash | unhashable | 0.5 ms | — |
| 800 | render | 148.8 ms | 1.9 ms | 79× |
| 10,000 | render | 21.6 **s** | 12.7 ms | 1700× |

Other figures at 400 triples: tree memory 2016 KB → 382 KB (5.3× less), and 1.63×
fewer nodes. Formatted rendering (`to_pretty_string()`) is 1.3 ms. Parsing, with the
`parse` extra, is 0.67 ms per query under LALR. Importing the package takes ~100 ms.

The old library's render time swings between 39 ms and 65 ms across runs — it
allocates heavily and is sensitive to garbage-collection state — so the conservative
figure is quoted. Run `python benchmarks/bench.py` to reproduce all of it; it refuses
to report timings if the two libraries stop rendering the same query.

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
Expression.negate(is_blank(var("node")))        # !isBLANK(?node)
PathAlternative.seq(iri("ex:a"), iri("ex:b"))   # ex:a/ex:b
PathAlternative.mod(iri("ex:broader"), "+")     # ex:broader+
Aggregate.count(var("x"), distinct=True)        # COUNT(DISTINCT ?x)
```

`sparql_grammar.helpers` adds the cross-production shorthands — `triple`, `values`,
`filter_`, `optional`, `union`, `graph`, `service`, `bind`, `select`, `construct`,
`modify`, and so on. Every one returns ordinary grammar nodes, so results stay
inspectable, mutable and hashable.

### Terms are explicit — no string is ever interpreted

`var()`, `iri()` and `literal()` say which term you mean, exactly as rdflib makes you
choose between `URIRef` and `Literal`. A bare string in a term position is a
`TypeError`, and the message names the constructor to reach for:

```python
triple(var("s"), iri("skos:broader"), literal("x"))   # say what each one is
triple("?s", "skos:broader", "x")                     # TypeError, three times over
```

The reason is not tidiness. Reading a string by its shape lets the *value* choose its
role in the query:

| written | read as | but the caller may have meant |
|---|---|---|
| `"<http://ex/admin>"` | an IRI | the literal `"<http://ex/admin>"` |
| `"?anything"` | a variable | the literal `"?anything"` |
| `"skos:broader"` | a literal | the IRI `skos:broader` |

The variable case is the dangerous one: `VALUES ?name { "Alice" }` constrains a query,
while `VALUES ?name { ?anything }` removes the constraint altogether — so one untrusted
value beginning with `?` would rewrite the query rather than parameterise it. Escaping
cannot help, because nothing is being escaped; only the caller knows the type.

What still needs no ceremony:

* **`int`, `float`, `bool`** — the Python type already says which literal it is, so
  `literal(5)` is `5`, `literal(-1.5)` is `-1.5`, `literal(True)` is `true`, and
  `literal("5")` is the string `"5"`.
* **`"a"` in predicate position** — a SPARQL keyword for `rdf:type`, not a term.
* **A name where the grammar allows nothing but a variable** — the projection list,
  `BIND … AS`, the `VALUES` variable list. There is no second reading to get wrong:
  `select("?s", …)`, `bind(expr, "?count")`, `values("x", […])`.
* **Surface form within one type** — `iri("http://x")` renders `<http://x>` and
  `iri("skos:broader")` renders as a prefixed name; both are IRIs either way.
  Likewise `var("s")` and `var("?s")` are the same variable.

One name that surprises people: `INTEGER` really is a term. The grammar reads
`VarOrTerm ::= Var | iri | RDFLiteral | NumericLiteral | …`,
`NumericLiteral ::= NumericLiteralUnsigned | …`, and
`NumericLiteralUnsigned ::= INTEGER | DECIMAL | DOUBLE` — and because those middle
productions are bare alternations, this library models them as union aliases, so
`INTEGER` appears in `VarOrTerm` directly. A bare `5` in a triple is an `INTEGER` token
per the spec, however lexical the name sounds.

## Parameterised queries, and untrusted input

The usual shape is a query skeleton built once from values the program controls, with
inputs substituted per request. That makes the term constructors the only place input
safety matters, and there are three different jobs to do there:

**Text can be escaped, so it always is.** A string literal is safe to build from
hostile input with no ceremony:

```python
literal('x" . ?s ?p ?o . #')     # -> "x\" . ?s ?p ?o . #"   one literal, still
```

**IRIs, variable names and language tags cannot be escaped** — there is no escape
syntax for them — so a bad one can only be refused. The string-accepting helpers
therefore validate by default:

```python
iri("http://x> . ?s ?p ?o . <http://y")   # ValidationError
var("s . ?x ?y")                          # ValidationError
literal("x", lang='en" . #')              # ValidationError
```

**And the type of the term is never taken from the input**, per the section above — a
parameter cannot promote itself from a literal to an IRI, or to a variable.

So the pattern is: build the skeleton from your own values, and wrap each incoming
parameter in the constructor for the term you meant. Those constructors check by
default, so the short way is the safe way:

```python
template = select(                                                    # once, trusted
    var("s"), where=[(var("s"), iri("ex:p"), var("value"))]
)
...
row = values("value", [iri(v) for v in request_values])               # per request
```

Checking costs about 0.3 µs per term — a fraction of a microsecond, against the
milliseconds a whole-tree `validate()` would take. Pass `check=False`, or use the
production constructors (`IRI(...)`, `Var(...)`) which never validate, for values the
program produced itself.

## Validation of a whole tree is opt-in

Beyond the per-term checks above, a whole tree can be validated on demand. This is
for tests and development; it is not cheap.

```python
node.validate("terminals")           # terminal values against their spec regex
node.validate("full")                # terminals plus every field's type

with debug_validation("terminals"):  # or check as each node is constructed
    ...
with debug_validation():             # "full" is the default level
    ...
```

What each option costs, on a 400-triple query (min-of-5):

| mode | cost | vs a plain build |
|---|---|---|
| default — no whole-tree validation | 1.98 ms build | 1.0× |
| `debug_validation("terminals")` while building | 2.58 ms | 1.3× |
| `debug_validation()` — full — while building | 13.7 ms | 6.9× |
| `validate("terminals")` as a pass | +8.6 ms | 4.4× |
| `validate("full")` as a pass | +20.7 ms | 10.5× |

Worth reading twice: building with full construction-time validation (13.7 ms) costs
about what the *old* library's always-on validation cost (15.7 ms). Being opt-in is
where most of the build speedup comes from, so leave it off in production —
`debug_validation("terminals")` is the one cheap enough to develop with.

Constraints that types cannot express are checked here rather than left unenforced:
`SEPARATOR` only on `GROUP_CONCAT`, `*` only on `COUNT`, `MODIFY` needing a `DELETE` or
`INSERT` clause, a literal having a language *or* a datatype. All were broken or
unenforceable before.

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
| a bare string as a term | `iri()` / `literal()` / `var()` | nothing is guessed; see [Terms are explicit](#terms-are-explicit--no-string-is-ever-interpreted) |
| `"UNDEF"` in a `VALUES` row | the `UNDEF` node | a keyword, not a value, so `DataBlockValue` can stay precise |

The trailing `.` after the last triple of a block is no longer emitted; it is optional in
the grammar.

## Licence

BSD-3-Clause.
