"""Cross-check the implemented node classes against spec/sparql.bnf.

This is the coverage guarantee that makes hand-written classes safe: the .bnf is the
authority on *which* productions exist, so any production without a registered class
(or any class whose name is not a production) is reported here and in CI.

    python tools/audit.py             # coverage report
    python tools/audit.py --skeleton  # emit class stubs for missing productions
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.bnf import Production, parse_bnf  # noqa: E402


def load_registry() -> dict[str, object]:
    """Every implemented production: node classes plus alternation aliases."""
    import sparql_grammar  # noqa: F401  (imports every module, populating REGISTRY)
    from sparql_grammar._base import ALIASES, REGISTRY

    return {**REGISTRY, **ALIASES}


def audit() -> tuple[list[Production], list[str], dict[str, type]]:
    prods = parse_bnf()
    registry = load_registry()
    missing = [p for p in prods if p.name not in registry]
    names = {p.name for p in prods}
    extra = sorted(n for n in registry if n not in names)
    return missing, extra, registry


def skeleton(p: Production) -> str:
    """Emit a starting-point class stub. Field names are left to a human."""
    kind = "Terminal" if p.terminal else "Node"
    return (
        f"@production\n"
        f"class {p.name}({kind}):\n"
        f'    """{p.name} ::= {p.body}"""\n\n'
        f"    # TODO fields: refs={p.refs} literals={p.literals}\n\n"
        f"    def render(self, add: Add) -> None:\n"
        f"        raise NotImplementedError\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skeleton", action="store_true", help="emit stubs for gaps")
    ap.add_argument("--strict", action="store_true", help="exit 1 unless complete")
    args = ap.parse_args()

    missing, extra, registry = audit()
    total = len(parse_bnf())
    done = total - len(missing)

    from sparql_grammar._base import ALIASES, REGISTRY

    print(
        f"coverage: {done}/{total} productions implemented ({done / total:.0%}) "
        f"- {len(REGISTRY)} classes, {len(ALIASES)} alternation aliases"
    )
    if missing:
        nt = [p.name for p in missing if not p.terminal]
        te = [p.name for p in missing if p.terminal]
        if nt:
            print(f"\nmissing nonterminals ({len(nt)}):")
            for name in nt:
                print(f"  {name}")
        if te:
            print(f"\nmissing terminals ({len(te)}):")
            for name in te:
                print(f"  {name}")
    if extra:
        print(f"\nregistered but not in the grammar ({len(extra)}):")
        for name in extra:
            print(f"  {name}")

    if args.skeleton and missing:
        print("\n# ---- skeletons ----")
        for p in missing:
            print()
            print(skeleton(p))

    if args.strict and (missing or extra):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
