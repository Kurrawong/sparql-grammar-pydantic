"""Parse the vendored W3C SPARQL 1.2 grammar (spec/sparql.bnf).

The .bnf file is the authoritative machine-readable grammar, copied verbatim from
the w3c/sparql-query spec sources. It is the single source of truth for *which*
productions exist; the Python classes in sparql_grammar own *how* each is shaped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BNF_PATH = Path(__file__).resolve().parent.parent / "spec" / "sparql.bnf"

_RULE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z_0-9]*)\s+::=\s*(?P<body>.*)$")


@dataclass
class Production:
    name: str
    body: str
    terminal: bool = False
    #: literal keywords/punctuation appearing in the RHS, in order of appearance
    literals: list[str] = field(default_factory=list)
    #: names of other productions referenced by the RHS
    refs: list[str] = field(default_factory=list)

    @property
    def is_terminal_name(self) -> bool:
        """True when the production name is spelled as a terminal (ALL_CAPS)."""
        return self.name.upper() == self.name


def _strip_literals(body: str) -> tuple[list[str], str]:
    """Pull quoted literals out of a RHS, returning them and the remaining text."""
    literals = re.findall(r"'([^']*)'|\"([^\"]*)\"", body)
    flat = [a or b for a, b in literals]
    return flat, re.sub(r"'[^']*'|\"[^\"]*\"", " ", body)


def parse_bnf(path: Path | str = BNF_PATH) -> list[Production]:
    """Parse the .bnf into ordered Production records."""
    text = Path(path).read_text(encoding="utf-8")
    prods: list[Production] = []
    in_terminals = False
    current: Production | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip() == "@terminals":
            in_terminals = True
            continue

        m = _RULE_RE.match(line)
        if m:
            current = Production(
                name=m.group("name"), body=m.group("body").strip(), terminal=in_terminals
            )
            prods.append(current)
        elif current is not None and line.lstrip().startswith("|"):
            # continuation line of the previous production's alternation
            current.body += " " + line.strip()

    known = {p.name for p in prods}
    for p in prods:
        p.literals, rest = _strip_literals(p.body)
        p.refs = [t for t in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", rest) if t in known]
    return prods


def summary(prods: list[Production]) -> dict[str, int]:
    return {
        "total": len(prods),
        "nonterminals": sum(1 for p in prods if not p.terminal),
        "terminals": sum(1 for p in prods if p.terminal),
    }


if __name__ == "__main__":
    ps = parse_bnf()
    s = summary(ps)
    print(f"{s['total']} productions ({s['nonterminals']} nonterminal, {s['terminals']} terminal)")
    for p in ps[:5]:
        print(f"  {p.name:26s} refs={p.refs[:4]} literals={p.literals[:3]}")
    print("  ...")
    for p in ps:
        if p.name in {"ReifiedTriple", "TripleTerm", "VersionDecl", "LANG_DIR"}:
            print(f"  {p.name:26s} {p.body[:70]}")
