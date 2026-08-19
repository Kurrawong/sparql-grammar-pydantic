# %% [markdown]
# # Parsing SPARQL back into objects
#
# Write the SPARQL you already know, get a typed tree, change it programmatically,
# render it back. Useful when you have a query and want to adapt it rather than
# rebuild it.

# %%
import piplite

await piplite.install(["sparql-grammar", "lark"])

# %%
from sparql_grammar import *
from sparql_grammar.parse import parse, to_python_source

query = parse("""
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?concept ?label
    WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label .
        OPTIONAL { ?concept skos:broader ?parent }
    }
    LIMIT 10
""")

type(query).__name__

# %% [markdown]
# It is an ordinary object tree. Walk it, search it, change it.

# %%
print("variables:", sorted({v.value for v in query.collect(Var)}))
print("triples   :", len(query.collect(TriplesSameSubjectPath)))

# %%
# raise the limit
query.query.query.solution_modifier.limit_offset.limit_clause.limit = INTEGER("500")

# add a pattern
ggps = query.query.query.where_clause.group_graph_pattern.content
ggps.add_pattern(filter_(regex(var("label"), "water", "i")))

print(query.to_pretty_string())

# %% [markdown]
# ## Round-tripping
#
# Rendering is stable: parse, render, parse again, and you get the same tree. This
# is checked against the W3C syntax test suites and the specification's own
# examples — 941 queries, all of them stable.

# %%
source = "SELECT * WHERE { ?s <http://a>/<http://b>|^<http://c> ?o } ORDER BY DESC(?o)"
once = parse(source).to_string()
twice = parse(once).to_string()
print(once)
print("\nstable:", once == twice)

# %% [markdown]
# ## Turning SPARQL into Python
#
# A development shortcut: parse a query you have, and print the constructor calls
# that would build it.

# %%
print(to_python_source(parse("SELECT ?s WHERE { ?s a <http://ex/C> } LIMIT 5")))

# %% [markdown]
# ## Equality and hashing
#
# Every node is hashable and compares structurally, so deduplication and set
# operations work on query fragments. The predecessor could not do this — most of
# its classes were unhashable.

# %%
a = triple(var("s"), iri("ex:p"), var("o"))
b = triple(var("s"), iri("ex:p"), var("o"))
c = triple(var("s"), iri("ex:q"), var("o"))
print("a == b :", a == b)
print("unique :", len({a, b, c}))
