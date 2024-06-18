# https://www.w3.org/TR/sparql11-query/#rIRIREF
# [139] IRIREF ::= '<' ([^<>"{}|^`\]-[#x00-#x20])* '>'
IRIREF_REGEX = r'([^<>"{}|^`\\u0000-\\u0020])*'

# https://www.w3.org/TR/sparql11-query/#rPN_CHARS_BASE
# [164] PN_CHARS_BASE ::= [A-Z] | [a-z] | [#x00C0-#x00D6] | [#x00D8-#x00F6] | [#x00F8-#x02FF] | [#x0370-#x037D] | [#x037F-#x1FFF] | [#x200C-#x200D] | [#x2070-#x218F] | [#x2C00-#x2FEF] | [#x3001-#xD7FF] | [#xF900-#xFDCF] | [#xFDF0-#xFFFD] | [#x10000-#xEFFFF]
PN_CHARS_BASE_REGEX = (
    r"[A-Z]|[a-z]|"
    r"[\u00C0-\u00D6]|"
    r"[\u00D8-\u00F6]|"
    r"[\u00F8-\u02FF]|"
    r"[\u0370-\u037D]|"
    r"[\u037F-\u1FFF]|"
    r"[\u200C-\u200D]|"
    r"[\u2070-\u218F]|"
    r"[\u2C00-\u2FEF]|"
    r"[\u3001-\uD7FF]|"
    r"[\uF900-\uFDCF]|"
    r"[\uFDF0-\uFFFD]|"
    r"[\U00010000-\U000EFFFF]"
)

# https://www.w3.org/TR/sparql11-query/#rINTEGER
# [146] INTEGER ::= [0-9]+
INT = r"[0-9]"
INTEGER_REGEX = rf"{INT}+"

# https://www.w3.org/TR/sparql11-query/#rPN_CHARS_U
# [165] PN_CHARS_U ::= PN_CHARS_BASE | '_'
PN_CHARS_U_REGEX = rf"({PN_CHARS_BASE_REGEX}|_)"

# https://www.w3.org/TR/sparql11-query/#rPN_CHARS
# [167] PN_CHARS ::= PN_CHARS_U | '-' | [0-9] | #x00B7 | [#x0300-#x036F] | [#x203F-#x2040]
PN_CHARS_REGEX = rf"({PN_CHARS_U_REGEX}|-|{INT}|[\u00B7]|[\u0300-\u036F]|[\u203F-\u2040])"

# https://www.w3.org/TR/sparql11-query/#rPN_PREFIX
# [168] PN_PREFIX ::= PN_CHARS_BASE ((PN_CHARS|'.')* PN_CHARS)?
PN_PREFIX_REGEX = (
    rf"{PN_CHARS_BASE_REGEX}(({PN_CHARS_REGEX}|\.)*{PN_CHARS_REGEX})?"
)

# https://www.w3.org/TR/sparql11-query/#rPNAME_NS
# [140] PNAME_NS ::= PN_PREFIX? ':'
PNAME_NS_REGEX = rf"({PN_PREFIX_REGEX})?"

# https://www.w3.org/TR/sparql11-query/#rVARNAME
# [166] VARNAME ::= ( PN_CHARS_U | [0-9] ) ( PN_CHARS_U | [0-9] | #x00B7 | [#x0300-#x036F] | [#x203F-#x2040] )*
VARNAME_REGEX = rf"({PN_CHARS_U_REGEX}|{INT})({PN_CHARS_U_REGEX}|{INT}|[\u00B7]|[\u0300-\u036F]|[\u203F-\u2040])*"

# https://www.w3.org/TR/sparql11-query/#rBLANK_NODE_LABEL
# [142] BLANK_NODE_LABEL ::= '_:' ( PN_CHARS_U | [0-9] ) ((PN_CHARS|'.')* PN_CHARS)?
BLANK_NODE_LABEL_REGEX = rf"(({PN_CHARS_U_REGEX}|{INT})(({PN_CHARS_REGEX}|\.)*{PN_CHARS_REGEX})?)"

# https://www.w3.org/TR/sparql11-query/#rLANGTAG
# [145] LANGTAG ::= '@' [a-zA-Z]+ ('-' [a-zA-Z0-9]+)*
LANGTAG_REGEX = r"@[a-zA-Z]+(-[a-zA-Z0-9]+)*"

# https://www.w3.org/TR/sparql11-query/#rDECIMAL
# [147] DECIMAL ::= [0-9]* '.' [0-9]+
DECIMAL_REGEX = rf"{INT}*\.{INT}+"

# https://www.w3.org/TR/sparql11-query/#rEXPONENT
# [155] EXPONENT ::= [eE] [+-]? [0-9]+
EXPONENT_REGEX = rf"[eE][+-]?{INT}+"

# https://www.w3.org/TR/sparql11-query/#rDOUBLE
# [148] DOUBLE ::= [0-9]+ '.' [0-9]* EXPONENT | '.' ([0-9])+ EXPONENT | ([0-9])+ EXPONENT
DOUBLE_REGEX = rf"{INT}+\.{INT}*{EXPONENT_REGEX}|\.{INT}+{EXPONENT_REGEX}|{INT}+{EXPONENT_REGEX}"

# https://www.w3.org/TR/sparql11-query/#rECHAR
# [160] ECHAR ::= '\' [tbnrf\"']
ECHAR_REGEX = r"\\[tbnrf\"\'\\]"

# https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL1
# [156] STRING_LITERAL1 ::= "'" ( ([^#x27#x5C#xA#xD]) | ECHAR )* "'"
STRING_LITERAL1_REGEX = (
    rf"([^\\u0027\\u005C\\u000A\\u000D]|{ECHAR_REGEX})*"
)

# https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL2
# [157] STRING_LITERAL2 ::= '"' ( ([^#x22#x5C#xA#xD]) | ECHAR )* '"'
STRING_LITERAL2_REGEX = (
    rf"([^\\u0022\\u005C\\u000A\\u000D]|{ECHAR_REGEX})*"
)

# https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL_LONG1
# [158] STRING_LITERAL_LONG1 ::= "'''" ( ( "'" | "''" )? ( [^'\] | ECHAR ) )* "'''"
STRING_LITERAL_LONG1_REGEX = (
    rf"'''((''|')?([^'\\]|{ECHAR_REGEX}))*'''"
)

# https://www.w3.org/TR/sparql11-query/#rSTRING_LITERAL_LONG2
# [159] STRING_LITERAL_LONG2 ::= '"""' ( ( '"' | '""' )? ( [^"\] | ECHAR ) )* '"""'
STRING_LITERAL_LONG2_REGEX = (
    rf'"""(("|"")?([^"\\]|{ECHAR_REGEX}))*"""'
)

# https://www.w3.org/TR/sparql11-query/#rWS
# [162] WS ::= #x20 | #x9 | #xD | #xA
WS_REGEX = r"[\u0020\u0009\u000D\u000A]"

# https://www.w3.org/TR/sparql11-query/#rNIL
# [161] NIL ::= '(' WS* ')'
NIL_ANON_REGEX = rf"{WS_REGEX}*"

# https://www.w3.org/TR/sparql11-query/#rHEX
# [172] HEX ::= [0-9] | [A-F] | [a-f]
HEX_REGEX = r"[0-9A-Fa-f]"

# https://www.w3.org/TR/sparql11-query/#rPERCENT
# [171] PERCENT ::= '%' HEX HEX
PERCENT_REGEX = rf"%{HEX_REGEX}{HEX_REGEX}"

# https://www.w3.org/TR/sparql11-query/#rPN_LOCAL_ESC
# [173] PN_LOCAL_ESC ::= '\' ( '_' | '~' | '.' | '-' | '!' | '$' | '&' | "'" | '(' | ')' | '*' | '+' | ',' | ';' | '=' | '/' | '?' | '#' | '@' | '%' )
PN_LOCAL_ESC_REGEX = r"[_~.\-!$&\'()*+,;=\/?@%]"

# https://www.w3.org/TR/sparql11-query/#rPLX
# [170] PLX ::= PERCENT | PN_LOCAL_ESC
PLX_REGEX = rf"{PERCENT_REGEX}|{PN_LOCAL_ESC_REGEX}"

# https://www.w3.org/TR/sparql11-query/#rPN_LOCAL
# [169] PN_LOCAL ::= (PN_CHARS_U | ':' | [0-9] | PLX ) ((PN_CHARS | '.' | ':' | PLX)* (PN_CHARS | ':' | PLX) )?
PN_LOCAL_REGEX = rf"({PN_CHARS_U_REGEX}|:|{INT}|{PLX_REGEX})(({PN_CHARS_REGEX}|.|:|{PLX_REGEX})*({PN_CHARS_REGEX}|:|{PLX_REGEX}))?"

# https://www.w3.org/TR/sparql11-query/#rPNAME_LN
# [141] PNAME_LN ::= PNAME_NS PN_LOCAL
PNAME_LN_REGEX = f"{PNAME_NS_REGEX}{PN_LOCAL_REGEX}"
