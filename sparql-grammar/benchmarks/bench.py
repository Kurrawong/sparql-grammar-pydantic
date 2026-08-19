"""Compare sparql-grammar against sparql-grammar-pydantic 0.1.11.

Run with::

    python benchmarks/bench.py

Rules this benchmark holds itself to, so the numbers mean something:

* Two quirks of the old library are worked around so that both sides render the
  same query: its triples-block builder emits the triples in reverse, so it is fed a
  reversed list, and one difference in output is normalised away:
  the grammar makes the ``.`` after the final triple of a block optional, and the old
  library always emits it while this one does not. Nothing else is normalised - any
  other divergence is reported and the run stops, rather than being timed.
* Both sides use their real class trees. No simplified stand-ins - an earlier
  version of this comparison used three-field stub classes on the new side and
  flattered it by roughly ten times.
* Node counts per triple are printed next to the timings, because "faster" means
  little without knowing how much structure each library builds.
* The old library needs rdflib. If it is missing, a minimal stub is installed, which
  makes the old numbers a floor: real rdflib term rendering is slower.

The old library is loaded from the git branch the downstream project pins
(david/temp-prez-compatible-patch), so this measures what people actually run.
"""

from __future__ import annotations

import copy
import subprocess
import sys
import timeit
import types
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OLD_REF = "origin/david/temp-prez-compatible-patch:sparql_grammar_pydantic/grammar.py"
REPO = Path(__file__).resolve().parent.parent.parent


def _install_rdflib_stub() -> bool:
    """Give the old library the rdflib surface it imports, if rdflib is absent."""
    try:
        import rdflib  # noqa: F401

        return False
    except ImportError:
        pass

    module = types.ModuleType("rdflib")

    class URIRef(str):
        def n3(self):
            return f"<{self}>"

    class Variable(str):
        def n3(self):
            return f"?{self}"

    class Literal(str):
        def n3(self):
            return f'"{self}"'

    module.URIRef, module.Variable, module.Literal = URIRef, Variable, Literal
    sys.modules["rdflib"] = module
    for name in ("rdflib.plugins", "rdflib.plugins.sparql", "rdflib.plugins.sparql.algebra"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["rdflib.plugins.sparql"].prepareQuery = lambda q: q
    sys.modules["rdflib.plugins.sparql.algebra"].translateAlgebra = lambda q: q
    return True


def load_old():
    """Load the pinned old library from git, without writing it to disk."""
    source = subprocess.run(
        ["git", "-C", str(REPO), "show", OLD_REF],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    module = types.ModuleType("old_grammar")
    sys.modules["old_grammar"] = module
    exec(compile(source, "grammar.py(0.1.11)", "exec"), module.__dict__)  # noqa: S102
    return module


def count_nodes_new(node) -> int:
    from sparql_grammar import Node

    return sum(1 for _ in node.walk()) if isinstance(node, Node) else 0


def count_nodes_old(node) -> int:
    """Walk an old-library tree by its pydantic fields."""
    seen = 0
    stack = [node]
    while stack:
        current = stack.pop()
        if hasattr(current, "model_fields"):
            seen += 1
            for name in type(current).model_fields:
                value = getattr(current, name, None)
                if isinstance(value, (list, tuple)):
                    stack.extend(value)
                elif value is not None:
                    stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return seen


# ---------------------------------------------------------------------------
# The workloads
# ---------------------------------------------------------------------------


def make_old_builders(old):
    IRI, Var = old.IRI, old.Var
    TSSP, TSS = old.TriplesSameSubjectPath, old.TriplesSameSubject
    TriplesBlock, ConstructTriples = old.TriplesBlock, old.ConstructTriples

    def build(n):
        # Both from_tss_list and from_tssp_list build their linked lists back to
        # front, so the old library renders the triples in reverse. Feeding it
        # reversed input makes both libraries emit the same query, which is what the
        # timings need.
        template = ConstructTriples.from_tss_list(
            [
                TSS.from_spo(Var(value=f"s{i}"), IRI(value="http://ex/p"), Var(value=f"o{i}"))
                for i in reversed(range(n))
            ]
        )
        where = TriplesBlock.from_tssp_list(
            [
                TSSP.from_spo(Var(value=f"s{i}"), IRI(value="http://ex/p"), Var(value=f"o{i}"))
                for i in reversed(range(n))
            ]
        )
        return template, where

    return build


def make_new_builders():
    from sparql_grammar import IRI, ConstructTriples, TriplesBlock, TriplesSameSubject
    from sparql_grammar import TriplesSameSubjectPath as TSSP
    from sparql_grammar import Var

    def build(n):
        template = ConstructTriples(
            [
                TriplesSameSubject.from_spo(Var(f"s{i}"), IRI("http://ex/p"), Var(f"o{i}"))
                for i in range(n)
            ]
        )
        where = TriplesBlock(
            [TSSP.from_spo(Var(f"s{i}"), IRI("http://ex/p"), Var(f"o{i}")) for i in range(n)]
        )
        return template, where

    return build


def _normalise(text: str) -> str:
    """Ignore the optional trailing '.' at the end of a triples block."""
    return text.strip().removesuffix(".").strip()


def _fmt(ms: float) -> str:
    return f"{ms:8.2f}ms" if ms >= 0.01 else f"{ms * 1000:8.1f}us"


def compare(label: str, old_call, new_call, number: int) -> tuple[float, float]:
    old_ms = timeit.timeit(old_call, number=number) / number * 1000
    new_ms = timeit.timeit(new_call, number=number) / number * 1000
    speedup = old_ms / new_ms if new_ms else float("inf")
    print(f"  {label:22s} {_fmt(old_ms)}  {_fmt(new_ms)}  {speedup:7.1f}x")
    return old_ms, new_ms


def main() -> int:
    stubbed = _install_rdflib_stub()
    old = load_old()
    sys.setrecursionlimit(100_000)

    build_old = make_old_builders(old)
    build_new = make_new_builders()

    print("sparql-grammar vs sparql-grammar-pydantic 0.1.11")
    if stubbed:
        print("(rdflib stubbed: the old numbers are a floor, real rdflib is slower)")

    # equivalence and structure size, before any timing
    print("\nequivalence check and tree size")
    print(f"  {'N':>5}  {'identical output':>16}  {'old nodes':>10}  {'new nodes':>10}  {'ratio':>6}")
    for n in (1, 10, 100):
        old_template, old_where = build_old(n)
        new_template, new_where = build_new(n)
        same = _normalise(old_template.to_string()) == _normalise(
            new_template.to_string()
        ) and _normalise(old_where.to_string()) == _normalise(new_where.to_string())
        old_nodes = count_nodes_old(old_template) + count_nodes_old(old_where)
        new_nodes = count_nodes_new(new_template) + count_nodes_new(new_where)
        print(
            f"  {n:>5}  {str(same):>16}  {old_nodes:>10}  {new_nodes:>10}  "
            f"{old_nodes / new_nodes:>5.2f}x"
        )
        if not same:
            print("\n  outputs differ - the comparison below would be meaningless")
            print(f"    old: {old_where.to_string()[:100]!r}")
            print(f"    new: {new_where.to_string()[:100]!r}")
            return 1

    print("\nprez-shaped CONSTRUCT + WHERE          old        new    speedup")
    for n, number in ((100, 5), (200, 5), (400, 3), (800, 3)):
        print(f"  --- {n} triples ---")
        compare("build", lambda: build_old(n), lambda: build_new(n), number)

        old_template, old_where = build_old(n)
        new_template, new_where = build_new(n)
        compare(
            "render",
            lambda: (old_template.to_string(), old_where.to_string()),
            lambda: (new_template.to_string(), new_where.to_string()),
            number,
        )
        compare(
            "deepcopy",
            lambda: copy.deepcopy(old_where),
            lambda: copy.deepcopy(new_where),
            number,
        )

    print("\nscaling of render (a linear model doubles when the input doubles)")
    for label, builder in (("old", build_old), ("new", build_new)):
        previous = None
        row = []
        for n in (100, 200, 400, 800):
            _, where = builder(n)
            ms = timeit.timeit(where.to_string, number=3) / 3 * 1000
            row.append("-" if previous is None else f"{ms / previous:.1f}x")
            previous = ms
        print(f"  {label}: " + "  ".join(f"{n}:{r:>5}" for n, r in zip((100, 200, 400, 800), row)))

    print("\nceiling")
    for n in (1_000, 10_000):
        for label, builder in (("old", build_old), ("new", build_new)):
            try:
                _, where = builder(n)
                ms = timeit.timeit(where.to_string, number=1) * 1000
                print(f"  {label:3s} {n:>6} triples: {_fmt(ms)}")
            except RecursionError:
                print(f"  {label:3s} {n:>6} triples: RecursionError")
            except Exception as exc:  # noqa: BLE001
                print(f"  {label:3s} {n:>6} triples: {type(exc).__name__}")

    print("\nnew-library operations, and what each validation option costs")
    print("  (all validation is opt-in and off by default)")
    _validation_report(build_new, 400)

    print("\nexpression ladder (one FILTER comparison)")
    old_expression = _old_comparison(old)
    new_expression = _new_comparison()
    print(f"  identical output: {old_expression() .to_string() == new_expression().to_string()}")
    compare("build", old_expression, new_expression, 2000)
    old_built, new_built = old_expression(), new_expression()
    compare("render", old_built.to_string, new_built.to_string, 5000)
    print(
        f"  nodes per comparison: old {count_nodes_old(old_built)}, "
        f"new {count_nodes_new(new_built)}"
    )
    return 0


def _validation_report(build_new, n: int) -> None:
    """Cost of every validation option, plus the traversal-based operations."""
    import copy as _copy

    from sparql_grammar import TriplesSameSubjectPath, set_debug_validation

    template, where = build_new(n)

    def with_debug(level):
        def run():
            set_debug_validation(level)
            try:
                build_new(n)
            finally:
                set_debug_validation(False)

        return run

    rows = [
        ("build (no validation)", lambda: build_new(n), 3),
        ("build + debug 'terminals'", with_debug("terminals"), 3),
        ("build + debug 'full'", with_debug("full"), 3),
        ("validate('terminals') pass", lambda: (template.validate("terminals"), where.validate("terminals")), 3),
        ("validate('full') pass", lambda: (template.validate("full"), where.validate("full")), 3),
        ("render to_string()", lambda: (template.to_string(), where.to_string()), 3),
        ("render to_pretty_string()", lambda: (template.to_pretty_string(), where.to_pretty_string()), 3),
        ("deepcopy", lambda: _copy.deepcopy(where), 3),
        ("hash(tree)", lambda: hash(where), 10),
        ("collect(TriplesSameSubjectPath)", lambda: where.collect(TriplesSameSubjectPath), 5),
    ]
    baseline = None
    print(f"  {n} triples")
    for label, call, number in rows:
        # min-of-5: the least noisy estimator for a timing like this
        ms = min(timeit.repeat(call, number=number, repeat=5)) / number * 1000
        if baseline is None:
            baseline = ms
        print(f"    {label:32s} {_fmt(ms)}  {ms / baseline:5.1f}x build")


def _old_comparison(old):
    def build():
        return old.Expression(
            conditional_or_expression=old.ConditionalOrExpression(
                conditional_and_expressions=[
                    old.ConditionalAndExpression(
                        value_logicals=[
                            old.ValueLogical(
                                relational_expression=old.RelationalExpression(
                                    left=old.NumericExpression(
                                        additive_expression=old.AdditiveExpression(
                                            base_expression=old.MultiplicativeExpression(
                                                base_expression=old.UnaryExpression(
                                                    primary_expression=old.PrimaryExpression(
                                                        content=old.Var(value="count")
                                                    )
                                                )
                                            )
                                        )
                                    ),
                                    operator="=",
                                    right=old.NumericExpression(
                                        additive_expression=old.AdditiveExpression(
                                            base_expression=old.MultiplicativeExpression(
                                                base_expression=old.UnaryExpression(
                                                    primary_expression=old.PrimaryExpression(
                                                        content=old.NumericLiteral(value=101)
                                                    )
                                                )
                                            )
                                        )
                                    ),
                                )
                            )
                        ]
                    )
                ]
            )
        )

    return build


def _new_comparison():
    from sparql_grammar import Expression, Var

    def build():
        return Expression.compare(Var("count"), "=", 101)

    return build


if __name__ == "__main__":
    raise SystemExit(main())
