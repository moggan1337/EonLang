"""
Lexer for EonLang - Tokenizes source code.
"""

from .tokens import Token, TokenType, KEYWORDS
from typing import List, Optional


class LexerError(Exception):
    """Raised when the lexer encounters an invalid token."""
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Lexer error at {line}:{column}: {message}")


class Lexer:
    """
    Tokenizes EonLang source code.
    
    Supports:
    - All EonLang keywords and operators
    - Integer, float, string, and character literals
    - Comments (single-line and multi-line)
    - Unicode identifiers
    - Full source location tracking
    """
    
    def __init__(self, source: str, filename: str = "<stdin>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        self.start_pos = 0
        self.start_line = 1
        self.start_column = 1
    
    def current_char(self) -> Optional[str]:
        """Get the current character without advancing."""
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]
    
    def peek(self, offset: int = 1) -> Optional[str]:
        """Look ahead at a character."""
        if self.pos + offset >= len(self.source):
            return None
        return self.source[self.pos + offset]
    
    def advance(self) -> str:
        """Consume and return the current character."""
        if self.pos >= len(self.source):
            return '\0'
        
        ch = self.source[self.pos]
        self.pos += 1
        
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        
        return ch
    
    def skip_whitespace(self) -> bool:
        """Skip whitespace except newlines. Returns True if newline was skipped."""
        had_newline = False
        while self.current_char() is not None:
            ch = self.current_char()
            
            if ch == ' ' or ch == '\t' or ch == '\r':
                self.advance()
            elif ch == '\n':
                had_newline = True
                self.advance()
            elif ch == '/':
                if self.peek() == '/':
                    # Single-line comment
                    while self.current_char() is not None and self.current_char() != '\n':
                        self.advance()
                elif self.peek() == '*':
                    # Multi-line comment
                    self.advance()  # skip /
                    self.advance()  # skip *
                    while self.current_char() is not None:
                        if self.current_char() == '*' and self.peek() == '/':
                            self.advance()
                            self.advance()
                            break
                        if self.current_char() == '\n':
                            had_newline = True
                        self.advance()
                else:
                    break
            else:
                break
        
        return had_newline
    
    def read_string(self) -> str:
        """Read a string literal."""
        quote = self.advance()  # Opening quote
        result = []
        
        while self.current_char() is not None and self.current_char() != quote:
            ch = self.advance()
            
            if ch == '\\':
                # Escape sequences
                next_ch = self.advance()
                if next_ch == 'n':
                    result.append('\n')
                elif next_ch == 't':
                    result.append('\t')
                elif next_ch == 'r':
                    result.append('\r')
                elif next_ch == '\\':
                    result.append('\\')
                elif next_ch == '0':
                    result.append('\0')
                elif next_ch == '"':
                    result.append('"')
                elif next_ch == "'":
                    result.append("'")
                elif next_ch == 'u':
                    # Unicode escape: \u{XXXX}
                    if self.current_char() == '{':
                        self.advance()
                        hex_chars = []
                        while self.current_char() != '}':
                            hex_chars.append(self.advance())
                        result.append(chr(int(''.join(hex_chars), 16)))
                else:
                    raise LexerError(f"Unknown escape sequence \\{next_ch}", 
                                   self.line, self.column - 1)
            elif ch == '\n':
                raise LexerError("Unterminated string literal", self.line, self.column - 1)
            else:
                result.append(ch)
        
        if self.current_char() is None:
            raise LexerError("Unterminated string literal", self.start_line, self.start_column)
        
        self.advance()  # Closing quote
        return ''.join(result)
    
    def read_char(self) -> str:
        """Read a character literal."""
        self.advance()  # Opening quote
        ch = self.advance()
        
        if ch == '\\':
            ch = self.advance()
            if ch == 'n':
                ch = '\n'
            elif ch == 't':
                ch = '\t'
            elif ch == 'r':
                ch = '\r'
            elif ch == '0':
                ch = '\0'
        
        if self.current_char() != "'":
            raise LexerError("Multi-character character literal", self.line, self.column)
        
        self.advance()  # Closing quote
        return ch
    
    def read_number(self) -> str:
        """Read a numeric literal."""
        result = []
        is_float = False
        
        while self.current_char() is not None and (
            self.current_char().isdigit() or 
            self.current_char() == '_' or
            (self.current_char() == '.' and self.peek() is not None and self.peek().isdigit())
        ):
            ch = self.current_char()
            if ch == '.':
                if is_float:
                    break
                # Check if it's a range operator or float
                if self.peek() == '.':
                    break
                is_float = True
            result.append(self.advance())
        
        # Handle scientific notation
        if self.current_char() in ('e', 'E'):
            is_float = True
            result.append(self.advance())
            if self.current_char() in ('+', '-'):
                result.append(self.advance())
            while self.current_char() is not None and self.current_char().isdigit():
                result.append(self.advance())
        
        return ''.join(result)
    
    def read_identifier(self) -> str:
        """Read an identifier or keyword."""
        result = []
        
        while self.current_char() is not None and (
            self.current_char().isalnum() or 
            self.current_char() == '_' or
            ord(self.current_char()) > 127  # Unicode support
        ):
            result.append(self.advance())
        
        return ''.join(result)
    
    def make_token(self, token_type: TokenType, value: str) -> Token:
        """Create a token with proper location info."""
        return Token(
            type=token_type,
            value=value,
            line=self.start_line,
            column=self.start_column,
            length=len(value)
        )
    
    def tokenize(self) -> List[Token]:
        """Tokenize the entire source code."""
        self.pos = 0
        self.line = 1
        self.column = 1
        
        while self.pos < len(self.source):
            self.start_pos = self.pos
            self.start_line = self.line
            self.start_column = self.column
            
            had_newline = self.skip_whitespace()
            
            if self.pos >= len(self.source):
                break
            
            ch = self.current_char()
            
            # Handle newlines (if not already skipped)
            if had_newline or ch == '\n':
                if had_newline:
                    self.tokens.append(self.make_token(TokenType.NEWLINE, '\n'))
                continue
            
            # Single-character tokens
            if ch == '(':
                self.advance()
                self.tokens.append(self.make_token(TokenType.LPAREN, '('))
            elif ch == ')':
                self.advance()
                self.tokens.append(self.make_token(TokenType.RPAREN, ')'))
            elif ch == '{':
                self.advance()
                self.tokens.append(self.make_token(TokenType.LBRACE, '{'))
            elif ch == '}':
                self.advance()
                self.tokens.append(self.make_token(TokenType.RBRACE, '}'))
            elif ch == '[':
                self.advance()
                self.tokens.append(self.make_token(TokenType.LBRACKET, '['))
            elif ch == ']':
                self.advance()
                self.tokens.append(self.make_token(TokenType.RBRACKET, ']'))
            elif ch == ',':
                self.advance()
                self.tokens.append(self.make_token(TokenType.COMMA, ','))
            elif ch == ';':
                self.advance()
                self.tokens.append(self.make_token(TokenType.SEMICOLON, ';'))
            elif ch == ':':
                self.advance()
                if self.current_char() == ':':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.COLON_COLON, '::'))
                else:
                    self.tokens.append(self.make_token(TokenType.COLON, ':'))
            elif ch == '_':
                self.advance()
                self.tokens.append(self.make_token(TokenType.UNDERSCORE, '_'))
            elif ch == '?':
                self.advance()
                self.tokens.append(self.make_token(TokenType.QUESTION, '?'))
            elif ch == '~':
                self.advance()
                self.tokens.append(self.make_token(TokenType.TILDE, '~'))
            
            # Two-character tokens
            elif ch == '.':
                self.advance()
                if self.current_char() == '.':
                    self.advance()
                    if self.current_char() == '.':
                        self.advance()
                        self.tokens.append(self.make_token(TokenType.DOTDOTDOT, '...'))
                    else:
                        self.tokens.append(self.make_token(TokenType.DOTDOT, '..'))
                else:
                    self.tokens.append(self.make_token(TokenType.DOT, '.'))
            
            elif ch == '+':
                self.advance()
                if self.current_char() == '+':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.PLUS_PLUS, '++'))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.PLUS_ASSIGN, '+='))
                else:
                    self.tokens.append(self.make_token(TokenType.PLUS, '+'))
            
            elif ch == '-':
                self.advance()
                if self.current_char() == '-':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.MINUS_MINUS, '--'))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.MINUS_ASSIGN, '-='))
                elif self.current_char() == '>':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.ARROW, '->'))
                else:
                    self.tokens.append(self.make_token(TokenType.MINUS, '-'))
            
            elif ch == '*':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.STAR_ASSIGN, '*='))
                else:
                    self.tokens.append(self.make_token(TokenType.STAR, '*'))
            
            elif ch == '/':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.SLASH_ASSIGN, '/='))
                else:
                    self.tokens.append(self.make_token(TokenType.SLASH, '/'))
            
            elif ch == '%':
                self.advance()
                self.tokens.append(self.make_token(TokenType.PERCENT, '%'))
            
            elif ch == '^':
                self.advance()
                self.tokens.append(self.make_token(TokenType.CARET, '^'))
            
            elif ch == '~':
                self.advance()
                self.tokens.append(self.make_token(TokenType.TILDE, '~'))
            
            # Comparison operators
            elif ch == '=':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.EQ, '=='))
                elif self.current_char() == '>':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.FAT_ARROW, '=>'))
                else:
                    self.tokens.append(self.make_token(TokenType.ASSIGN, '='))
            
            elif ch == '!':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.NE, '!='))
                else:
                    self.tokens.append(self.make_token(TokenType.BANG, '!'))
            
            elif ch == '<':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.LE, '<='))
                elif self.current_char() == '<':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.SHL, '<<'))
                else:
                    self.tokens.append(self.make_token(TokenType.LT, '<'))
            
            elif ch == '>':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.GE, '>='))
                elif self.current_char() == '>':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.SHR, '>>'))
                else:
                    self.tokens.append(self.make_token(TokenType.GT, '>'))
            
            # Logical operators
            elif ch == '&':
                self.advance()
                if self.current_char() == '&':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.AND, '&&'))
                else:
                    self.tokens.append(self.make_token(TokenType.AMPERSAND, '&'))
            
            elif ch == '|':
                self.advance()
                if self.current_char() == '|':
                    self.advance()
                    self.tokens.append(self.make_token(TokenType.OR, '||'))
                else:
                    self.tokens.append(self.make_token(TokenType.PIPE, '|'))
            
            # String literal
            elif ch == '"':
                value = self.read_string()
                self.tokens.append(self.make_token(TokenType.STRING, value))
            
            # Character literal
            elif ch == "'":
                value = self.read_char()
                self.tokens.append(self.make_token(TokenType.CHAR, value))
            
            # Number literal
            elif ch.isdigit():
                value = self.read_number()
                if '.' in value or 'e' in value or 'E' in value:
                    self.tokens.append(self.make_token(TokenType.FLOAT, value))
                else:
                    self.tokens.append(self.make_token(TokenType.INTEGER, value))
            
            # Identifier or keyword
            elif ch.isalpha() or ch == '_' or ord(ch) > 127:
                value = self.read_identifier()
                
                # Check for keywords
                if value in KEYWORDS:
                    self.tokens.append(self.make_token(KEYWORDS[value], value))
                else:
                    self.tokens.append(self.make_token(TokenType.IDENTIFIER, value))
            
            else:
                raise LexerError(f"Unexpected character '{ch}'", self.line, self.column)
        
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column))
        return self.tokens
