"""Core machinery: the node base class, the @production decorator, and the registry.

Design notes (see README for measurements):

* Nodes are ``dataclass(slots=True)`` — ~3.9x faster to construct than pydantic
  models and 40 bytes vs 80+``__dict__`` per instance.
* Rendering appends string parts through a callable instead of yielding through a
  generator chain. Generator delegation costs O(depth) per part; appending is O(1),
  which measured ~22x faster on deeply nested trees.
* Nothing is validated at construction time. Validation is opt-in, either per-tree
  via :meth:`Node.validate` or globally via :func:`set_debug_validation`.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, fields
from typing import Any, Callable, Iterator

__all__ = [
    "Node",
    "Terminal",
    "production",
    "alias",
    "REGISTRY",
    "ALIASES",
    "ValidationError",
    "set_debug_validation",
    "debug_validation",
]

#: production name -> node class. Populated by @production; used by the audit tool
#: to prove coverage against spec/sparql.bnf, and by the parser to map rules.
REGISTRY: dict[str, type["Node"]] = {}

#: production name -> union type, for productions that are a bare alternation of
#: other productions (``Var ::= VAR1 | VAR2``). Modelling these as unions rather
#: than wrapper classes is what keeps construction terse: a term goes straight
#: where the grammar allows a term, instead of being boxed one level per
#: alternation. The parser passes such rules straight through to their child.
ALIASES: dict[str, object] = {}

# Module-level flag so the __post_init__ check compiles down to one global lookup
# when validation is off, which is the default and the hot path.
_DEBUG_VALIDATION = False


class ValidationError(Exception):
    """Raised by :meth:`Node.validate` and by debug-mode construction checks."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def set_debug_validation(enabled: bool) -> None:
    """Turn construction-time validation on or off process-wide (default: off)."""
    global _DEBUG_VALIDATION
    _DEBUG_VALIDATION = bool(enabled)


class debug_validation:
    """Context manager enabling construction-time validation for a block."""

    def __enter__(self) -> None:
        self._prev = _DEBUG_VALIDATION
        set_debug_validation(True)

    def __exit__(self, *exc: object) -> None:
        set_debug_validation(self._prev)


Add = Callable[[str], None]


class Node:
    """Base class for every SPARQL grammar production.

    Subclasses are declared with :func:`production` and implement
    :meth:`render`, appending their SPARQL text through the ``add`` callable.
    """

    __slots__ = ()

    #: Set by @production to the spec production name (usually the class name).
    rule: typing.ClassVar[str] = ""

    def render(self, add: Add) -> None:  # pragma: no cover - abstract
        raise NotImplementedError(
            f"{type(self).__name__} must implement render(self, add)"
        )

    def to_string(self) -> str:
        """Serialize this node (and its children) to a SPARQL string."""
        parts: list[str] = []
        self.render(parts.append)
        return "".join(parts)

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.to_string()!r})"

    def __hash__(self) -> int:
        # Structural, and consistent with the dataclass-generated __eq__: equal
        # trees render identically. Keeps every node usable in sets and dict keys,
        # which the pydantic version could not manage (most classes were unhashable).
        return hash((type(self).__name__, self.to_string()))

    # -- traversal ---------------------------------------------------------

    def children(self) -> Iterator["Node"]:
        """Yield the direct child nodes held by this node's fields."""
        for f in fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if isinstance(value, Node):
                yield value
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, Node):
                        yield item

    def walk(self) -> Iterator["Node"]:
        """Yield this node and every descendant, depth first."""
        yield self
        for child in self.children():
            yield from child.walk()

    def collect(self, node_type: type) -> list["Node"]:
        """Collect every descendant of ``node_type`` (self included if it matches).

        Replaces the old ``collect_triples``: linear, ordered, and generic.
        """
        return [n for n in self.walk() if isinstance(n, node_type)]

    # -- opt-in validation -------------------------------------------------

    def validate(self, level: str = "full") -> None:
        """Validate this tree. ``level`` is ``"terminals"`` or ``"full"``.

        ``terminals`` checks terminal values against their spec regex.
        ``full`` additionally type-checks every field against its annotation.
        Raises :class:`ValidationError` listing every problem found.
        """
        if level not in ("terminals", "full"):
            raise ValueError("level must be 'terminals' or 'full'")
        errors: list[str] = []
        for node in self.walk():
            errors.extend(node._check(level))
        if errors:
            raise ValidationError(errors)

    def _check(self, level: str) -> list[str]:
        """Per-node validation hook. Terminals override to add regex checks."""
        if level != "full":
            return []
        return _check_field_types(self)


def _resolve_hints(cls: type) -> dict[str, Any]:
    """Resolve (and cache) a class's annotations, tolerating forward references."""
    cached = cls.__dict__.get("_hints_cache")
    if cached is not None:
        return cached
    try:
        hints = typing.get_type_hints(cls)
    except Exception:  # unresolvable forward ref - skip type checking for this class
        hints = {}
    try:
        cls._hints_cache = hints  # type: ignore[attr-defined]
    except (AttributeError, TypeError):  # pragma: no cover - slotted edge case
        pass
    return hints


def _permitted(hint: Any) -> tuple[type, ...] | None:
    """Flatten a type hint into a tuple of classes usable with isinstance()."""
    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is type(int | str):
        out: list[type] = []
        for arg in typing.get_args(hint):
            if arg is type(None):
                out.append(type(None))
            elif isinstance(arg, type):
                out.append(arg)
            elif typing.get_origin(arg) in (list, tuple):
                out.append(typing.get_origin(arg))  # type: ignore[arg-type]
            else:
                return None  # something exotic - don't guess
        return tuple(out)
    if origin in (list, tuple):
        return (origin,)  # type: ignore[return-value]
    if isinstance(hint, type):
        return (hint,)
    return None


def _check_field_types(node: Node) -> list[str]:
    hints = _resolve_hints(type(node))
    if not hints:
        return []
    errors: list[str] = []
    name = type(node).__name__
    for f in fields(node):  # type: ignore[arg-type]
        if f.name not in hints:
            continue
        permitted = _permitted(hints[f.name])
        if permitted is None:
            continue
        value = getattr(node, f.name)
        if not isinstance(value, permitted):
            expected = "|".join(t.__name__ for t in permitted)
            errors.append(
                f"{name}.{f.name}: expected {expected}, got {type(value).__name__}"
            )
    return errors


def production(cls: type | None = None, /, *, rule: str | None = None):
    """Declare a SPARQL grammar production.

    Applies ``dataclass(slots=True)``, restores the structural ``__hash__`` that
    ``dataclass(eq=True)`` would otherwise remove, and registers the class under
    its spec production name.
    """

    def wrap(target: type) -> type:
        name = rule or target.__name__
        target.rule = name  # type: ignore[attr-defined]
        # Must be attached before dataclass() runs: the generated __init__ only
        # calls __post_init__ if the attribute exists at class-creation time.
        if not hasattr(target, "__post_init__"):
            target.__post_init__ = _post_init  # type: ignore[attr-defined]
        dc = dataclass(eq=True, slots=True, repr=False)(target)
        dc.__hash__ = Node.__hash__  # type: ignore[assignment]
        _repoint_super_cells(target, dc)
        if name in REGISTRY and REGISTRY[name] is not dc:
            raise RuntimeError(f"duplicate production registration: {name}")
        REGISTRY[name] = dc
        return dc

    return wrap if cls is None else wrap(cls)


def alias(name: str, union: object) -> object:
    """Register a production that is a bare alternation of other productions.

    ``VarOrTerm ::= Var | iri | RDFLiteral | ...`` adds no syntax of its own, so it
    is represented as a union type rather than a node class. Registering it here
    keeps the audit tool honest: the production is accounted for, and its Python
    representation is recorded.
    """
    if name in ALIASES and ALIASES[name] is not union:
        raise RuntimeError(f"duplicate alias registration: {name}")
    if name in REGISTRY:
        raise RuntimeError(f"{name} is already registered as a node class")
    ALIASES[name] = union
    return union


def _repoint_super_cells(old: type, new: type) -> None:
    """Make zero-argument ``super()`` work in a slotted dataclass.

    ``dataclass(slots=True)`` cannot add ``__slots__`` to an existing class, so it
    builds and returns a *new* class. Methods defined in the original class body
    keep a ``__class__`` closure cell pointing at the original, and zero-argument
    ``super()`` reads that cell - so it raises ``TypeError: super(type, obj): obj
    must be an instance or subtype of type`` for instances of the new class.
    Repointing the cell fixes every method at once, so subclasses can call
    ``super()`` normally instead of naming a base class explicitly.
    """
    if old is new:
        return
    for member in vars(new).values():
        function = getattr(member, "__func__", member)
        if not isinstance(function, types.FunctionType):
            continue
        for cell in function.__closure__ or ():
            try:
                if cell.cell_contents is old:
                    cell.cell_contents = new
            except ValueError:  # empty cell
                continue


def _post_init(self: Node) -> None:
    if _DEBUG_VALIDATION:
        errors = self._check("full")
        if errors:
            raise ValidationError(errors)


class Terminal(Node):
    """Base for terminal productions: a single ``value`` plus surface syntax.

    ``value`` holds the *inner* text, not the surface form: ``VAR1("s")`` renders
    ``?s`` and ``IRIREF("http://x")`` renders ``<http://x>``.
    """

    __slots__ = ()

    #: compiled spec regex for ``value``; set by subclasses
    pattern: typing.ClassVar[Any] = None

    value: str

    def render(self, add: Add) -> None:
        add(self.value)

    def _check(self, level: str) -> list[str]:
        errors = super()._check(level)
        pattern = type(self).pattern
        if pattern is not None and not pattern.fullmatch(self.value):
            errors.append(
                f"{type(self).__name__}: {self.value!r} does not match {type(self).rule}"
            )
        return errors
