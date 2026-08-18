"""Turn the demo sources in ``src/`` into notebooks in ``notebooks/``.

The demos are written as plain Python so the code can be run and tested like any
other code, rather than living in JSON where it cannot be. Cells are delimited by
``# %%``, and ``# %% [markdown]`` starts a prose cell whose ``#`` prefixes are
stripped.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = {
    "kernelspec": {
        "display_name": "Python (Pyodide)",
        "language": "python",
        "name": "python",
    },
    "language_info": {"name": "python"},
}


def split_cells(text: str) -> list[tuple[str, str]]:
    cells: list[tuple[str, str]] = []
    kind, buffer = "code", []
    for line in text.splitlines():
        if line.startswith("# %%"):
            if buffer:
                cells.append((kind, "\n".join(buffer).strip("\n")))
            kind = "markdown" if "[markdown]" in line else "code"
            buffer = []
            continue
        buffer.append(line)
    if buffer:
        cells.append((kind, "\n".join(buffer).strip("\n")))
    return [(kind, body) for kind, body in cells if body.strip()]


def to_notebook(text: str) -> dict:
    cells = []
    for kind, body in split_cells(text):
        if kind == "markdown":
            body = "\n".join(
                line[2:] if line.startswith("# ") else line.lstrip("#")
                for line in body.splitlines()
            )
            cells.append(
                {"cell_type": "markdown", "metadata": {}, "source": _lines(body)}
            )
        else:
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": _lines(body),
                }
            )
    return {"cells": cells, "metadata": KERNEL, "nbformat": 4, "nbformat_minor": 5}


def _lines(body: str) -> list[str]:
    lines = body.splitlines()
    return [f"{line}\n" for line in lines[:-1]] + lines[-1:]


def main() -> None:
    out = HERE / "notebooks"
    out.mkdir(exist_ok=True)
    for source in sorted((HERE / "src").glob("*.py")):
        name = source.stem.split("_", 1)
        title = f"{name[0]}-{name[1].replace('_', '-')}.ipynb"
        target = out / title
        target.write_text(
            json.dumps(to_notebook(source.read_text(encoding="utf-8")), indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"  {source.name} -> notebooks/{target.name}")


if __name__ == "__main__":
    main()
