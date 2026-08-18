"""sparql-grammar: typed, dependency-free Python objects for the SPARQL 1.2 grammar.

One class per production of the W3C grammar (vendored at ``spec/sparql.bnf``), which
renders itself back to SPARQL text. No pydantic, no runtime dependencies.
"""

from ._base import (
    ALIASES,
    Node,
    Terminal,
    ValidationError,
    alias,
    debug_validation,
    production,
    set_debug_validation,
    REGISTRY,
)
from .terminals import *  # noqa: F401,F403
from .terminals import __all__ as _terminals_all
from .terms import *  # noqa: F401,F403
from .terms import __all__ as _terms_all
from .paths import *  # noqa: F401,F403
from .paths import __all__ as _paths_all
from .expressions import *  # noqa: F401,F403
from .expressions import __all__ as _expressions_all
from .grammar import *  # noqa: F401,F403
from .grammar import __all__ as _grammar_all
from .update import *  # noqa: F401,F403
from .update import __all__ as _update_all
from . import helpers
from .helpers import *  # noqa: F401,F403
from .helpers import __all__ as _helpers_all

__version__ = "0.1.0.dev0"

__all__ = [
    "Node",
    "Terminal",
    "ValidationError",
    "alias",
    "debug_validation",
    "production",
    "set_debug_validation",
    "ALIASES",
    "REGISTRY",
    "__version__",
    *_terminals_all,
    *_terms_all,
    *_paths_all,
    *_expressions_all,
    *_grammar_all,
    *_update_all,
    *_helpers_all,
    "helpers",
]
