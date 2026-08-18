"""Core machinery: node protocol, eq/hash contract, opt-in validation, registry."""

from __future__ import annotations

import pytest

from sparql_grammar import (
    Node,
    ValidationError,
    debug_validation,
    production,
)
from sparql_grammar._base import REGISTRY, Add


@production(rule="_TestTriple")
class _Triple(Node):
    """Not a real production - a stand-in for exercising the base class."""

    s: Node
    p: Node
    o: Node

    def render(self, add: Add) -> None:
        self.s.render(add)
        add(" ")
        self.p.render(add)
        add(" ")
        self.o.render(add)


@production(rule="_TestBlock")
class _Block(Node):
    triples: list

    def render(self, add: Add) -> None:
        for i, t in enumerate(self.triples):
            if i:
                add(" .\n")
            t.render(add)


from sparql_grammar import IRIREF, VAR1  # noqa: E402


def triple(s="s", p="http://ex/p", o="o"):
    return _Triple(VAR1(s), IRIREF(p), VAR1(o))


class TestNodeProtocol:
    def test_render_and_to_string(self):
        assert triple().to_string() == "?s <http://ex/p> ?o"

    def test_str_matches_to_string(self):
        t = triple()
        assert str(t) == t.to_string()

    def test_repr_shows_class_and_text(self):
        assert repr(VAR1("s")) == "VAR1('?s')"

    def test_slots_no_instance_dict(self):
        with pytest.raises(AttributeError):
            VAR1("s").__dict__

    def test_positional_construction(self):
        assert VAR1("s") == VAR1(value="s")


class TestEqHash:
    def test_structural_equality(self):
        assert triple() == triple()

    def test_hash_consistent_with_eq(self):
        assert hash(triple()) == hash(triple())

    def test_set_dedup(self):
        assert len({triple(), triple(), triple(o="other")}) == 2

    def test_distinct_types_not_equal(self):
        assert VAR1("x") != IRIREF("x")
        assert hash(VAR1("x")) != hash(IRIREF("x"))

    def test_nodes_with_list_fields_hashable(self):
        # the previous implementation raised TypeError: unhashable type 'list' here
        assert hash(_Block([triple()])) == hash(_Block([triple()]))

    def test_usable_as_dict_key(self):
        assert {triple(): "v"}[triple()] == "v"


class TestTraversal:
    def test_children_direct_only(self):
        t = triple()
        assert list(t.children()) == [t.s, t.p, t.o]

    def test_children_descends_into_lists(self):
        t = triple()
        assert list(_Block([t]).children()) == [t]

    def test_walk_includes_self_and_descendants(self):
        t = triple()
        assert list(t.walk()) == [t, t.s, t.p, t.o]

    def test_collect_by_type(self):
        block = _Block([triple(), triple(o="x")])
        assert len(block.collect(_Triple)) == 2
        assert len(block.collect(IRIREF)) == 2

    def test_collect_is_linear_and_deep(self):
        # 5000 triples: the old linked-list model hit RecursionError near 1000
        block = _Block([triple(o=f"o{i}") for i in range(5000)])
        assert len(block.collect(_Triple)) == 5000
        assert len(block.to_string()) > 5000


class TestValidation:
    def test_construction_does_not_validate(self):
        # wrong types, bad terminal values: constructing is always cheap and silent
        _Triple(VAR1("bad var!"), VAR1("s"), IRIREF("has space"))

    def test_terminals_level_catches_bad_value(self):
        with pytest.raises(ValidationError) as exc:
            triple(s="bad var!").validate("terminals")
        assert "VAR1" in str(exc.value)

    def test_terminals_level_ignores_type_errors(self):
        # p should be an IRIREF but is a VAR1; terminals-only doesn't type check
        _Triple(VAR1("s"), VAR1("p"), VAR1("o")).validate("terminals")

    def test_full_level_catches_type_errors(self):
        @production(rule="_TestStrict")
        class _Strict(Node):
            iri: IRIREF

            def render(self, add: Add) -> None:
                self.iri.render(add)

        with pytest.raises(ValidationError) as exc:
            _Strict(VAR1("s")).validate("full")
        assert "expected IRIREF" in str(exc.value)

    def test_full_level_accepts_correct_tree(self):
        triple().validate("full")

    def test_reports_every_error_at_once(self):
        with pytest.raises(ValidationError) as exc:
            _Block([triple(s="bad!"), triple(o="also bad!")]).validate("terminals")
        assert len(exc.value.errors) == 2

    def test_bad_level_rejected(self):
        with pytest.raises(ValueError):
            triple().validate("sloppy")

    def test_debug_validation_context_manager(self):
        with pytest.raises(ValidationError):
            with debug_validation():
                VAR1("bad var!")

    def test_debug_validation_off_after_context(self):
        VAR1("bad var!")  # silent again once the block has exited


class TestRegistry:
    def test_terminals_registered_under_production_names(self):
        assert REGISTRY["IRIREF"] is IRIREF
        assert REGISTRY["VAR1"] is VAR1

    def test_rule_attribute_set(self):
        assert IRIREF.rule == "IRIREF"

    def test_explicit_rule_name_used(self):
        assert REGISTRY["_TestTriple"] is _Triple

    def test_duplicate_registration_rejected(self):
        with pytest.raises(RuntimeError, match="duplicate"):

            @production(rule="IRIREF")
            class _Dupe(Node):
                pass
