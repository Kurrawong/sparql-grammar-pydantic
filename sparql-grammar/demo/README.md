# Browser demo

A [JupyterLite](https://jupyterlite.readthedocs.io/) site: the notebooks in
`notebooks/` run in the browser on Pyodide, with no server and nothing to install.
That works here because the library is pure Python with no runtime dependencies —
and because `lark`, needed for the `parse` extra, is pure Python too.

Published from `.github/workflows/deploy-demo.yml` on every push to the default
branch.

## Running the notebooks locally

The `piplite.install` cell is a no-op outside Pyodide, so the notebooks also run
against a normal checkout:

```shell
uv sync --all-extras
uv run --with jupyterlab jupyter lab demo/notebooks
```

`--with` layers JupyterLab over the project venv rather than adding it as a
dependency, so the kernel already imports `sparql_grammar` and `lark`.

## Runnable examples without the IDE

`embed.html` is the other shape the same library takes in a browser: a plain page
whose code blocks are editable and runnable, with no notebook and no file browser.
PyScript boots one Pyodide interpreter, a hidden `setup` editor installs the wheels
listed in `files/pyscript.json`, and every editor on the page shares that
interpreter.

```shell
just embed                         # builds the wheels, serves demo/ at :8001
```

Two constraints worth knowing before editing it:

- The editors run in a **worker**, so `window` and `document` need
  `SharedArrayBuffer`, which needs cross-origin isolation. `mini-coi.js` is vendored
  here to supply those headers from any static host, GitHub Pages included. It must
  be same-origin, so it cannot be linked from a CDN.
- micropip in a worker cannot resolve a root-relative wheel URL. The setup editor
  builds absolute URLs from `window.location.origin` rather than declaring packages
  in a PyScript `config`.

## Editing the notebooks

The demos are written as plain Python in `src/`, not as notebook JSON, so the code
can be run and tested like any other code. Cells are delimited by `# %%`, and
`# %% [markdown]` starts a prose cell.

```shell
python demo/build_notebooks.py     # src/*.py -> notebooks/*.ipynb
python demo/test_demos.py          # run every cell, offline
```

`test_demos.py` runs in CI before the site is built, so a demo that raises cannot be
published.

## Building the site locally

```shell
pip install -r demo/requirements-build.txt
python -m build --wheel --outdir demo/files .     # the wheel Pyodide installs
cd demo && jupyter lite build --contents notebooks --output-dir ../_site
python -m http.server --directory _site
```
