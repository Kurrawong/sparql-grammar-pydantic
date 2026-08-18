# %% [markdown]
# # Formatting, validation and speed
#
# Two ways out of the object tree, opt-in validation, and why the rebuild happened.

# %%
import piplite

await piplite.install(["sparql-grammar", "lark"])

# %%
from sparql_grammar import *

query = select(
    "?s",
    where=[
        ("?s", "a", iri("ex:Thing")),
        optional(("?s", iri("ex:p"), "?o")),
        union(("?s", iri("ex:a"), "?x"), ("?s", iri("ex:b"), "?x")),
    ],
    limit=5,
    prefixes={"ex": "http://example.com/"},
)

# %% [markdown]
# `to_string()` is the canonical rendering: compact, cheap, and what you send to an
# endpoint. It appends into a single buffer and makes no layout decisions.

# %%
print(query.to_string())

# %% [markdown]
# `to_pretty_string()` indents it for a person. Layout is a separate structural walk,
# so it costs nothing unless you ask for it — and it never rewrites the contents of a
# literal.

# %%
print(query.to_pretty_string())

# %%
print(query.to_pretty_string(indent="    "))

# %% [markdown]
# ## Validation is opt-in
#
# Construction never validates, because that is the hot path. Nothing stops you
# building something wrong; ask for a check when you want one.

# %%
bad = VAR1("not a valid name!")
print("constructed without complaint:", repr(bad))

try:
    bad.validate("terminals")
except ValidationError as error:
    print("validate('terminals'):", error.errors[0])

# %%
# 'full' also type-checks every field against its annotation
from sparql_grammar import Aggregate, AggregateFunction

try:
    Aggregate.create("SUM", var("x"), separator=",").validate("full")
except ValidationError as error:
    print(error.errors[0])

# %% [markdown]
# ## Why the rebuild
#
# The predecessor modelled recursive productions as linked lists, which made
# rendering quadratic and put a hard ceiling near a thousand triples. Flat lists
# render linearly with no ceiling. Watch the time per triple stay flat.

# %%
import time

for n in (100, 1_000, 10_000, 50_000):
    block = TriplesBlock.from_spo_list(
        [(Var(f"s{i}"), IRI("http://ex/p"), Var(f"o{i}")) for i in range(n)]
    )
    start = time.perf_counter()
    text = block.to_string()
    elapsed = (time.perf_counter() - start) * 1000
    print(f"{n:>6} triples: {elapsed:7.1f} ms render, {elapsed / n * 1000:5.2f} us/triple")

# %% [markdown]
# For reference, on the machine where the benchmarks were run, the predecessor took
# 21.6 **seconds** to render 10,000 triples, and raised `RecursionError` not far
# above 1,000. Browsers are slower than that machine, so read the shape of the
# numbers above rather than their absolute values: the cost per triple is constant.

# %% [markdown]
# ## Grammar coverage
#
# The W3C machine-readable grammar is vendored in the repository, and a tool checks
# the implemented classes against it, so coverage is a fact rather than a claim.

# %%
from sparql_grammar._base import ALIASES, REGISTRY

print(f"{len(REGISTRY)} node classes + {len(ALIASES)} alternation aliases")
print(f"= {len(REGISTRY) + len(ALIASES)} of the 194 SPARQL 1.2 productions")
