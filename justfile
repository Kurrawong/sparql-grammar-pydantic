# Demo and development tasks for sparql-grammar.
#
# The library lives in sparql-grammar/; recipes cd there for you, so every one of
# these runs from the repository root. `uv sync --all-extras` is enough to get a
# working environment - the jupyter tooling is layered on per-recipe with `--with`
# rather than added as a project dependency.

default:
    @just --list

# Create/refresh the venv: the project editable, plus the parse and rdflib extras.
[working-directory: 'sparql-grammar']
sync:
    uv sync --all-extras

# Run the test suite.
[working-directory: 'sparql-grammar']
test *args:
    uv run pytest {{ args }}

# --- demo -------------------------------------------------------------------

# Regenerate demo/notebooks/*.ipynb from their sources in demo/src/*.py.
[working-directory: 'sparql-grammar']
build-notebooks:
    uv run python demo/build_notebooks.py

# Run every demo cell offline. A demo that raises must not be published.
[working-directory: 'sparql-grammar']
test-demos:
    uv run python demo/test_demos.py

# Open the demos in a local JupyterLab. The piplite cell is a no-op off Pyodide.
[working-directory: 'sparql-grammar']
lab:
    uv run --with jupyterlab jupyter lab demo/notebooks

# What CI enforces: the notebooks are in sync with src/, and every cell runs.
[working-directory: 'sparql-grammar']
check-demos:
    #!/usr/bin/env bash
    set -euo pipefail
    # CI compares against a clean checkout; here the rebuild is compared against
    # whatever is on disk, so an uncommitted-but-current notebook still passes.
    before=$(cat demo/notebooks/*.ipynb | sha256sum)
    uv run python demo/build_notebooks.py
    after=$(cat demo/notebooks/*.ipynb | sha256sum)
    if [ "$before" != "$after" ]; then
        echo "demo/notebooks was stale - rebuilt it from demo/src, commit the result" >&2
        exit 1
    fi
    uv run python demo/test_demos.py

# Build the JupyterLite site into _site/, wheels and all.
[working-directory: 'sparql-grammar']
site: wheels
    #!/usr/bin/env bash
    set -euo pipefail
    cd demo
    # --piplite-wheels takes one wheel per flag, so build the list up
    wheels=""
    for wheel in files/*.whl; do
        wheels="$wheels --piplite-wheels $wheel"
    done
    echo "bundling:$wheels"
    uv run --with-requirements requirements-build.txt \
        jupyter lite build --contents notebooks $wheels --output-dir ../_site

# The wheels Pyodide installs: this package, and lark for the parse extra.
[working-directory: 'sparql-grammar']
wheels:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -f demo/files/*.whl
    uv run --with-requirements demo/requirements-build.txt \
        python -m build --wheel --outdir demo/files .
    uv run --with-requirements demo/requirements-build.txt --with pip \
        python -m pip download lark --no-deps --only-binary=:all: --dest demo/files
    # embed.html reads its package list from here, so the wheel version never has
    # to be spelled out in the HTML
    python3 - <<'PY'
    import json, pathlib
    files = pathlib.Path("demo/files")
    wheels = sorted(f"/files/{w.name}" for w in files.glob("*.whl"))
    (files / "pyscript.json").write_text(json.dumps({"packages": wheels}, indent=2) + "\n")
    print("pyscript.json ->", wheels)
    PY

# Serve demo/embed.html: the same library, as editable examples in a plain page.
[working-directory: 'sparql-grammar']
embed port="8001": wheels
    @echo "open http://localhost:{{ port }}/embed.html"
    python3 -m http.server {{ port }} --directory demo

# Serve a site built by `just site` at http://localhost:8000.
[working-directory: 'sparql-grammar']
serve port="8000": site
    python3 -m http.server {{ port }} --directory _site

# Drop the demo build artefacts.
[working-directory: 'sparql-grammar']
clean:
    rm -rf _site demo/files demo/.cache demo/.jupyterlite.doit.db
