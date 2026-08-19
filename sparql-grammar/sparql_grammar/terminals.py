"""Terminal productions of the SPARQL 1.2 grammar (the ``@terminals`` section).

Each terminal stores its *inner* text in ``value`` and adds its surface syntax when
rendering: ``VAR1("s")`` renders ``?s``, ``IRIREF("http://x")`` renders ``<http://x>``,
``STRING_LITERAL2("hi")`` renders ``"hi"``.

Regexes are composed bottom-up from the spec productions, mirroring the structure of
the grammar so each one can be checked against the .bnf line quoted in its docstring.
They are only applied when validation is requested (see ``Node.validate``).
"""

from __future__ import annotations

import re
from typing import ClassVar

from ._base import Add, Node, Terminal, production

__all__ = [
    "escape_string",
    "HEX", "PERCENT", "PN_LOCAL_ESC", "PLX", "PN_CHARS_BASE", "PN_CHARS_U",
    "PN_CHARS", "PN_PREFIX", "PN_LOCAL", "VARNAME", "WS", "ECHAR", "UCHAR",
    "IRIREF", "PNAME_NS", "PNAME_LN", "BLANK_NODE_LABEL", "VAR1", "VAR2",
    "LANG_DIR", "INTEGER", "DECIMAL", "DOUBLE", "EXPONENT",
    "INTEGER_POSITIVE", "DECIMAL_POSITIVE", "DOUBLE_POSITIVE",
    "INTEGER_NEGATIVE", "DECIMAL_NEGATIVE", "DOUBLE_NEGATIVE",
    "STRING_LITERAL1", "STRING_LITERAL2",
    "STRING_LITERAL_LONG1", "STRING_LITERAL_LONG2",
    "NIL", "ANON",
]

# ---------------------------------------------------------------------------
# Regex fragments, composed in spec order.
#
# Every fragment is a self-contained group, so fragments can be concatenated or
# alternated without precedence surprises. Character ranges use \uXXXX / \xXX
# escapes, which ``re`` interprets natively - writing them as literal characters
# or double-escaping them are the two ways this has gone wrong before.
# ---------------------------------------------------------------------------

HEX_RE = r"[0-9A-Fa-f]"
PERCENT_RE = rf"(?:%{HEX_RE}{HEX_RE})"
PN_LOCAL_ESC_RE = r"(?:\\[_~.\-!$&'()*+,;=/?#@%])"
PLX_RE = rf"(?:{PERCENT_RE}|{PN_LOCAL_ESC_RE})"

# Expressed as one character class rather than an alternation: the previous
# implementation alternated these without grouping, which broke precedence in
# every pattern derived from it.
PN_CHARS_BASE_CC = (
    r"A-Za-z"
    r"À-ÖØ-öø-˿"
    r"Ͱ-ͽͿ-῿"
    r"‌-‍⁰-↏Ⰰ-⿯"
    r"、-퟿豈-﷏ﷰ-�"
    r"\U00010000-\U000EFFFF"
)
PN_CHARS_BASE_RE = rf"[{PN_CHARS_BASE_CC}]"
PN_CHARS_U_CC = PN_CHARS_BASE_CC + r"_"
PN_CHARS_U_RE = rf"[{PN_CHARS_U_CC}]"
PN_CHARS_EXTRA_CC = r"\-0-9·̀-ͯ‿-⁀"
PN_CHARS_CC = PN_CHARS_U_CC + PN_CHARS_EXTRA_CC
PN_CHARS_RE = rf"[{PN_CHARS_CC}]"

VARNAME_RE = (
    rf"(?:[{PN_CHARS_U_CC}0-9]"
    rf"[{PN_CHARS_U_CC}0-9·̀-ͯ‿-⁀]*)"
)
PN_PREFIX_RE = rf"(?:{PN_CHARS_BASE_RE}(?:(?:{PN_CHARS_RE}|\.)*{PN_CHARS_RE})?)"
PN_LOCAL_RE = (
    rf"(?:(?:[{PN_CHARS_U_CC}:0-9]|{PLX_RE})"
    rf"(?:(?:{PN_CHARS_RE}|[.:]|{PLX_RE})*(?:{PN_CHARS_RE}|:|{PLX_RE}))?)"
)

WS_RE = r"[\x20\x09\x0D\x0A]"
ECHAR_RE = r"(?:\\[tbnrf\"'\\])"
UCHAR_RE = rf"(?:\\u{HEX_RE}{{4}}|\\U{HEX_RE}{{8}})"

# Inner text only - the surrounding delimiters are added by render().
IRIREF_INNER_RE = rf"(?:[^<>\"{{}}|^`\\\x00-\x20]|{UCHAR_RE})*"
BLANK_NODE_LABEL_INNER_RE = (
    rf"(?:[{PN_CHARS_U_CC}0-9](?:(?:{PN_CHARS_RE}|\.)*{PN_CHARS_RE})?)"
)
LANG_DIR_INNER_RE = r"(?:[a-zA-Z]+(?:-[a-zA-Z0-9]+)*(?:--[a-zA-Z]+)?)"

INTEGER_RE = r"[0-9]+"
DECIMAL_RE = r"(?:[0-9]*\.[0-9]+)"
EXPONENT_RE = r"(?:[eE][+-]?[0-9]+)"
DOUBLE_RE = rf"(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+){EXPONENT_RE})"

STRING_LITERAL1_INNER_RE = rf"(?:[^\x27\x5C\x0A\x0D]|{ECHAR_RE}|{UCHAR_RE})*"
STRING_LITERAL2_INNER_RE = rf"(?:[^\x22\x5C\x0A\x0D]|{ECHAR_RE}|{UCHAR_RE})*"
STRING_LITERAL_LONG1_INNER_RE = rf"(?:(?:\x27|\x27\x27)?(?:[^\x27\x5C]|{ECHAR_RE}|{UCHAR_RE}))*"
STRING_LITERAL_LONG2_INNER_RE = rf"(?:(?:\x22|\x22\x22)?(?:[^\x22\x5C]|{ECHAR_RE}|{UCHAR_RE}))*"


def _c(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


#: Characters a double- or single-quoted string literal cannot carry verbatim.
_MUST_ESCAPE = '\\"\'\n\r\t'
_ESCAPES = str.maketrans(
    {"\\": "\\\\", '"': '\\"', "'": "\\'", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
)


def escape_string(text: str) -> str:
    """Escape text so it is safe inside a quoted SPARQL string literal.

    This is what stops an untrusted value from closing its own literal and adding
    clauses to the query. It is applied automatically when a literal is given plain
    text, so the safe behaviour is the default rather than something to remember.

    The membership test first is a fast path: the overwhelming majority of values
    contain nothing to escape, and translate() on a long string is not free.
    """
    if not any(character in text for character in _MUST_ESCAPE):
        return text
    return text.translate(_ESCAPES)


# ---------------------------------------------------------------------------
# Sub-terminals. These are real spec productions, registered for completeness;
# in practice they are consumed through the composed regexes above.
# ---------------------------------------------------------------------------


@production
class HEX(Terminal):
    """HEX ::= [0-9] | [A-F] | [a-f]"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(HEX_RE)


@production
class PERCENT(Terminal):
    """PERCENT ::= '%' HEX HEX"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PERCENT_RE)


@production
class PN_LOCAL_ESC(Terminal):
    r"""PN_LOCAL_ESC ::= '\' ( '_' | '~' | '.' | '-' | '!' | '$' | '&' | "'" | '(' | ')' | '*' | '+' | ',' | ';' | '=' | '/' | '?' | '#' | '@' | '%' )"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PN_LOCAL_ESC_RE)


@production
class PLX(Terminal):
    """PLX ::= PERCENT | PN_LOCAL_ESC"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PLX_RE)


@production
class PN_CHARS_BASE(Terminal):
    """PN_CHARS_BASE ::= [A-Z] | [a-z] | [#x00C0-#x00D6] | ... | [#x10000-#xEFFFF]"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PN_CHARS_BASE_RE)


@production
class PN_CHARS_U(Terminal):
    """PN_CHARS_U ::= PN_CHARS_BASE | '_'"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PN_CHARS_U_RE)


@production
class PN_CHARS(Terminal):
    """PN_CHARS ::= PN_CHARS_U | '-' | [0-9] | #x00B7 | [#x0300-#x036F] | [#x203F-#x2040]"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PN_CHARS_RE)


@production
class PN_PREFIX(Terminal):
    """PN_PREFIX ::= PN_CHARS_BASE ((PN_CHARS|'.')* PN_CHARS)?"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PN_PREFIX_RE)


@production
class PN_LOCAL(Terminal):
    """PN_LOCAL ::= (PN_CHARS_U | ':' | [0-9] | PLX ) ((PN_CHARS | '.' | ':' | PLX)* (PN_CHARS | ':' | PLX) )?"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(PN_LOCAL_RE)


@production
class VARNAME(Terminal):
    """VARNAME ::= ( PN_CHARS_U | [0-9] ) ( PN_CHARS_U | [0-9] | #x00B7 | [#x0300-#x036F] | [#x203F-#x2040] )*"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(VARNAME_RE)


@production
class WS(Terminal):
    """WS ::= #x20 | #x9 | #xD | #xA"""

    value: str = " "
    pattern: ClassVar[re.Pattern[str]] = _c(WS_RE)


@production
class ECHAR(Terminal):
    r"""ECHAR ::= '\' [tbnrf\"']"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(ECHAR_RE)


@production
class UCHAR(Terminal):
    r"""UCHAR ::= ('\u' HEX HEX HEX HEX) | ('\U' HEX HEX HEX HEX HEX HEX HEX HEX)"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(UCHAR_RE)


# ---------------------------------------------------------------------------
# Terminals used directly when building queries.
# ---------------------------------------------------------------------------


@production
class IRIREF(Terminal):
    r"""IRIREF ::= '<' ( [^<>"{}|^`\]-[#x00-#x20] | UCHAR ) * '>'

    ``value`` is the IRI itself, without angle brackets.
    """

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(IRIREF_INNER_RE)

    def render(self, add: Add) -> None:
        add("<")
        add(self.value)
        add(">")

    @classmethod
    def from_string(cls, text: str) -> IRIREF:
        """Accept either ``<http://x>`` or ``http://x``."""
        text = text.strip()
        if text.startswith("<") and text.endswith(">"):
            text = text[1:-1]
        return cls(text)


@production
class PNAME_NS(Terminal):
    """PNAME_NS ::= PN_PREFIX? ':'

    ``value`` is the prefix without the colon (empty for the default prefix).
    """

    value: str = ""
    pattern: ClassVar[re.Pattern[str]] = _c(rf"(?:{PN_PREFIX_RE})?")

    def render(self, add: Add) -> None:
        add(self.value)
        add(":")

    @classmethod
    def from_string(cls, text: str) -> PNAME_NS:
        return cls(text[:-1] if text.endswith(":") else text)


@production
class PNAME_LN(Terminal):
    """PNAME_LN ::= PNAME_NS PN_LOCAL

    ``value`` is the whole prefixed name, e.g. ``skos:prefLabel``.
    """

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(rf"(?:{PN_PREFIX_RE})?:{PN_LOCAL_RE}")

    @classmethod
    def from_parts(cls, prefix: str, local: str) -> PNAME_LN:
        return cls(f"{prefix}:{local}")

    @property
    def prefix(self) -> str:
        return self.value.split(":", 1)[0]

    @property
    def local(self) -> str:
        return self.value.split(":", 1)[1]


@production
class BLANK_NODE_LABEL(Terminal):
    """BLANK_NODE_LABEL ::= '_:' ( PN_CHARS_U | [0-9] ) ((PN_CHARS|'.')* PN_CHARS)?

    ``value`` is the label without the ``_:`` prefix.
    """

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(BLANK_NODE_LABEL_INNER_RE)

    def render(self, add: Add) -> None:
        add("_:")
        add(self.value)

    @classmethod
    def from_string(cls, text: str) -> BLANK_NODE_LABEL:
        return cls(text[2:] if text.startswith("_:") else text)


@production
class VAR1(Terminal):
    """VAR1 ::= '?' VARNAME"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(VARNAME_RE)

    def render(self, add: Add) -> None:
        add("?")
        add(self.value)

    @classmethod
    def from_string(cls, text: str) -> VAR1:
        return cls(text.lstrip("?$"))


@production
class VAR2(Terminal):
    """VAR2 ::= '$' VARNAME"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(VARNAME_RE)

    def render(self, add: Add) -> None:
        add("$")
        add(self.value)

    @classmethod
    def from_string(cls, text: str) -> VAR2:
        return cls(text.lstrip("?$"))


@production
class LANG_DIR(Terminal):
    """LANG_DIR ::= '@' [a-zA-Z]+ ('-' [a-zA-Z0-9]+)* ('--' [a-zA-Z]+)?

    New in SPARQL 1.2 (supersedes LANGTAG): carries an optional base direction,
    e.g. ``@en``, ``@en-AU``, ``@ar--rtl``. ``value`` excludes the ``@``.
    """

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(LANG_DIR_INNER_RE)

    def render(self, add: Add) -> None:
        add("@")
        add(self.value)

    @classmethod
    def from_string(cls, text: str) -> LANG_DIR:
        return cls(text[1:] if text.startswith("@") else text)


@production
class INTEGER(Terminal):
    """INTEGER ::= [0-9]+"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(INTEGER_RE)

    @classmethod
    def from_int(cls, number: int) -> INTEGER:
        return cls(str(number))


@production
class DECIMAL(Terminal):
    """DECIMAL ::= [0-9]* '.' [0-9]+"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(DECIMAL_RE)


@production
class DOUBLE(Terminal):
    """DOUBLE ::= ( ([0-9]+ ('.'[0-9]*)? ) | ( '.' ([0-9])+ ) ) EXPONENT"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(DOUBLE_RE)


@production
class EXPONENT(Terminal):
    """EXPONENT ::= [eE] [+-]? [0-9]+"""

    value: str
    pattern: ClassVar[re.Pattern[str]] = _c(EXPONENT_RE)


class _Signed(Terminal):
    """Shared rendering for the signed numeric terminals."""

    __slots__ = ()
    sign: ClassVar[str] = ""

    def render(self, add: Add) -> None:
        add(type(self).sign)
        add(self.value)


@production
class INTEGER_POSITIVE(_Signed):
    """INTEGER_POSITIVE ::= '+' INTEGER"""

    value: str
    sign: ClassVar[str] = "+"
    pattern: ClassVar[re.Pattern[str]] = _c(INTEGER_RE)


@production
class DECIMAL_POSITIVE(_Signed):
    """DECIMAL_POSITIVE ::= '+' DECIMAL"""

    value: str
    sign: ClassVar[str] = "+"
    pattern: ClassVar[re.Pattern[str]] = _c(DECIMAL_RE)


@production
class DOUBLE_POSITIVE(_Signed):
    """DOUBLE_POSITIVE ::= '+' DOUBLE"""

    value: str
    sign: ClassVar[str] = "+"
    pattern: ClassVar[re.Pattern[str]] = _c(DOUBLE_RE)


@production
class INTEGER_NEGATIVE(_Signed):
    """INTEGER_NEGATIVE ::= '-' INTEGER"""

    value: str
    sign: ClassVar[str] = "-"
    pattern: ClassVar[re.Pattern[str]] = _c(INTEGER_RE)


@production
class DECIMAL_NEGATIVE(_Signed):
    """DECIMAL_NEGATIVE ::= '-' DECIMAL"""

    value: str
    sign: ClassVar[str] = "-"
    pattern: ClassVar[re.Pattern[str]] = _c(DECIMAL_RE)


@production
class DOUBLE_NEGATIVE(_Signed):
    """DOUBLE_NEGATIVE ::= '-' DOUBLE"""

    value: str
    sign: ClassVar[str] = "-"
    pattern: ClassVar[re.Pattern[str]] = _c(DOUBLE_RE)


class _Quoted(Terminal):
    """Shared rendering for the quoted string terminals."""

    __slots__ = ()
    quote: ClassVar[str] = '"'

    def render(self, add: Add) -> None:
        q = type(self).quote
        add(q)
        add(self.value)
        add(q)


@production
class STRING_LITERAL1(_Quoted):
    """STRING_LITERAL1 ::= "'" ( ([^#x27#x5C#xA#xD]) | ECHAR | UCHAR )* "'" """

    value: str
    quote: ClassVar[str] = "'"
    pattern: ClassVar[re.Pattern[str]] = _c(STRING_LITERAL1_INNER_RE)


@production
class STRING_LITERAL2(_Quoted):
    '''STRING_LITERAL2 ::= '"' ( ([^#x22#x5C#xA#xD]) | ECHAR | UCHAR )* '"' '''

    value: str
    quote: ClassVar[str] = '"'
    pattern: ClassVar[re.Pattern[str]] = _c(STRING_LITERAL2_INNER_RE)


@production
class STRING_LITERAL_LONG1(_Quoted):
    """STRING_LITERAL_LONG1 ::= "'''" ( ( "'" | "''" )? ( [^'\\] | ECHAR | UCHAR ) )* "'''" """

    value: str
    quote: ClassVar[str] = "'''"
    pattern: ClassVar[re.Pattern[str]] = _c(STRING_LITERAL_LONG1_INNER_RE)


@production
class STRING_LITERAL_LONG2(_Quoted):
    '''STRING_LITERAL_LONG2 ::= \'"""\' ( ( \'"\' | \'""\' )? ( [^"\\] | ECHAR | UCHAR ) )* \'"""\' '''

    value: str
    quote: ClassVar[str] = '"""'
    pattern: ClassVar[re.Pattern[str]] = _c(STRING_LITERAL_LONG2_INNER_RE)


@production
class NIL(Node):
    """NIL ::= '(' WS* ')'"""

    def render(self, add: Add) -> None:
        add("()")


@production
class ANON(Node):
    """ANON ::= '[' WS* ']'"""

    def render(self, add: Add) -> None:
        add("[]")
