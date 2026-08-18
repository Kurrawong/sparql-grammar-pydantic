# sparql-grammar

Typed Python objects for the [SPARQL 1.2](https://www.w3.org/TR/sparql12-query/) grammar:
one class per production of the W3C grammar, each able to render itself back to SPARQL text.

No runtime dependencies. No pydantic.

```python
from sparql_grammar import IRIREF, VAR1

IRIREF("http://example.com/p").to_string()   # '<http://example.com/p>'
VAR1("concept").to_string()                  # '?concept'
```

## Why a rebuild

This is the successor to `sparql-grammar-pydantic`. Same idea - model the grammar, not
strings - with three changes that came out of measuring the original under real load
(Prez builds query trees per HTTP request):

| | before | now |
|---|---|---|
| Node type | pydantic `BaseModel` | `dataclass(slots=True)` |
| Construction (28-node tree) | 54.5 us | 14.1 us |
| Per-node memory | 80 B + `__dict__` | 40 B |
| Rendering | generator `yield from` chains | append into one buffer |
| Render, deeply nested tree | 654 us | 29.5 us |
| Recursive productions | linked lists, O(n^2), `RecursionError` past ~1000 triples | flat lists, linear, no ceiling |
| Validation | always on, partly broken | opt-in, two levels |
| Hashing | ~30 hand-written, most classes unhashable | structural, every node hashable |

## Validation is opt-in

Construction never validates - that is the hot path. Ask for it when you want it:

```python
node.validate("terminals")   # terminal values against their spec regex
node.validate("full")        # terminals + field types

with debug_validation():     # or validate everything as it is constructed
    ...
```

## Grammar coverage

`spec/sparql.bnf` is the W3C machine-readable grammar, vendored verbatim.
`tools/audit.py` checks the implemented classes against it, so coverage is a fact rather
than a claim:

```
$ python tools/audit.py
coverage: 36/194 productions implemented (19%)
```

Field names and shapes are hand-written on purpose: EBNF names productions but not their
parts, so generated classes end up with positional, anonymous fields. The grammar file
proves *completeness*; humans own the *API*.

## Status

Under construction. Terminals and core machinery are done; the nonterminal productions,
helper layer, and the optional `[parse]` extra (SPARQL text -> objects) are next.
