# %% [markdown]
# # Building SPARQL queries as objects
#
# `sparql-grammar` models the [SPARQL 1.2](https://www.w3.org/TR/sparql12-query/)
# grammar as one Python class per production. Every class renders itself back to
# SPARQL, so a query is ordinary data you can build, inspect and change.
#
# This notebook runs entirely in your browser — no server, no install. Edit any cell
# and press Shift+Enter.

# %%
import piplite

await piplite.install(["sparql-grammar", "lark"])

# %%
from sparql_grammar import *

# The short way in: helpers that coerce their arguments.
query = select(
    "?concept",
    "?label",
    where=[
        ("?concept", "a", iri("skos:Concept")),
        ("?concept", iri("skos:prefLabel"), "?label"),
        optional(("?concept", iri("skos:broader"), "?parent")),
    ],
    limit=10,
    prefixes={"skos": "http://www.w3.org/2004/02/skos/core#"},
)

print(query.to_pretty_string())

# %% [markdown]
# ## Coercion rules
#
# Strings are only interpreted where the syntax is unambiguous: `?x` is a variable,
# `<...>` is an IRI, `a` in predicate position is `rdf:type`. Anything else is a
# literal — a bare `http://...` string is *not* guessed to be an IRI, because that
# guess silently misreads literals that look like URLs.

# %%
for value in ["?s", "<http://ex/p>", "http://ex/p", "hello", 42, True]:
    print(f"{value!r:20} -> {type(term(value)).__name__:16} {term(value)}")

# %% [markdown]
# ## The parts that used to be painful
#
# A `FILTER` comparison sits nine levels down the expression tower, and a
# single-predicate path six levels down its own. Builders live on the production
# they build, so you never spell the tower out.

# %%
print(Expression.compare(var("count"), "=", 101))
print(Expression.all_of(
    Expression.compare(var("a"), ">", 1),
    Expression.compare(var("b"), "<", 10),
))
print(Expression.negate(is_blank("?node")))
print(PathAlternative.seq(iri("ex:a"), iri("ex:b")))
print(PathAlternative.mod(iri("ex:broader"), "+"))
print(Aggregate.count(var("x"), distinct=True))

# %% [markdown]
# ## A bigger query
#
# UNION, GRAPH, VALUES, aggregation and a subquery, composed from the same pieces.

# %%
query = select(
    "?scheme",
    (Expression.from_primary_expression(count()), var("concepts")),
    where=[
        values("scheme", [iri("ex:s1"), iri("ex:s2")]),
        graph("?g", ("?concept", iri("skos:inScheme"), "?scheme")),
        union(
            ("?concept", iri("skos:prefLabel"), "?label"),
            ("?concept", iri("skos:altLabel"), "?label"),
        ),
        filter_(regex("?label", "water", "i")),
        filter_(not_exists(("?concept", iri("owl:deprecated"), literal(True)))),
    ],
    group_by=var("scheme"),
    having=Expression.compare(var("concepts"), ">", 5),
    order_by=OrderCondition.desc(var("concepts")),
    limit=20,
    prefixes={
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "ex": "http://example.com/",
    },
)
print(query.to_pretty_string())

# %% [markdown]
# ## SPARQL Update
#
# The whole update grammar is supported — none of it was usable in the predecessor.

# %%
print(modify(
    where=[("?s", iri("ex:old"), "?o")],
    delete=[("?s", iri("ex:old"), "?o")],
    insert=[("?s", iri("ex:new"), "?o")],
    prefixes={"ex": "http://example.com/"},
).to_pretty_string())

# %% [markdown]
# ## SPARQL 1.2
#
# Reified triples, triple terms, annotations, `VERSION`, and base directions on
# language tags.

# %%
print(ReifiedTriple(var("s"), iri("ex:p"), var("o"), Reifier(var("r"))))
print(TripleTerm(var("s"), iri("ex:p"), var("o")))
print(RDFLiteral.langed("مرحبا", "ar--rtl"))
print(BuiltInCall.create("isTRIPLE", var("x")))
