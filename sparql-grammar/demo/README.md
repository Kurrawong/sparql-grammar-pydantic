# Browser demo

A [JupyterLite](https://jupyterlite.readthedocs.io/) site: the notebooks in
`notebooks/` run in the browser on Pyodide, with no server and nothing to install.
That works here because the library is pure Python with no runtime dependencies —
and because `lark`, needed for the `parse` extra, is pure Python too.

Published from `.github/workflows/deploy-demo.yml` on every push to the default
branch.

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
