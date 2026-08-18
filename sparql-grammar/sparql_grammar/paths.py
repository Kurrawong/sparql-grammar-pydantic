"""Property path productions.

Paths are the most nesting-heavy corner of the grammar: a bare ``?s <p> ?o`` needs
``Path -> PathAlternative -> PathSequence -> PathEltOrInverse -> PathElt ->
PathPrimary`` before the predicate appears. The productions below stay faithful to
that structure, and the classmethods on :class:`PathAlternative` (``iri``, ``inverse``,
``seq``, ``alt``, ``mod``) build the common shapes in one call so callers never have
to spell the tower out.
"""

from __future__ import annotations

from enum import Enum
from typing import Union

from ._base import Add, Node, alias, production
from .terminals import PNAME_LN, PNAME_NS
from .terms import IRI

__all__ = [
    "Path",
    "PathAlternative",
    "PathSequence",
    "PathElt",
    "PathEltOrInverse",
    "PathMod",
    "PathPrimary",
    "PathNegatedPropertySet",
    "PathOneInPropertySet",
    "RDF_TYPE",
]

#: The ``a`` shorthand for ``rdf:type``, usable wherever a path primary or verb is.
RDF_TYPE = "a"

IRIish = Union[IRI, PNAME_LN, PNAME_NS]


class PathMod(str, Enum):
    """PathMod ::= '?' | '*' | '+'"""

    ZERO_OR_ONE = "?"
    ZERO_OR_MORE = "*"
    ONE_OR_MORE = "+"

    def render(self, add: Add) -> None:
        add(self.value)


@production(rule="PathPrimary")
class PathPrimary(Node):
    """PathPrimary ::= iri | 'a' | '!' PathNegatedPropertySet | '(' Path ')'

    ``value`` is an IRI, the string ``"a"``, a negated property set, or a nested
    path (which is rendered parenthesised).
    """

    value: object

    def render(self, add: Add) -> None:
        value = self.value
        if value == RDF_TYPE:
            add("a")
        elif isinstance(value, PathNegatedPropertySet):
            add("!")
            value.render(add)
        elif isinstance(value, PathAlternative):
            add("(")
            value.render(add)
            add(")")
        else:
            value.render(add)


@production(rule="PathElt")
class PathElt(Node):
    """PathElt ::= PathPrimary PathMod?"""

    path_primary: PathPrimary
    path_mod: PathMod | None = None

    def render(self, add: Add) -> None:
        self.path_primary.render(add)
        if self.path_mod is not None:
            add(self.path_mod.value)


@production(rule="PathEltOrInverse")
class PathEltOrInverse(Node):
    """PathEltOrInverse ::= PathElt | '^' PathElt"""

    path_elt: PathElt
    inverse: bool = False

    def render(self, add: Add) -> None:
        if self.inverse:
            add("^")
        self.path_elt.render(add)


@production(rule="PathSequence")
class PathSequence(Node):
    """PathSequence ::= PathEltOrInverse ( '/' PathEltOrInverse )*"""

    list_path_elt_or_inverse: list[PathEltOrInverse]

    def render(self, add: Add) -> None:
        for i, elt in enumerate(self.list_path_elt_or_inverse):
            if i:
                add("/")
            elt.render(add)


@production(rule="PathAlternative")
class PathAlternative(Node):
    """PathAlternative ::= PathSequence ( '|' PathSequence )*

    The classmethods here are the intended entry points for building paths.
    """

    sequence_paths: list[PathSequence]

    def render(self, add: Add) -> None:
        for i, seq in enumerate(self.sequence_paths):
            if i:
                add("|")
            seq.render(add)

    # -- builders ----------------------------------------------------------

    @staticmethod
    def _elt(step: object, inverse: bool = False, mod: PathMod | None = None) -> PathEltOrInverse:
        """Wrap one step (IRI, ``"a"``, path, or an already-built element)."""
        if isinstance(step, PathEltOrInverse):
            return step
        if isinstance(step, PathElt):
            return PathEltOrInverse(step, inverse)
        primary = step if isinstance(step, PathPrimary) else PathPrimary(step)
        return PathEltOrInverse(PathElt(primary, mod), inverse)

    @classmethod
    def iri(cls, predicate: IRIish | str, mod: PathMod | None = None) -> PathAlternative:
        """``<p>`` - a single predicate. Pass ``"a"`` for ``rdf:type``."""
        return cls([PathSequence([cls._elt(predicate, mod=mod)])])

    @classmethod
    def inverse(cls, predicate: IRIish | str) -> PathAlternative:
        """``^<p>``"""
        return cls([PathSequence([cls._elt(predicate, inverse=True)])])

    @classmethod
    def seq(cls, *steps: object) -> PathAlternative:
        """``<p1>/<p2>/...`` - pass ``PathEltOrInverse`` for inverse steps."""
        return cls([PathSequence([cls._elt(s) for s in steps])])

    @classmethod
    def alt(cls, *steps: object) -> PathAlternative:
        """``<p1>|<p2>|...``

        A step may itself be a ``PathAlternative`` (its sequences are merged) or a
        ``PathSequence``, so alternatives of sequences compose.
        """
        sequences: list[PathSequence] = []
        for step in steps:
            if isinstance(step, PathAlternative):
                sequences.extend(step.sequence_paths)
            elif isinstance(step, PathSequence):
                sequences.append(step)
            else:
                sequences.append(PathSequence([cls._elt(step)]))
        return cls(sequences)

    @classmethod
    def mod(cls, predicate: IRIish | str, mod: PathMod | str) -> PathAlternative:
        """``<p>*``, ``<p>+`` or ``<p>?``"""
        return cls.iri(predicate, PathMod(mod))

    @classmethod
    def negated(cls, *predicates: object) -> PathAlternative:
        """``!(<p1>|<p2>)`` - a negated property set."""
        one_ins = [
            p if isinstance(p, PathOneInPropertySet) else PathOneInPropertySet(p)
            for p in predicates
        ]
        return cls(
            [PathSequence([cls._elt(PathPrimary(PathNegatedPropertySet(one_ins)))])]
        )


@production(rule="PathOneInPropertySet")
class PathOneInPropertySet(Node):
    """PathOneInPropertySet ::= iri | 'a' | '^' ( iri | 'a' )"""

    value: object
    inverse: bool = False

    def render(self, add: Add) -> None:
        if self.inverse:
            add("^")
        if self.value == RDF_TYPE:
            add("a")
        else:
            self.value.render(add)


@production(rule="PathNegatedPropertySet")
class PathNegatedPropertySet(Node):
    """PathNegatedPropertySet ::= PathOneInPropertySet | '(' ( PathOneInPropertySet ( '|' PathOneInPropertySet )* )? ')'

    A single entry renders bare; anything else (including empty) renders
    parenthesised, as the grammar requires.
    """

    paths: list[PathOneInPropertySet]

    def render(self, add: Add) -> None:
        if len(self.paths) == 1:
            self.paths[0].render(add)
            return
        add("(")
        for i, path in enumerate(self.paths):
            if i:
                add("|")
            path.render(add)
        add(")")


#: Path ::= PathAlternative
Path = alias("Path", PathAlternative)
