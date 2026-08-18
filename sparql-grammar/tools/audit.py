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
    ap.add_argument("--lark", action="store_true", help="check the parser grammar too")
    args = ap.parse_args()

    if args.lark:
        return main_lark()

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




# ---------------------------------------------------------------------------
# Parser-grammar cross-check
#
# grammar.lark started life as a third-party SPARQL 1.1 grammar. Rather than trust
# it, this compares its rule set against spec/sparql.bnf, which is the authority.
# Naming convention: production FooBar <-> rule foo_bar, TERMINAL <-> TERMINAL.
# ---------------------------------------------------------------------------

import re as _re


def _snake(name: str) -> str:
    """PascalCase production name -> snake_case lark rule name.

    Handles acronym runs, so RDFLiteral maps to rdf_literal rather than
    r_d_f_literal, and leaves all-caps terminal names alone.
    """
    if name.upper() == name:  # a terminal: IRIREF, PN_CHARS_BASE
        return name
    spaced = _re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return _re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced).lower()


def lark_rules(path: Path | None = None) -> tuple[set[str], set[str]]:
    """Return (rule names, terminal names) defined in the lark grammar."""
    text = (path or Path(__file__).resolve().parent.parent / "sparql_grammar" / "grammar.lark").read_text(
        encoding="utf-8"
    )
    rules = set(_re.findall(r"^([a-z_][a-z_0-9]*)\s*:", text, _re.M))
    terminals = set(_re.findall(r"^([A-Z_][A-Z_0-9]*)\s*:", text, _re.M))
    return rules, terminals


def audit_lark() -> dict[str, list[str]]:
    """Compare the parser grammar against the spec grammar."""
    prods = parse_bnf()
    rules, terminals = lark_rules()
    defined = rules | terminals

    expected = {_snake(p.name): p for p in prods}
    missing = sorted(name for name in expected if name not in defined)
    # Rules the parser grammar adds. Split by kind so the report is actionable:
    # named terminals are lexer plumbing the spec spells inline, while extra rules
    # are helper productions for repetition - each one is a place the parser tree
    # differs in shape from the class model, so they are worth reviewing.
    extra = defined - set(expected) - {"unit", "start"}
    return {
        "missing": missing,
        "extra_terminals": sorted(n for n in extra if n.upper() == n),
        "extra_rules": sorted(n for n in extra if n.upper() != n),
    }


def main_lark() -> int:
    result = audit_lark()
    prods = parse_bnf()
    covered = len(prods) - len(result["missing"])
    print(
        f"parser grammar: {covered}/{len(prods)} spec productions have a rule "
        f"({covered / len(prods):.0%})"
    )
    if result["missing"]:
        print(f"\nspec productions with NO parser rule ({len(result['missing'])}):")
        for name in result["missing"]:
            print(f"  {name}")
    if result["extra_terminals"]:
        print(
            f"\nnamed terminals (lexer plumbing for punctuation and keywords the "
            f"spec spells inline): {len(result['extra_terminals'])}"
        )
    if result["extra_rules"]:
        print(f"\nhelper rules, not spec productions ({len(result['extra_rules'])}):")
        for name in result["extra_rules"]:
            print(f"  {name}")
    return 1 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
