"""
Token definitions for EonLang lexer.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional


class TokenType(Enum):
    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    CHAR = auto()
    BOOL = auto()
    IDENTIFIER = auto()
    
    # Keywords
    FN = auto()
    LET = auto()
    MUT = auto()
    CONST = auto()
    IF = auto()
    ELSE = auto()
    MATCH = auto()
    CASE = auto()
    LOOP = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    RETURN = auto()
    BREAK = auto()
    CONTINUE = auto()
    STRUCT = auto()
    ENUM = auto()
    TRAIT = auto()
    IMPL = auto()
    PUB = auto()
    MOD = auto()
    USE = auto()
    WHERE = auto()
    AS = auto()
    TYPE = auto()
    SELF = auto()
    STATIC = auto()
    
    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    AMPERSAND = auto()
    PIPE = auto()
    CARET = auto()
    TILDE = auto()
    BANG = auto()
    DOT = auto()
    DOTDOT = auto()
    DOTDOTDOT = auto()
    
    # Comparison
    EQ = auto()
    NE = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    
    # Assignment
    ASSIGN = auto()
    PLUS_ASSIGN = auto()
    MINUS_ASSIGN = auto()
    STAR_ASSIGN = auto()
    SLASH_ASSIGN = auto()
    
    # Logical
    AND = auto()
    OR = auto()
    
    # Shift
    SHL = auto()
    SHR = auto()
    
    # Increment/Decrement
    PLUS_PLUS = auto()
    MINUS_MINUS = auto()
    
    # Arrow
    ARROW = auto()
    FAT_ARROW = auto()
    
    # Scope
    LBRACE = auto()
    RBRACE = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    
    # Special
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    UNDERSCORE = auto()
    
    # Special tokens
    EOF = auto()
    NEWLINE = auto()
    COMMENT = auto()
    DOC_COMMENT = auto()
    
    # Generics
    QUESTION = auto()
    COLON_COLON = auto()


# Keyword mapping
KEYWORDS = {
    'fn': TokenType.FN,
    'let': TokenType.LET,
    'mut': TokenType.MUT,
    'const': TokenType.CONST,
    'if': TokenType.IF,
    'else': TokenType.ELSE,
    'match': TokenType.MATCH,
    'case': TokenType.CASE,
    'loop': TokenType.LOOP,
    'while': TokenType.WHILE,
    'for': TokenType.FOR,
    'in': TokenType.IN,
    'return': TokenType.RETURN,
    'break': TokenType.BREAK,
    'continue': TokenType.CONTINUE,
    'struct': TokenType.STRUCT,
    'enum': TokenType.ENUM,
    'trait': TokenType.TRAIT,
    'impl': TokenType.IMPL,
    'pub': TokenType.PUB,
    'mod': TokenType.MOD,
    'use': TokenType.USE,
    'where': TokenType.WHERE,
    'as': TokenType.AS,
    'type': TokenType.TYPE,
    'self': TokenType.SELF,
    'static': TokenType.STATIC,
    'true': TokenType.BOOL,
    'false': TokenType.BOOL,
    'where': TokenType.WHERE,
}


@dataclass
class Token:
    """Represents a token in the source code."""
    type: TokenType
    value: str
    line: int
    column: int
    length: int = 0
    
    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"
    
    def is_keyword(self) -> bool:
        return self.type in KEYWORDS.values()
    
    def is_literal(self) -> bool:
        return self.type in (
            TokenType.INTEGER,
            TokenType.FLOAT,
            TokenType.STRING,
            TokenType.CHAR,
            TokenType.BOOL,
        )
    
    def is_operator(self) -> bool:
        return self.type in (
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
            TokenType.AMPERSAND,
            TokenType.PIPE,
            TokenType.CARET,
            TokenType.TILDE,
            TokenType.BANG,
        )
