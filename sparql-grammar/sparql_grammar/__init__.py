"""sparql-grammar: typed, dependency-free Python objects for the SPARQL 1.2 grammar.

One class per production of the W3C grammar (vendored at ``spec/sparql.bnf``), which
renders itself back to SPARQL text. No pydantic, no runtime dependencies.
"""

from ._base import (
    Node,
    Terminal,
    ValidationError,
    debug_validation,
    production,
    set_debug_validation,
    REGISTRY,
)
from .terminals import *  # noqa: F401,F403
from .terminals import __all__ as _terminals_all

__version__ = "0.1.0.dev0"

__all__ = [
    "Node",
    "Terminal",
    "ValidationError",
    "debug_validation",
    "production",
    "set_debug_validation",
    "REGISTRY",
    "__version__",
    *_terminals_all,
]
