from __future__ import annotations

import re
from typing import Generator

from pydantic import BaseModel, field_validator

from sparql_grammar_pydantic.terminals_regex import IRIREF_REGEX, PN_PREFIX_REGEX, PNAME_LN_REGEX, \
    BLANK_NODE_LABEL_REGEX, VARNAME_REGEX, LANGTAG_REGEX, INTEGER_REGEX, DECIMAL_REGEX, DOUBLE_REGEX, EXPONENT_REGEX, \
    STRING_LITERAL1_REGEX, STRING_LITERAL2_REGEX, STRING_LITERAL_LONG1_REGEX, STRING_LITERAL_LONG2_REGEX, ECHAR_REGEX, \
    NIL_ANON_REGEX, WS_REGEX, PN_CHARS_BASE_REGEX, PN_CHARS_U_REGEX, PN_CHARS_REGEX, PN_LOCAL_REGEX, PLX_REGEX, \
    PERCENT_REGEX, HEX_REGEX, PN_LOCAL_ESC_REGEX


class Terminal(BaseModel):
    value: str

    class Config:
        arbitrary_types_allowed = True

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"{self.__class__.__name__} ({self})"

    def __hash__(self):
        return hash(self.value)

    def render(self):
        raise self.value

    def to_string(self):
        return self.__str__()

    @field_validator("value")
    @classmethod
    def check_value(cls, v):
        pattern = cls.get_regex_pattern()
        match = re.fullmatch(pattern, v)
        if not match:
            raise ValueError(f"Invalid value: {v} does not match pattern: {pattern}")
        return v

    @classmethod
    def get_regex_pattern(cls):
        raise NotImplementedError(
            "Subclasses must implement this method to return the appropriate regex pattern."
        )


class IRIREF(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rIRIREF
    IRIREF ::= '<' ([^<>"{}|^`\x00-\x20])* '>'
    """

    @classmethod
    def get_regex_pattern(cls):
        return IRIREF_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "<"
        yield self.value
        yield ">"


class PNAME_NS(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPNAME_NS
    PNAME_NS ::= PN_PREFIX? ':'
    """

    @classmethod
    def get_regex_pattern(cls):
        return PN_PREFIX_REGEX


class PNAME_LN(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPNAME_LN
    PNAME_LN ::= PNAME_NS PN_LOCAL
    """

    @classmethod
    def get_regex_pattern(cls):
        return PNAME_LN_REGEX


class BlankNodeLabel(Terminal):
    """
    BLANK_NODE_LABEL	  ::=  	'_:' ( PN_CHARS_U | [0-9] ) ((PN_CHARS|'.')* PN_CHARS)?
    """

    @classmethod
    def get_regex_pattern(cls):
        return BLANK_NODE_LABEL_REGEX

    def render(self):
        yield "_:"
        yield self.value


class VAR1(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rVAR1
    VAR1	  ::=  	'?' VARNAME
    """

    def render(self):
        yield "?"
        yield self.value

    @classmethod
    def get_regex_pattern(self):
        return VARNAME_REGEX


class VAR2(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rVAR2
    VAR2	  ::=  	'$' VARNAME
    """

    @classmethod
    def get_regex_pattern(cls):
        return VARNAME_REGEX

    def render(self):
        yield "$"
        yield self.value


class LANGTAG(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rLANGTAG
    LANGTAG	  ::=  	'@' [a-zA-Z]+ ('-' [a-zA-Z0-9]+)*
    """

    @classmethod
    def get_regex_pattern(cls):
        return LANGTAG_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "@"
        yield self.value


class INTEGER(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rINTEGER
    INTEGER	  ::=  	[0-9]+
    """

    @classmethod
    def get_regex_pattern(cls):
        return INTEGER_REGEX


class DECIMAL(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rDECIMAL
    DECIMAL	  ::=  	[0-9]* '.' [0-9]+
    """

    @classmethod
    def get_regex_pattern(cls):
        return DECIMAL_REGEX


class DOUBLE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rDOUBLE
    DOUBLE	  ::=  	[0-9]+ '.' [0-9]* EXPONENT | '.' ([0-9])+ EXPONENT | ([0-9])+ EXPONENT
    """

    @classmethod
    def get_regex_pattern(self):
        return DOUBLE_REGEX


class INTEGER_POSITIVE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rINTEGER_POSITIVE
    INTEGER_POSITIVE ::= '+' INTEGER
    """

    @classmethod
    def get_regex_pattern(self):
        return INTEGER_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "+"
        yield self.value


class DECIMAL_POSITIVE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rDECIMAL_POSITIVE
    DECIMAL_POSITIVE ::= '+' DECIMAL
    """

    @classmethod
    def get_regex_pattern(self):
        return DECIMAL_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "+"
        yield self.value


class DOUBLE_POSITIVE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rDOUBLE_POSITIVE
    DOUBLE_POSITIVE ::= '+' DOUBLE
    """

    @classmethod
    def get_regex_pattern(self):
        return DOUBLE_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "+"
        yield self.value


class INTEGER_NEGATIVE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rINTEGER_NEGATIVE
    INTEGER_NEGATIVE ::= '-' INTEGER
    """

    @classmethod
    def get_regex_pattern(self):
        return INTEGER_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "-"
        yield self.value


class DECIMAL_NEGATIVE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rDECIMAL_NEGATIVE
    DECIMAL_NEGATIVE ::= '-' DECIMAL
    """

    @classmethod
    def get_regex_pattern(self):
        return DECIMAL_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "-"
        yield self.value


class DOUBLE_NEGATIVE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rDOUBLE_NEGATIVE
    DOUBLE_NEGATIVE ::= '-' DOUBLE
    """

    @classmethod
    def get_regex_pattern(self):
        return DOUBLE_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "-"
        yield self.value


class EXPONENT(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rEXPONENT
    EXPONENT	  ::=  	[eE] [+-]? [0-9]+
    """

    @classmethod
    def get_regex_pattern(self):
        return EXPONENT_REGEX


class STRING_LITERAL1(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL1
    STRING_LITERAL1	  ::=  	"'" ( ([^#x27#x5C#xA#xD]) | ECHAR )* "'"
    """

    @classmethod
    def get_regex_pattern(self):
        return STRING_LITERAL1_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "'"
        yield self.value
        yield "'"


class STRING_LITERAL2(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL2
    STRING_LITERAL2	  ::=  	'"' ( ([^#x22#x5C#xA#xD]) | ECHAR )* '"'
    """

    @classmethod
    def get_regex_pattern(self):
        return STRING_LITERAL2_REGEX

    def render(self) -> Generator[str, None, None]:
        yield '"'
        yield self.value
        yield '"'


class STRING_LITERAL_LONG1(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL_LONG1
    STRING_LITERAL_LONG1	  ::=  	"'''" ( ( "'" | "''" )? ( [^'\] | ECHAR ) )* "'''"
    """

    @classmethod
    def get_regex_pattern(self):
        return STRING_LITERAL_LONG1_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "'''"
        yield self.value
        yield "'''"


class STRING_LITERAL_LONG2(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL_LONG2
    STRING_LITERAL_LONG2	  ::=  	'\"""' ( ( '"' | '""' )? ( [^"\] | ECHAR ) )* '\"""'
    """

    @classmethod
    def get_regex_pattern(self):
        return STRING_LITERAL_LONG2_REGEX

    def render(self) -> Generator[str, None, None]:
        yield '"""'
        yield self.value
        yield '"""'


class ECHAR(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rECHAR
    ECHAR	  ::=  	'\' [tbnrf\"']
    """

    @classmethod
    def get_regex_pattern(self):
        return ECHAR_REGEX


class NIL(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rNIL
    NIL	  ::=  	'(' WS* ')'
    """

    @classmethod
    def get_regex_pattern(self):
        return NIL_ANON_REGEX

    def render(self) -> Generator[str, None, None]:
        yield "("
        yield self.value
        yield ")"


class WS(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rWS
    WS	  ::=  	#x20 | #x9 | #xD | #xA
    """

    @classmethod
    def get_regex_pattern(self):
        return WS_REGEX


class Anon:
    """
    ANON	  ::=  	'[' WS* ']'
    https://www.w3.org/TR/sparql11-query/#rANON
    """

    @classmethod
    def get_regex_pattern(self):
        return NIL_ANON_REGEX

    def render(self):
        yield "["
        yield self.value
        yield "]"


class PN_CHARS_BASE(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPN_CHARS_BASE
    PN_CHARS_BASE	  ::=  	[A-Z] | [a-z] | [#x00C0-#x00D6] | [#x00D8-#x00F6] | [#x00F8-#x02FF] | [#x0370-#x037D] | [#x037F-#x1FFF] | [#x200C-#x200D] | [#x2070-#x218F] | [#x2C00-#x2FEF] | [#x3001-#xD7FF] | [#xF900-#xFDCF] | [#xFDF0-#xFFFD] | [#x10000-#xEFFFF]
    """

    @classmethod
    def get_regex_pattern(self):
        return PN_CHARS_BASE_REGEX


class PN_CHARS_U(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPN_CHARS_U
    PN_CHARS_U	  ::=  	PN_CHARS_BASE | '_'
    """

    @classmethod
    def get_regex_pattern(self):
        return PN_CHARS_U_REGEX


class VARNAME(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rVARNAME
    VARNAME	  ::=  	( PN_CHARS_U | [0-9] ) ( PN_CHARS_U | [0-9] | #x00B7 | [#x0300-#x036F] | [#x203F-#x2040] )*
    """

    @classmethod
    def get_regex_pattern(self):
        return VARNAME_REGEX


class PN_CHARS(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPN_CHARS
    PN_CHARS	  ::=  	PN_CHARS_U | '-' | [0-9] | #x00B7 | [#x0300-#x036F] | [#x203F-#x2040]
    """

    @classmethod
    def get_regex_pattern(self):
        return PN_CHARS_REGEX


class PN_PREFIX(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPN_PREFIX
    PN_PREFIX	  ::=  	PN_CHARS_BASE ((PN_CHARS|'.')* PN_CHARS)?
    """

    @classmethod
    def get_regex_pattern(self):
        return PN_PREFIX_REGEX


class PN_LOCAL(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPN_LOCAL
    PN_LOCAL	  ::=  	(PN_CHARS_U | ':' | [0-9] | PLX) ((PN_CHARS|'.'|':'|PLX)* (PN_CHARS|':'|PLX))?
    """

    @classmethod
    def get_regex_pattern(self):
        return PN_LOCAL_REGEX


class PLX(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPLX
    PLX	  ::=  	PERCENT | PN_LOCAL_ESC
    """

    @classmethod
    def get_regex_pattern(self):
        return PLX_REGEX


class PERCENT(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPERCENT
    PERCENT	  ::=  	'%' HEX HEX
    """

    @classmethod
    def get_regex_pattern(self):
        return PERCENT_REGEX


class HEX(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rHEX
    HEX	  ::=  	[0-9] | [A-F] | [a-f]
    """

    @classmethod
    def get_regex_pattern(self):
        return HEX_REGEX


class PN_LOCAL_ESC(Terminal):
    """
    https://www.w3.org/TR/sparql11-query/#rPN_LOCAL_ESC
    PN_LOCAL_ESC	  ::=  	'\' ( '_' | '~' | '.' | '-' | '!' | '$' | '&' | "'" | '(' | ')' | '*' | '+' | ',' | ';' | '=' | '/' | '?' | '#' | '@' | '%' )
    """

    @classmethod
    def get_regex_pattern(self):
        return PN_LOCAL_ESC_REGEX

    def render(self):
        yield "\\"
        yield self.value
