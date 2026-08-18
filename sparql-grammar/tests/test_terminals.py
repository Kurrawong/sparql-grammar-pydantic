"""Terminal productions: rendering, opt-in regex validation, convenience parsing."""

from __future__ import annotations

import pytest

from sparql_grammar import (
    ANON,
    BLANK_NODE_LABEL,
    DECIMAL,
    DECIMAL_NEGATIVE,
    DOUBLE,
    DOUBLE_POSITIVE,
    INTEGER,
    INTEGER_NEGATIVE,
    INTEGER_POSITIVE,
    IRIREF,
    LANG_DIR,
    NIL,
    PNAME_LN,
    PNAME_NS,
    STRING_LITERAL1,
    STRING_LITERAL2,
    STRING_LITERAL_LONG1,
    STRING_LITERAL_LONG2,
    VAR1,
    VAR2,
    ValidationError,
)


class TestRendering:
    """``value`` holds inner text; render() adds the surface syntax."""

    @pytest.mark.parametrize(
        "node,expected",
        [
            (IRIREF("http://ex/p"), "<http://ex/p>"),
            (PNAME_NS("skos"), "skos:"),
            (PNAME_NS(), ":"),
            (PNAME_LN("skos:prefLabel"), "skos:prefLabel"),
            (BLANK_NODE_LABEL("b1"), "_:b1"),
            (VAR1("s"), "?s"),
            (VAR2("s"), "$s"),
            (LANG_DIR("en"), "@en"),
            (LANG_DIR("ar--rtl"), "@ar--rtl"),
            (INTEGER("42"), "42"),
            (DECIMAL("3.14"), "3.14"),
            (DOUBLE("1.5e10"), "1.5e10"),
            (INTEGER_POSITIVE("42"), "+42"),
            (INTEGER_NEGATIVE("42"), "-42"),
            (DECIMAL_NEGATIVE("3.14"), "-3.14"),
            (DOUBLE_POSITIVE("1.5e10"), "+1.5e10"),
            (STRING_LITERAL1("hi"), "'hi'"),
            (STRING_LITERAL2("hi"), '"hi"'),
            (STRING_LITERAL_LONG1("hi"), "'''hi'''"),
            (STRING_LITERAL_LONG2("hi"), '"""hi"""'),
            (NIL(), "()"),
            (ANON(), "[]"),
        ],
    )
    def test_renders(self, node, expected):
        assert node.to_string() == expected


class TestValidation:
    @pytest.mark.parametrize(
        "node",
        [
            IRIREF("http://www.w3.org/2004/02/skos/core#Concept"),
            IRIREF("urn:uuid:12345"),
            IRIREF(""),
            IRIREF(r"http://ex/é"),
            PNAME_NS("ex"),
            PNAME_NS(""),
            PNAME_LN("ex:local"),
            PNAME_LN("ex:my-Local.name"),
            PNAME_LN(":noPrefix"),
            VAR1("s"),
            VAR1("_private"),
            VAR1("v123"),
            BLANK_NODE_LABEL("b1"),
            BLANK_NODE_LABEL("has.dot.inside"),
            LANG_DIR("en"),
            LANG_DIR("en-AU"),
            LANG_DIR("ar--rtl"),
            INTEGER("0"),
            DECIMAL(".5"),
            DOUBLE("1e10"),
            DOUBLE(".5E-3"),
            STRING_LITERAL2("with \\\" escape"),
        ],
    )
    def test_accepts_valid(self, node):
        node.validate("terminals")

    @pytest.mark.parametrize(
        "node",
        [
            IRIREF("has space"),
            IRIREF("angle<bracket"),
            IRIREF('quote"inside'),
            PNAME_NS("0startsWithDigit"),
            VAR1("bad var!"),
            VAR1(""),
            VAR1("-leadingHyphen"),
            BLANK_NODE_LABEL("ends.with.dot."),
            LANG_DIR("en_AU"),
            LANG_DIR("123"),
            INTEGER("4.5"),
            INTEGER("-4"),
            DECIMAL("42"),
            DOUBLE("42"),
        ],
    )
    def test_rejects_invalid(self, node):
        with pytest.raises(ValidationError):
            node.validate("terminals")


class TestRegressions:
    """Cases the previous implementation got wrong."""

    def test_iriref_accepts_ordinary_iris(self):
        # the old IRIREF regex double-escaped its \\u ranges, excluding 0x30-0x5C,
        # which rejected every IRI containing a digit, colon or capital letter
        for iri in [
            "http://example.com/thing",
            "https://linked.data.gov.au/def/borehole",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        ]:
            IRIREF(iri).validate("terminals")

    def test_prefixed_name_patterns_have_correct_precedence(self):
        # PN_CHARS_BASE was an unparenthesised alternation, so every derived
        # pattern (PN_PREFIX, PNAME_NS, PNAME_LN, VARNAME, ...) mis-parsed
        PNAME_NS("ex").validate("terminals")
        PNAME_LN("ex:Concept").validate("terminals")
        VAR1("focus_node").validate("terminals")

    def test_every_terminal_renders(self):
        # the old Terminal base did `raise self.value`, so any terminal that did
        # not override render() blew up with a TypeError
        from sparql_grammar import ECHAR, EXPONENT, HEX, PERCENT, UCHAR, WS

        assert HEX("A").to_string() == "A"
        assert PERCENT("%20").to_string() == "%20"
        assert EXPONENT("e10").to_string() == "e10"
        assert ECHAR("\\n").to_string() == "\\n"
        assert UCHAR("\\u00e9").to_string() == "\\u00e9"
        assert WS().to_string() == " "

    def test_lang_dir_renders_single_at_sign(self):
        # the old LANGTAG regex required the '@' in value and render() added
        # another, producing '@@en'
        assert LANG_DIR("en").to_string() == "@en"


class TestFromString:
    def test_iriref_accepts_both_forms(self):
        assert IRIREF.from_string("<http://x>") == IRIREF("http://x")
        assert IRIREF.from_string("http://x") == IRIREF("http://x")

    def test_var_strips_sigil(self):
        assert VAR1.from_string("?s") == VAR1("s")
        assert VAR2.from_string("$s") == VAR2("s")

    def test_lang_dir_strips_at(self):
        assert LANG_DIR.from_string("@en") == LANG_DIR("en")

    def test_pname_ns_strips_colon(self):
        assert PNAME_NS.from_string("ex:") == PNAME_NS("ex")

    def test_blank_node_label_strips_prefix(self):
        assert BLANK_NODE_LABEL.from_string("_:b1") == BLANK_NODE_LABEL("b1")

    def test_integer_from_int(self):
        assert INTEGER.from_int(42) == INTEGER("42")


class TestPnameParts:
    def test_prefix_and_local(self):
        p = PNAME_LN("skos:prefLabel")
        assert (p.prefix, p.local) == ("skos", "prefLabel")

    def test_from_parts(self):
        assert PNAME_LN.from_parts("skos", "prefLabel") == PNAME_LN("skos:prefLabel")


class TestCoverage:
    def test_all_terminal_productions_implemented(self):
        """Every @terminals production in the vendored grammar has a class."""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from sparql_grammar._base import REGISTRY
        from tools.bnf import parse_bnf

        missing = [
            p.name for p in parse_bnf() if p.terminal and p.name not in REGISTRY
        ]
        assert missing == []
