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

# The short way in: helpers that assemble the productions for you.
query = select(
    var("concept"),
    var("label"),
    where=[
        (var("concept"), "a", iri("skos:Concept")),
        (var("concept"), iri("skos:prefLabel"), var("label")),
        optional((var("concept"), iri("skos:broader"), var("parent"))),
    ],
    limit=10,
    prefixes={"skos": "http://www.w3.org/2004/02/skos/core#"},
)

print(query.to_pretty_string())

# %% [markdown]
# ## Terms are explicit
#
# No string is ever read as a term. `var()`, `iri()` and `literal()` say which one you
# mean, the same way rdflib makes you choose between `URIRef` and `Literal`. The text
# alone cannot tell you: `"<http://x>"` is as plausibly a literal as an IRI, and a
# value read as a *variable* would widen a query rather than parameterise it.
#
# Python values that already carry their type — `int`, `float`, `bool` — need no help.
# The one keyword that stays a string is `a`, which is `rdf:type`, not a term.

# %%
for value in [var("s"), iri("http://ex/p"), literal("http://ex/p"), 42, -1.5, True]:
    print(f"{str(value):22} {type(term(value)).__name__}")

# %%
# and a string in a term position is refused, with the fix in the message
for text in ["?s", "<http://ex/p>", "hello"]:
    try:
        term(text)
    except TypeError as error:
        print(f"{text!r:16} {error}")

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
print(Expression.negate(is_blank(var("node"))))
print(PathAlternative.seq(iri("ex:a"), iri("ex:b")))
print(PathAlternative.mod(iri("ex:broader"), "+"))
print(Aggregate.count(var("x"), distinct=True))

# %% [markdown]
# ## A bigger query
#
# UNION, GRAPH, VALUES, aggregation and a subquery, composed from the same pieces.

# %%
query = select(
    var("scheme"),
    (Expression.from_primary_expression(count()), var("concepts")),
    where=[
        values("scheme", [iri("ex:s1"), iri("ex:s2")]),
        graph(var("g"), (var("concept"), iri("skos:inScheme"), var("scheme"))),
        union(
            (var("concept"), iri("skos:prefLabel"), var("label")),
            (var("concept"), iri("skos:altLabel"), var("label")),
        ),
        filter_(regex(var("label"), "water", "i")),
        filter_(not_exists((var("concept"), iri("owl:deprecated"), literal(True)))),
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
    where=[(var("s"), iri("ex:old"), var("o"))],
    delete=[(var("s"), iri("ex:old"), var("o"))],
    insert=[(var("s"), iri("ex:new"), var("o"))],
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
