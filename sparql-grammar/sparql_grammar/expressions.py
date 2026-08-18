"""Expression productions, including the built-in function calls and aggregates.

The grammar reaches a primary expression through nine levels of precedence
(``Expression -> ConditionalOr -> ConditionalAnd -> ValueLogical -> Relational ->
Numeric -> Additive -> Multiplicative -> Unary -> Primary``). Spelling that tower out
by hand is the single worst piece of boilerplate in this problem space, so the
levels that are pure pass-throughs are aliases, and :class:`ConditionalOrExpression`
(aliased as ``Expression``) carries builders that construct a whole ladder in one
call: :meth:`~ConditionalOrExpression.compare`, ``all_of``, ``any_of``, ``negate``,
``from_primary_expression``.

``FILTER(?count = 101)`` is one call here; the same thing spelled out level by level
is a 39-line expression.
"""

from __future__ import annotations

from enum import Enum
from typing import Union

from ._base import Add, Node, alias, production
from .terminals import (
    ANON,
    BLANK_NODE_LABEL,
    DECIMAL,
    DECIMAL_NEGATIVE,
    DECIMAL_POSITIVE,
    DOUBLE,
    DOUBLE_NEGATIVE,
    DOUBLE_POSITIVE,
    INTEGER,
    INTEGER_NEGATIVE,
    INTEGER_POSITIVE,
    NIL,
    PNAME_LN,
    PNAME_NS,
    STRING_LITERAL1,
    STRING_LITERAL2,
    STRING_LITERAL_LONG1,
    STRING_LITERAL_LONG2,
)
from .terms import IRI, BooleanLiteral, RDFLiteral, Var

__all__ = [
    "Expression",
    "ConditionalOrExpression",
    "ConditionalAndExpression",
    "ValueLogical",
    "RelationalExpression",
    "RelationalOperator",
    "NumericExpression",
    "AdditiveExpression",
    "AdditiveOperator",
    "MultiplicativeExpression",
    "MultiplicativeOperator",
    "UnaryExpression",
    "UnaryOperator",
    "PrimaryExpression",
    "BrackettedExpression",
    "BuiltInCall",
    "BuiltIn",
    "RegexExpression",
    "SubstringExpression",
    "StrReplaceExpression",
    "ExistsFunc",
    "NotExistsFunc",
    "Aggregate",
    "AggregateFunction",
    "IRIOrFunction",
    "FunctionCall",
    "ArgList",
    "ExpressionList",
    "Constraint",
    "ExprTripleTerm",
    "ExprTripleTermSubject",
    "ExprTripleTermObject",
    "WILDCARD",
]

#: The ``*`` argument accepted by ``COUNT``.
WILDCARD = "*"


class RelationalOperator(str, Enum):
    """The comparison operators of ``RelationalExpression``."""

    EQ = "="
    NE = "!="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    IN = "IN"
    NOT_IN = "NOT IN"


class AdditiveOperator(str, Enum):
    PLUS = "+"
    MINUS = "-"


class MultiplicativeOperator(str, Enum):
    TIMES = "*"
    DIVIDE = "/"


class UnaryOperator(str, Enum):
    NOT = "!"
    PLUS = "+"
    MINUS = "-"


class BuiltIn(str, Enum):
    """The named built-in functions of ``BuiltInCall``.

    Includes the SPARQL 1.2 additions: ``LANGDIR``, ``STRLANGDIR``, ``hasLANG``,
    ``hasLANGDIR``, ``isTRIPLE``, ``TRIPLE``, ``SUBJECT``, ``PREDICATE``, ``OBJECT``.
    """

    STR = "STR"
    LANG = "LANG"
    LANGMATCHES = "LANGMATCHES"
    LANGDIR = "LANGDIR"
    DATATYPE = "DATATYPE"
    BOUND = "BOUND"
    IRI = "IRI"
    URI = "URI"
    BNODE = "BNODE"
    RAND = "RAND"
    ABS = "ABS"
    CEIL = "CEIL"
    FLOOR = "FLOOR"
    ROUND = "ROUND"
    CONCAT = "CONCAT"
    STRLEN = "STRLEN"
    UCASE = "UCASE"
    LCASE = "LCASE"
    ENCODE_FOR_URI = "ENCODE_FOR_URI"
    CONTAINS = "CONTAINS"
    STRSTARTS = "STRSTARTS"
    STRENDS = "STRENDS"
    STRBEFORE = "STRBEFORE"
    STRAFTER = "STRAFTER"
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    HOURS = "HOURS"
    MINUTES = "MINUTES"
    SECONDS = "SECONDS"
    TIMEZONE = "TIMEZONE"
    TZ = "TZ"
    NOW = "NOW"
    UUID = "UUID"
    STRUUID = "STRUUID"
    MD5 = "MD5"
    SHA1 = "SHA1"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"
    COALESCE = "COALESCE"
    IF = "IF"
    STRLANG = "STRLANG"
    STRLANGDIR = "STRLANGDIR"
    STRDT = "STRDT"
    SAME_TERM = "sameTerm"
    IS_IRI = "isIRI"
    IS_URI = "isURI"
    IS_BLANK = "isBLANK"
    IS_LITERAL = "isLITERAL"
    IS_NUMERIC = "isNUMERIC"
    HAS_LANG = "hasLANG"
    HAS_LANGDIR = "hasLANGDIR"
    IS_TRIPLE = "isTRIPLE"
    TRIPLE = "TRIPLE"
    SUBJECT = "SUBJECT"
    PREDICATE = "PREDICATE"
    OBJECT = "OBJECT"


class AggregateFunction(str, Enum):
    COUNT = "COUNT"
    SUM = "SUM"
    MIN = "MIN"
    MAX = "MAX"
    AVG = "AVG"
    SAMPLE = "SAMPLE"
    GROUP_CONCAT = "GROUP_CONCAT"


# ---------------------------------------------------------------------------
# The precedence tower. Repetition is modelled as a flat list of (operator,
# operand) pairs rather than the grammar's right-recursion, so rendering stays
# linear and the operator can be a validated enum.
# ---------------------------------------------------------------------------


@production(rule="UnaryExpression")
class UnaryExpression(Node):
    """UnaryExpression ::= '!' UnaryExpression | '+' PrimaryExpression | '-' PrimaryExpression | PrimaryExpression"""

    primary_expression: object
    operator: UnaryOperator | None = None

    def render(self, add: Add) -> None:
        if self.operator is not None:
            add(self.operator.value)
        self.primary_expression.render(add)


@production(rule="MultiplicativeExpression")
class MultiplicativeExpression(Node):
    """MultiplicativeExpression ::= UnaryExpression ( '*' UnaryExpression | '/' UnaryExpression )*"""

    base_expression: UnaryExpression
    additional_expressions: list = None

    def __post_init__(self) -> None:
        if self.additional_expressions is None:
            self.additional_expressions = []

    def render(self, add: Add) -> None:
        self.base_expression.render(add)
        for operator, operand in self.additional_expressions:
            add(" ")
            add(operator.value)
            add(" ")
            operand.render(add)


@production(rule="AdditiveExpression")
class AdditiveExpression(Node):
    """AdditiveExpression ::= MultiplicativeExpression ( '+' MultiplicativeExpression | '-' MultiplicativeExpression | ( NumericLiteralPositive | NumericLiteralNegative ) ( ( '*' UnaryExpression ) | ( '/' UnaryExpression ) )* )*

    The grammar's third branch is a lexical shortcut for a signed numeric literal
    (``?x -3``); it is represented here as an ordinary ``-``/``+`` pair with a
    literal operand, which renders identically.
    """

    base_expression: MultiplicativeExpression
    additional_expressions: list = None

    def __post_init__(self) -> None:
        if self.additional_expressions is None:
            self.additional_expressions = []

    def render(self, add: Add) -> None:
        self.base_expression.render(add)
        for operator, operand in self.additional_expressions:
            add(" ")
            add(operator.value)
            add(" ")
            operand.render(add)


#: NumericExpression ::= AdditiveExpression
NumericExpression = alias("NumericExpression", AdditiveExpression)


@production(rule="RelationalExpression")
class RelationalExpression(Node):
    """RelationalExpression ::= NumericExpression ( '=' NumericExpression | '!=' NumericExpression | '<' NumericExpression | '>' NumericExpression | '<=' NumericExpression | '>=' NumericExpression | 'IN' ExpressionList | 'NOT' 'IN' ExpressionList )?"""

    left: AdditiveExpression
    operator: RelationalOperator | None = None
    right: object = None

    def render(self, add: Add) -> None:
        self.left.render(add)
        if self.operator is None:
            return
        add(" ")
        add(self.operator.value)
        add(" ")
        self.right.render(add)


#: ValueLogical ::= RelationalExpression
ValueLogical = alias("ValueLogical", RelationalExpression)


@production(rule="ConditionalAndExpression")
class ConditionalAndExpression(Node):
    """ConditionalAndExpression ::= ValueLogical ( '&&' ValueLogical )*"""

    value_logicals: list[RelationalExpression]

    def render(self, add: Add) -> None:
        for i, value_logical in enumerate(self.value_logicals):
            if i:
                add(" && ")
            value_logical.render(add)


@production(rule="ConditionalOrExpression")
class ConditionalOrExpression(Node):
    """ConditionalOrExpression ::= ConditionalAndExpression ( '||' ConditionalAndExpression )*

    Aliased as ``Expression``. The classmethods build whole ladders in one call.
    """

    conditional_and_expressions: list[ConditionalAndExpression]

    def render(self, add: Add) -> None:
        for i, and_expression in enumerate(self.conditional_and_expressions):
            if i:
                add(" || ")
            and_expression.render(add)

    # -- builders ----------------------------------------------------------

    @staticmethod
    def _to_primary(value: object) -> object:
        """Accept a bare term, a built-in call, or an already-wrapped expression."""
        if isinstance(value, str):
            return RDFLiteral(value)
        if isinstance(value, bool):
            return BooleanLiteral(value)
        if isinstance(value, int):
            return INTEGER(str(value))
        if isinstance(value, ConditionalOrExpression):
            return BrackettedExpression(value)
        return value

    @classmethod
    def _to_numeric(cls, value: object) -> AdditiveExpression:
        """Lift anything up to the AdditiveExpression level of the tower."""
        if isinstance(value, AdditiveExpression):
            return value
        if isinstance(value, MultiplicativeExpression):
            return AdditiveExpression(value)
        if isinstance(value, UnaryExpression):
            return AdditiveExpression(MultiplicativeExpression(value))
        return AdditiveExpression(
            MultiplicativeExpression(UnaryExpression(cls._to_primary(value)))
        )

    @classmethod
    def from_primary_expression(cls, primary_expression: object) -> ConditionalOrExpression:
        """Wrap a primary expression in the full tower."""
        return cls(
            [
                ConditionalAndExpression(
                    [RelationalExpression(cls._to_numeric(primary_expression))]
                )
            ]
        )

    @classmethod
    def compare(
        cls, left: object, operator: RelationalOperator | str, right: object
    ) -> ConditionalOrExpression:
        """``Expression.compare(Var("count"), "=", 101)`` -> ``?count = 101``"""
        return cls(
            [
                ConditionalAndExpression(
                    [
                        RelationalExpression(
                            cls._to_numeric(left),
                            RelationalOperator(operator),
                            cls._to_numeric(right),
                        )
                    ]
                )
            ]
        )

    @classmethod
    def in_(
        cls, left: object, values: list, negated: bool = False
    ) -> ConditionalOrExpression:
        """``?x IN (1, 2)``, or ``NOT IN`` when ``negated``."""
        return cls(
            [
                ConditionalAndExpression(
                    [
                        RelationalExpression(
                            cls._to_numeric(left),
                            RelationalOperator.NOT_IN
                            if negated
                            else RelationalOperator.IN,
                            ExpressionList(
                                [
                                    v
                                    if isinstance(v, ConditionalOrExpression)
                                    else cls.from_primary_expression(v)
                                    for v in values
                                ]
                            ),
                        )
                    ]
                )
            ]
        )

    @classmethod
    def all_of(cls, *expressions: object) -> ConditionalOrExpression:
        """Join with ``&&``. Accepts expressions or anything liftable to one."""
        value_logicals: list[RelationalExpression] = []
        for expression in expressions:
            value_logicals.extend(cls._as_value_logicals(expression))
        return cls([ConditionalAndExpression(value_logicals)])

    @classmethod
    def any_of(cls, *expressions: object) -> ConditionalOrExpression:
        """Join with ``||``."""
        and_expressions: list[ConditionalAndExpression] = []
        for expression in expressions:
            if isinstance(expression, ConditionalOrExpression):
                and_expressions.extend(expression.conditional_and_expressions)
            else:
                and_expressions.append(
                    ConditionalAndExpression(cls._as_value_logicals(expression))
                )
        return cls(and_expressions)

    @classmethod
    def _as_value_logicals(cls, expression: object) -> list[RelationalExpression]:
        if isinstance(expression, ConditionalOrExpression):
            if len(expression.conditional_and_expressions) == 1:
                return expression.conditional_and_expressions[0].value_logicals
            # an || chain must be bracketed before it can join an && chain
            return [RelationalExpression(cls._to_numeric(expression))]
        if isinstance(expression, ConditionalAndExpression):
            return expression.value_logicals
        if isinstance(expression, RelationalExpression):
            return [expression]
        return [RelationalExpression(cls._to_numeric(expression))]

    @classmethod
    def negate(cls, expression: object) -> ConditionalOrExpression:
        """``!(...)`` - brackets the operand when it is a compound expression."""
        if isinstance(expression, ConditionalOrExpression):
            operand = BrackettedExpression(expression)
        else:
            operand = cls._to_primary(expression)
        return cls.from_primary_expression(
            UnaryExpression(operand, UnaryOperator.NOT)
        )


#: Expression ::= ConditionalOrExpression
Expression = alias("Expression", ConditionalOrExpression)


@production(rule="BrackettedExpression")
class BrackettedExpression(Node):
    """BrackettedExpression ::= '(' Expression ')'"""

    expression: ConditionalOrExpression

    def render(self, add: Add) -> None:
        add("(")
        self.expression.render(add)
        add(")")


# ---------------------------------------------------------------------------
# Function calls
# ---------------------------------------------------------------------------


@production(rule="ExpressionList")
class ExpressionList(Node):
    """ExpressionList ::= NIL | '(' Expression ( ',' Expression )* ')'"""

    expressions: list = None

    def __post_init__(self) -> None:
        if self.expressions is None:
            self.expressions = []

    def render(self, add: Add) -> None:
        if not self.expressions:
            add("()")
            return
        add("(")
        for i, expression in enumerate(self.expressions):
            if i:
                add(", ")
            expression.render(add)
        add(")")


@production(rule="ArgList")
class ArgList(Node):
    """ArgList ::= NIL | '(' 'DISTINCT'? Expression ( ',' Expression )* ')'"""

    expressions: list = None
    distinct: bool = False

    def __post_init__(self) -> None:
        if self.expressions is None:
            self.expressions = []

    def render(self, add: Add) -> None:
        if not self.expressions:
            add("()")
            return
        add("(")
        if self.distinct:
            add("DISTINCT ")
        for i, expression in enumerate(self.expressions):
            if i:
                add(", ")
            expression.render(add)
        add(")")


@production(rule="BuiltInCall")
class BuiltInCall(Node):
    """BuiltInCall ::= Aggregate | 'STR' '(' Expression ')' | ... | 'OBJECT' '(' Expression ')'

    The named forms all render as ``NAME(arg, ...)``, so one class covers them.
    ``Aggregate``, ``RegexExpression``, ``SubstringExpression``,
    ``StrReplaceExpression``, ``ExistsFunc`` and ``NotExistsFunc`` are separate
    productions in their own right and appear directly in the
    ``PrimaryExpression`` union.
    """

    function: BuiltIn
    arguments: list = None

    def __post_init__(self) -> None:
        if self.arguments is None:
            self.arguments = []

    def render(self, add: Add) -> None:
        add(self.function.value)
        add("(")
        for i, argument in enumerate(self.arguments):
            if i:
                add(", ")
            argument.render(add)
        add(")")

    @classmethod
    def create(cls, function: BuiltIn | str, *arguments: object) -> BuiltInCall:
        """``BuiltInCall.create("STR", Var("x"))`` -> ``STR(?x)``

        Arguments that are not already expressions are lifted for you.
        """
        lifted = [
            argument
            if isinstance(argument, (ConditionalOrExpression, Var))
            else ConditionalOrExpression.from_primary_expression(argument)
            for argument in arguments
        ]
        return cls(BuiltIn(function), lifted)


@production(rule="RegexExpression")
class RegexExpression(Node):
    """RegexExpression ::= 'REGEX' '(' Expression ',' Expression ( ',' Expression )? ')'"""

    text_expression: ConditionalOrExpression
    pattern_expression: ConditionalOrExpression
    flags_expression: ConditionalOrExpression | None = None

    def render(self, add: Add) -> None:
        add("REGEX(")
        self.text_expression.render(add)
        add(", ")
        self.pattern_expression.render(add)
        if self.flags_expression is not None:
            add(", ")
            self.flags_expression.render(add)
        add(")")


@production(rule="SubstringExpression")
class SubstringExpression(Node):
    """SubstringExpression ::= 'SUBSTR' '(' Expression ',' Expression ( ',' Expression )? ')'"""

    source_expression: ConditionalOrExpression
    starting_loc: ConditionalOrExpression
    length: ConditionalOrExpression | None = None

    def render(self, add: Add) -> None:
        add("SUBSTR(")
        self.source_expression.render(add)
        add(", ")
        self.starting_loc.render(add)
        if self.length is not None:
            add(", ")
            self.length.render(add)
        add(")")


@production(rule="StrReplaceExpression")
class StrReplaceExpression(Node):
    """StrReplaceExpression ::= 'REPLACE' '(' Expression ',' Expression ',' Expression ( ',' Expression )? ')'"""

    arg: ConditionalOrExpression
    pattern: ConditionalOrExpression
    replacement: ConditionalOrExpression
    flags: ConditionalOrExpression | None = None

    def render(self, add: Add) -> None:
        add("REPLACE(")
        self.arg.render(add)
        add(", ")
        self.pattern.render(add)
        add(", ")
        self.replacement.render(add)
        if self.flags is not None:
            add(", ")
            self.flags.render(add)
        add(")")


@production(rule="ExistsFunc")
class ExistsFunc(Node):
    """ExistsFunc ::= 'EXISTS' GroupGraphPattern

    ``group_graph_pattern`` is a ``GroupGraphPattern``; it is typed loosely here
    because that production lives in ``grammar``, which imports this module.
    """

    group_graph_pattern: Node

    def render(self, add: Add) -> None:
        add("EXISTS ")
        self.group_graph_pattern.render(add)


@production(rule="NotExistsFunc")
class NotExistsFunc(Node):
    """NotExistsFunc ::= 'NOT' 'EXISTS' GroupGraphPattern"""

    group_graph_pattern: Node

    def render(self, add: Add) -> None:
        add("NOT EXISTS ")
        self.group_graph_pattern.render(add)


@production(rule="Aggregate")
class Aggregate(Node):
    """Aggregate ::= 'COUNT' '(' 'DISTINCT'? ( '*' | Expression ) ')' | 'SUM' ... | 'GROUP_CONCAT' '(' 'DISTINCT'? Expression ( ';' 'SEPARATOR' '=' String )? ')'

    ``expression`` may be the string ``"*"`` for ``COUNT(*)``. ``separator`` applies
    only to ``GROUP_CONCAT``; that constraint is checked by ``validate()`` rather
    than at construction time.
    """

    function: AggregateFunction
    expression: object = None
    distinct: bool = False
    separator: str | None = None

    def render(self, add: Add) -> None:
        add(self.function.value)
        add("(")
        if self.distinct:
            add("DISTINCT ")
        if self.expression == WILDCARD or self.expression is None:
            add("*")
        else:
            self.expression.render(add)
        if self.separator is not None:
            add(';SEPARATOR="')
            add(self.separator)
            add('"')
        add(")")

    def _check(self, level: str) -> list[str]:
        errors = super()._check(level)
        if self.separator is not None and self.function is not AggregateFunction.GROUP_CONCAT:
            errors.append(
                f"Aggregate: SEPARATOR is only valid for GROUP_CONCAT, not {self.function.value}"
            )
        if self.expression in (None, WILDCARD) and self.function is not AggregateFunction.COUNT:
            errors.append(
                f"Aggregate: '*' is only valid for COUNT, not {self.function.value}"
            )
        return errors

    @classmethod
    def count(cls, expression: object = WILDCARD, distinct: bool = False) -> Aggregate:
        """``COUNT(*)`` by default, or ``COUNT(?x)`` / ``COUNT(DISTINCT ?x)``."""
        if expression is not WILDCARD and not isinstance(
            expression, ConditionalOrExpression
        ):
            expression = ConditionalOrExpression.from_primary_expression(expression)
        return cls(AggregateFunction.COUNT, expression, distinct)

    @classmethod
    def create(
        cls,
        function: AggregateFunction | str,
        expression: object,
        distinct: bool = False,
        separator: str | None = None,
    ) -> Aggregate:
        if not isinstance(expression, ConditionalOrExpression) and expression != WILDCARD:
            expression = ConditionalOrExpression.from_primary_expression(expression)
        return cls(AggregateFunction(function), expression, distinct, separator)


@production(rule="iriOrFunction")
class IRIOrFunction(Node):
    """iriOrFunction ::= iri ArgList?"""

    iri: object
    arg_list: ArgList | None = None

    def render(self, add: Add) -> None:
        self.iri.render(add)
        if self.arg_list is not None:
            self.arg_list.render(add)


@production(rule="FunctionCall")
class FunctionCall(Node):
    """FunctionCall ::= iri ArgList"""

    iri: object
    arg_list: ArgList

    def render(self, add: Add) -> None:
        self.iri.render(add)
        self.arg_list.render(add)


# ---------------------------------------------------------------------------
# SPARQL 1.2 triple terms inside expressions
# ---------------------------------------------------------------------------

#: ExprTripleTermSubject ::= iri | Var
ExprTripleTermSubject = alias(
    "ExprTripleTermSubject", Union[IRI, PNAME_LN, PNAME_NS, Var]
)


@production(rule="ExprTripleTerm")
class ExprTripleTerm(Node):
    """ExprTripleTerm ::= '<<(' ExprTripleTermSubject Verb ExprTripleTermObject ')>>'

    New in SPARQL 1.2.
    """

    subject: object
    verb: object
    object: object

    def render(self, add: Add) -> None:
        add("<<(")
        self.subject.render(add)
        add(" ")
        self.verb.render(add)
        add(" ")
        self.object.render(add)
        add(")>>")


#: ExprTripleTermObject ::= iri | RDFLiteral | NumericLiteral | BooleanLiteral | Var | ExprTripleTerm
ExprTripleTermObject = alias(
    "ExprTripleTermObject",
    Union[
        IRI,
        PNAME_LN,
        PNAME_NS,
        RDFLiteral,
        INTEGER,
        DECIMAL,
        DOUBLE,
        INTEGER_POSITIVE,
        DECIMAL_POSITIVE,
        DOUBLE_POSITIVE,
        INTEGER_NEGATIVE,
        DECIMAL_NEGATIVE,
        DOUBLE_NEGATIVE,
        BooleanLiteral,
        Var,
        ExprTripleTerm,
    ],
)

#: PrimaryExpression ::= BrackettedExpression | BuiltInCall | iriOrFunction | RDFLiteral | NumericLiteral | BooleanLiteral | Var | ExprTripleTerm
#:
#: The ``BuiltInCall`` alternatives that are productions in their own right
#: (Aggregate, RegexExpression, ...) are admitted here directly, which removes a
#: redundant wrapper without changing the rendered output.
PrimaryExpression = alias(
    "PrimaryExpression",
    Union[
        BrackettedExpression,
        BuiltInCall,
        Aggregate,
        RegexExpression,
        SubstringExpression,
        StrReplaceExpression,
        ExistsFunc,
        NotExistsFunc,
        IRIOrFunction,
        RDFLiteral,
        INTEGER,
        DECIMAL,
        DOUBLE,
        INTEGER_POSITIVE,
        DECIMAL_POSITIVE,
        DOUBLE_POSITIVE,
        INTEGER_NEGATIVE,
        DECIMAL_NEGATIVE,
        DOUBLE_NEGATIVE,
        BooleanLiteral,
        Var,
        ExprTripleTerm,
    ],
)

#: Constraint ::= BrackettedExpression | BuiltInCall | FunctionCall
Constraint = alias(
    "Constraint",
    Union[
        BrackettedExpression,
        BuiltInCall,
        Aggregate,
        RegexExpression,
        SubstringExpression,
        StrReplaceExpression,
        ExistsFunc,
        NotExistsFunc,
        FunctionCall,
    ],
)
