# %% [markdown]
# # Formatting, validation and speed
#
# Two ways out of the object tree, opt-in validation, and why the rebuild happened.

# %%
# In the browser this fetches the wheels; outside Pyodide there is no piplite and
# the package is already installed, so the cell does nothing.
try:
    import piplite

    await piplite.install(["sparql-grammar", "lark"])
except ModuleNotFoundError:
    pass

# %%
from sparql_grammar import *

query = select(
    var("s"),
    where=[
        (var("s"), "a", iri("ex:Thing")),
        optional((var("s"), iri("ex:p"), var("o"))),
        union((var("s"), iri("ex:a"), var("x")), (var("s"), iri("ex:b"), var("x"))),
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
# ## Parameterised queries and untrusted input
#
# The usual shape is a skeleton built once from values you control, with inputs
# substituted per request. Three different jobs at that boundary:
#
# Text **can** be escaped, so it always is — a literal is safe from hostile input
# with no ceremony.

# %%
payload = 'x" . ?s ?p ?o . #'
print(literal(payload).to_string())
print(select(var("s"), where=[(var("s"), iri("http://p"), literal(payload))]).to_string())
# still one triple: the payload could not break out

# %% [markdown]
# IRIs, variable names and language tags have **no** escape syntax, so a bad one can
# only be refused. The string-accepting helpers validate by default.

# %%
for label, call in [
    ("iri", lambda: iri("http://x> . ?s ?p ?o . <http://y")),
    ("var", lambda: var("s . ?x ?y")),
    ("lang", lambda: literal("x", lang='en" . #')),
]:
    try:
        call()
        print(f"{label}: accepted")
    except ValidationError as error:
        print(f"{label}: refused - {error.errors[0][:60]}")

# %% [markdown]
# And the third job: the *type* of the term is yours to state, never inferred from the
# input. A parameter read as a variable would not narrow the query, it would widen it —
# `VALUES ?name { "Alice" }` asks a question, `VALUES ?name { ?anything }` asks none.

# %%
for hostile in ["?anything", "<http://ex/secret>"]:
    try:
        values("name", [hostile])
    except TypeError:
        print(f"{hostile!r:22} refused - say iri(...) or literal(...) and mean it")
# said explicitly, the same text is just text
print(values("name", [literal("?anything")]).to_string())

# %% [markdown]
# So: build the skeleton from your own values, and wrap each parameter in the
# constructor for the term you meant. Checking costs a fraction of a microsecond per
# term, against the milliseconds a whole-tree `validate()` would take.

# %%
template = select(var("s"), where=[(var("s"), iri("ex:p"), var("value"))],
                  prefixes={"ex": "http://example.com/"})
inputs = ["http://example.com/a", "http://example.com/b"]
print(values("value", [iri(v) for v in inputs]).to_string())
print()
print(template.to_string())

# %% [markdown]
# ## Whole-tree validation is opt-in
#
# Beyond the per-term checks above, a whole tree can be checked on demand. This is
# for tests and development - full validation costs several times a plain build.

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
