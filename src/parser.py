"""
Recursive-descent parser for EonLang.
"""

from typing import List, Optional, Dict
from .tokens import Token, TokenType, KEYWORDS
from .ast import *


class ParseError(Exception):
    """Raised when the parser encounters a syntax error."""
    def __init__(self, message: str, token: Token):
        self.message = message
        self.token = token
        super().__init__(f"Parse error at {token.line}:{token.column}: {message}")


class Parser:
    """
    Recursive-descent parser for EonLang.
    
    Grammar (simplified):
        program     := item*
        item        := fn | struct | enum | trait | impl | use | mod | type
        fn          := 'fn' ident '(' params? ')' ('->' type)? block
        struct      := 'struct' ident generic_params? '{' struct_field* '}'
        enum        := 'enum' ident generic_params? '{' enum_variant* '}'
        trait       := 'trait' ident generic_params? '{' trait_method* '}'
        impl        := 'impl' generic_params? type ('for' type)? '{' fn* '}'
        block       := '{' stmt* expr? '}'
        stmt        := let | expr_stmt | if | match | loop | while | for | return
        let         := 'let' ('mut')? ident (':' type)? '=' expr
        expr_stmt   := expr (';' | newline)
        if          := 'if' expr block ('else' (if | block))?
        match       := 'match' expr '{' match_arm* '}'
        loop        := 'loop' block
        while       := 'while' expr block
        for         := 'for' ident 'in' expr block
        return      := 'return' expr?
        expr        := assign
        assign      := logic_or ('=' assign)?
        logic_or    := logic_and ('||' logic_and)*
        logic_and   := equality ('&&' equality)*
        equality    := comparison (('==' | '!=') comparison)*
        comparison  := term (('<' | '>' | '<=' | '>=') term)*
        term        := factor (('+' | '-') factor)*
        factor      := unary (('*' | '/' | '%') unary)*
        unary       := ('-' | '!' | '&' | '&mut' | '*') unary | call
        call        := primary ('(' args? ')' | '.' ident | '[' expr ']')*
        primary     := literal | ident | '(' expr ')' | block | if | match | loop
        literal     := int | float | string | char | bool
    """
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.scope_depth = 0
        self.loop_depth = 0
        self.function_depth = 0
    
    @property
    def current(self) -> Token:
        """Get the current token."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF
    
    def peek(self, offset: int = 1) -> Token:
        """Look ahead at a token."""
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]
    
    def advance(self) -> Token:
        """Consume and return the current token."""
        token = self.current
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token
    
    def check(self, token_type: TokenType) -> bool:
        """Check if the current token is of a given type."""
        return self.current.type == token_type
    
    def check_keyword(self, keyword: str) -> bool:
        """Check if the current token is a keyword."""
        return self.current.type == KEYWORDS.get(keyword)
    
    def match(self, *token_types: TokenType) -> bool:
        """Match one of the given token types."""
        for token_type in token_types:
            if self.check(token_type):
                self.advance()
                return True
        return False
    
    def match_keyword(self, *keywords: str) -> bool:
        """Match one of the given keywords."""
        for keyword in keywords:
            if self.check_keyword(keyword):
                self.advance()
                return True
        return False
    
    def expect(self, token_type: TokenType, message: str) -> Token:
        """Expect a token type and error if not found."""
        if self.check(token_type):
            return self.advance()
        raise ParseError(message, self.current)
    
    def expect_keyword(self, keyword: str) -> Token:
        """Expect a keyword and error if not found."""
        if self.check_keyword(keyword):
            return self.advance()
        raise ParseError(f"Expected '{keyword}'", self.current)
    
    def skip_newlines(self):
        """Skip optional newlines."""
        while self.match(TokenType.NEWLINE):
            pass
    
    def make_span(self, start: Token, end: Token) -> Span:
        """Create a source span from two tokens."""
        return Span(start.line, start.column, end.line, end.column, start.value)
    
    # ==================== TOP LEVEL ====================
    
    def parse_source_file(self) -> SourceFile:
        """Parse a complete source file."""
        items = []
        start = self.current
        
        while not self.check(TokenType.EOF):
            self.skip_newlines()
            if self.check(TokenType.EOF):
                break
            
            try:
                item = self.parse_item()
                if item:
                    items.append(item)
            except ParseError as e:
                # Recovery: skip to next item
                print(f"Warning: {e}")
                while not self.check(TokenType.EOF) and not self.check(TokenType.NEWLINE):
                    self.advance()
                self.advance()  # Skip newline
        
        return SourceFile(items=items, span=self.make_span(start, self.current))
    
    def parse_item(self) -> Optional[Node]:
        """Parse a top-level item."""
        self.skip_newlines()
        
        is_public = self.match(TokenType.PUB)
        
        if self.check_keyword('fn'):
            return self.parse_function(is_public)
        elif self.check_keyword('struct'):
            return self.parse_struct(is_public)
        elif self.check_keyword('enum'):
            return self.parse_enum(is_public)
        elif self.check_keyword('trait'):
            return self.parse_trait(is_public)
        elif self.check_keyword('impl'):
            return self.parse_impl()
        elif self.check_keyword('type'):
            return self.parse_type_alias(is_public)
        elif self.check_keyword('mod'):
            return self.parse_module(is_public)
        elif self.check_keyword('use'):
            return self.parse_use(is_public)
        elif self.check(TokenType.NEWLINE) or self.check(TokenType.SEMICOLON):
            self.advance()
            return None
        else:
            # Try parsing as expression statement at top level
            expr = self.parse_expr()
            self.skip_newlines()
            return ExprStmt(expr=expr)
    
    # ==================== FUNCTIONS ====================
    
    def parse_function(self, is_public: bool = False) -> FuncStmt:
        """Parse a function declaration."""
        start = self.expect_keyword('fn')
        
        name = self.expect(TokenType.IDENTIFIER, "Expected function name").value
        type_params = self.parse_generic_params()
        
        self.expect(TokenType.LPAREN, "Expected '(' after function name")
        params = self.parse_fn_params()
        self.expect(TokenType.RPAREN, "Expected ')' after parameters")
        
        return_type = Type(TypeKind.UNIT)
        if self.match(TokenType.ARROW):
            return_type = self.parse_type()
        
        func = FuncStmt(
            name=name,
            params=params,
            return_type=return_type,
            type_params=type_params,
            is_public=is_public,
            span=self.make_span(start, self.current)
        )
        
        # Check for extern
        if self.check(TokenType.SEMICOLON):
            self.advance()
            func.is_extern = True
        else:
            func.body = self.parse_block()
        
        return func
    
    def parse_fn_params(self) -> List[tuple]:
        """Parse function parameters."""
        params = []
        
        if self.check(TokenType.RPAREN):
            return params
        
        while True:
            is_mutable = self.match_keyword('mut')
            name = self.expect(TokenType.IDENTIFIER, "Expected parameter name").value
            
            self.expect(TokenType.COLON, "Expected ':' after parameter name")
            param_type = self.parse_type()
            
            params.append((name, param_type, is_mutable))
            
            if not self.match(TokenType.COMMA):
                break
        
        return params
    
    def parse_generic_params(self) -> List[str]:
        """Parse generic type parameters."""
        params = []
        
        if self.match(TokenType.LT):
            while True:
                if self.check(TokenType.IDENTIFIER):
                    params.append(self.advance().value)
                elif self.match(TokenType.QUESTION):
                    params.append("_")
                else:
                    break
                
                if not self.match(TokenType.COMMA):
                    break
            
            self.expect(TokenType.GT, "Expected '>' after generic parameters")
        
        return params
    
    # ==================== TYPES ====================
    
    def parse_type(self) -> Type:
        """Parse a type."""
        return self.parse_type_with_binding(0)
    
    def parse_type_with_binding(self, min_prec: int) -> Type:
        """Parse types with precedence for generics."""
        base_type = self.parse_type_base()
        
        # Handle generic parameters
        while True:
            if self.check(TokenType.LT):
                self.advance()
                args = []
                while True:
                    args.append(self.parse_type())
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.GT, "Expected '>' after type arguments")
                base_type = Type(
                    kind=TypeKind.GENERIC,
                    name=base_type.name,
                    generic_params=args
                )
            elif self.check(TokenType.QUESTION):
                # Optional type (like Option<T>)
                self.advance()
                base_type = Type(
                    kind=TypeKind.GENERIC,
                    name="Option",
                    generic_params=[base_type]
                )
            else:
                break
        
        # Handle reference types
        while True:
            if self.match(TokenType.AMPERSAND):
                is_mut = self.match_keyword('mut')
                lifetime = None
                if self.check(TokenType.IDENTIFIER) and not self.check_keyword('mut'):
                    lifetime = self.advance().value
                
                ref_type = self.parse_type_base()
                ref_type = Type(
                    kind=TypeKind.REFERENCE,
                    generic_params=[ref_type],
                    is_mutable=is_mut,
                    lifetime=lifetime
                )
                base_type = ref_type
            elif self.match(TokenType.STAR):
                is_mut = self.match_keyword('mut')
                pointee = self.parse_type()
                base_type = Type(
                    kind=TypeKind.POINTER,
                    generic_params=[pointee],
                    is_mutable=is_mut
                )
            else:
                break
        
        # Handle array/slice types
        if self.match(TokenType.LBRACKET):
            elem_type = base_type
            if self.match(TokenType.SEMICOLON):
                size_expr = self.parse_expr()
                self.expect(TokenType.RBRACKET, "Expected ']' after array size")
                base_type = Type(kind=TypeKind.ARRAY, fields={'size': size_expr})
                base_type.generic_params = [elem_type]
            else:
                self.expect(TokenType.RBRACKET, "Expected ']' after [")
                base_type = Type(kind=TypeKind.REFERENCE, generic_params=[elem_type])
                base_type.name = "slice"
        
        return base_type
    
    def parse_type_base(self) -> Type:
        """Parse a base type (no operators)."""
        if self.check(TokenType.IDENTIFIER):
            name = self.advance().value
            return Type(kind=TypeKind.STRUCT, name=name)
        
        if self.match_keyword('fn'):
            return self.parse_fn_type()
        
        if self.match(TokenType.LPAREN):
            return self.parse_tuple_type()
        
        if self.match(TokenType.LBRACKET):
            elem_type = self.parse_type()
            self.expect(TokenType.RBRACKET, "Expected ']'")
            return Type(kind=TypeKind.ARRAY, generic_params=[elem_type])
        
        # Primitive types
        if self.check_keyword('i8'): return Type(kind=TypeKind.INT, name='i8', size=1)
        if self.check_keyword('i16'): return Type(kind=TypeKind.INT, name='i16', size=2)
        if self.check_keyword('i32'): return Type(kind=TypeKind.INT, name='i32', size=4)
        if self.check_keyword('i64'): return Type(kind=TypeKind.INT, name='i64', size=8)
        if self.check_keyword('i128'): return Type(kind=TypeKind.INT, name='i128', size=16)
        if self.check_keyword('isize'): return Type(kind=TypeKind.INT, name='isize', size=8)
        
        if self.check_keyword('u8'): return Type(kind=TypeKind.UINT, name='u8', size=1)
        if self.check_keyword('u16'): return Type(kind=TypeKind.UINT, name='u16', size=2)
        if self.check_keyword('u32'): return Type(kind=TypeKind.UINT, name='u32', size=4)
        if self.check_keyword('u64'): return Type(kind=TypeKind.UINT, name='u64', size=8)
        if self.check_keyword('u128'): return Type(kind=TypeKind.UINT, name='u128', size=16)
        if self.check_keyword('usize'): return Type(kind=TypeKind.UINT, name='usize', size=8)
        
        if self.check_keyword('f32'): return Type(kind=TypeKind.FLOAT, name='f32', size=4)
        if self.check_keyword('f64'): return Type(kind=TypeKind.DOUBLE, name='f64', size=8)
        
        if self.check_keyword('bool'): return Type(kind=TypeKind.BOOL, name='bool')
        if self.check_keyword('char'): return Type(kind=TypeKind.CHAR, name='char')
        if self.check_keyword('str'): return Type(kind=TypeKind.STRING, name='str')
        
        if self.check_keyword('void') or self.check_keyword('unit'):
            return Type(kind=TypeKind.UNIT, name='void')
        
        if self.check_keyword('never'):
            return Type(kind=TypeKind.NEVER, name='!')
        
        if self.match(TokenType.UNDERSCORE):
            return Type(kind=TypeKind.UNKNOWN)
        
        if self.match(TokenType.TILDE):
            self.expect(TokenType.LT, "Expected '<' after '~'")
            type_param = self.parse_type()
            self.expect(TokenType.GT, "Expected '>'")
            return Type(kind=TypeKind.REFERENCE, name='Owned', generic_params=[type_param])
        
        raise ParseError(f"Expected type, found {self.current.type.name}", self.current)
    
    def parse_fn_type(self) -> Type:
        """Parse a function type."""
        self.expect(TokenType.LPAREN, "Expected '(' after 'fn'")
        
        params = []
        if not self.check(TokenType.RPAREN):
            while True:
                params.append(self.parse_type())
                if not self.match(TokenType.COMMA):
                    break
        
        self.expect(TokenType.RPAREN, "Expected ')' after parameter types")
        
        ret_type = Type(TypeKind.UNIT)
        if self.match(TokenType.ARROW):
            ret_type = self.parse_type()
        
        return Type(kind=TypeKind.FUNCTION, generic_params=[*params, ret_type])
    
    def parse_tuple_type(self) -> Type:
        """Parse a tuple type."""
        fields = []
        
        if not self.check(TokenType.RPAREN):
            while True:
                fields.append(self.parse_type())
                if not self.match(TokenType.COMMA):
                    break
        
        self.expect(TokenType.RPAREN, "Expected ')'")
        return Type(kind=TypeKind.TUPLE, generic_params=fields)
    
    # ==================== STRUCTS, ENUMS, TRAITS ====================
    
    def parse_struct(self, is_public: bool) -> StructStmt:
        """Parse a struct declaration."""
        start = self.expect_keyword('struct')
        name = self.expect(TokenType.IDENTIFIER, "Expected struct name").value
        
        type_params = self.parse_generic_params()
        
        self.expect(TokenType.LBRACE, "Expected '{' after struct name")
        
        fields = []
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            field_public = self.match(TokenType.PUB)
            field_name = self.expect(TokenType.IDENTIFIER, "Expected field name").value
            self.expect(TokenType.COLON, "Expected ':' after field name")
            field_type = self.parse_type()
            self.expect(TokenType.SEMICOLON, "Expected ';' after field type")
            
            fields.append((field_name, field_type, field_public))
            self.skip_newlines()
        
        self.expect(TokenType.RBRACE, "Expected '}' after struct body")
        
        return StructStmt(
            name=name,
            fields=fields,
            type_params=type_params,
            is_public=is_public,
            span=self.make_span(start, self.current)
        )
    
    def parse_enum(self, is_public: bool) -> EnumStmt:
        """Parse an enum declaration."""
        start = self.expect_keyword('enum')
        name = self.expect(TokenType.IDENTIFIER, "Expected enum name").value
        
        type_params = self.parse_generic_params()
        
        self.expect(TokenType.LBRACE, "Expected '{' after enum name")
        
        variants = []
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            var_name = self.expect(TokenType.IDENTIFIER, "Expected variant name").value
            
            # Check for tuple variant
            variant_types = []
            if self.match(TokenType.LPAREN):
                while not self.check(TokenType.RPAREN):
                    variant_types.append(self.parse_type())
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RPAREN, "Expected ')'")
            
            # Check for struct variant
            variant_fields = []
            if self.match(TokenType.LBRACE):
                while not self.check(TokenType.RBRACE):
                    field_name = self.expect(TokenType.IDENTIFIER, "Expected field name").value
                    self.expect(TokenType.COLON, "Expected ':'")
                    field_type = self.parse_type()
                    variant_fields.append((field_name, field_type))
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RBRACE, "Expected '}'")
            
            if variant_types:
                variants.append((var_name, variant_types))
            elif variant_fields:
                variants.append((var_name, dict(variant_fields)))
            else:
                variants.append((var_name, None))
            
            self.match(TokenType.COMMA)
            self.skip_newlines()
        
        self.expect(TokenType.RBRACE, "Expected '}' after enum body")
        
        return EnumStmt(
            name=name,
            variants=variants,
            type_params=type_params,
            is_public=is_public,
            span=self.make_span(start, self.current)
        )
    
    def parse_trait(self, is_public: bool) -> TraitStmt:
        """Parse a trait declaration."""
        start = self.expect_keyword('trait')
        name = self.expect(TokenType.IDENTIFIER, "Expected trait name").value
        
        type_params = self.parse_generic_params()
        
        self.expect(TokenType.LBRACE, "Expected '{' after trait name")
        
        methods = []
        associated_types = {}
        
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            if self.check_keyword('type'):
                self.advance()
                type_name = self.expect(TokenType.IDENTIFIER, "Expected type name").value
                default_type = None
                if self.match(TokenType.ASSIGN):
                    default_type = self.parse_type()
                self.expect(TokenType.SEMICOLON, "Expected ';' after associated type")
                associated_types[type_name] = default_type
            elif self.check_keyword('fn'):
                methods.append(self.parse_function(is_public=True))
            else:
                raise ParseError("Expected trait method or associated type", self.current)
        
        self.expect(TokenType.RBRACE, "Expected '}' after trait body")
        
        return TraitStmt(
            name=name,
            methods=methods,
            associated_types=associated_types,
            type_params=type_params,
            is_public=is_public,
            span=self.make_span(start, self.current)
        )
    
    def parse_impl(self) -> ImplStmt:
        """Parse an impl block."""
        start = self.expect_keyword('impl')
        
        type_params = self.parse_generic_params()
        
        trait_name = None
        if self.check(TokenType.IDENTIFIER):
            trait_name = self.advance().value
            self.expect_keyword('for')
        
        type_name = self.expect(TokenType.IDENTIFIER, "Expected type name").value
        
        self.expect(TokenType.LBRACE, "Expected '{' after impl type")
        
        methods = []
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            if self.check_keyword('fn'):
                methods.append(self.parse_function())
            elif self.check_keyword('type'):
                # Default method implementation for associated type
                self.advance()
                type_name_local = self.expect(TokenType.IDENTIFIER, "Expected type name").value
                self.expect(TokenType.ASSIGN, "Expected '='")
                type_val = self.parse_type()
                self.expect(TokenType.SEMICOLON, "Expected ';'")
            else:
                raise ParseError("Expected method declaration", self.current)
        
        self.expect(TokenType.RBRACE, "Expected '}' after impl body")
        
        return ImplStmt(
            type_params=type_params,
            trait_name=trait_name,
            type_name=type_name,
            methods=methods,
            span=self.make_span(start, self.current)
        )
    
    def parse_type_alias(self, is_public: bool) -> TypeStmt:
        """Parse a type alias."""
        start = self.expect_keyword('type')
        name = self.expect(TokenType.IDENTIFIER, "Expected type name").value
        
        type_params = self.parse_generic_params()
        
        self.expect(TokenType.ASSIGN, "Expected '=' after type name")
        value = self.parse_type()
        self.expect(TokenType.SEMICOLON, "Expected ';'")
        
        return TypeStmt(
            name=name,
            type_params=type_params,
            value=value,
            is_public=is_public,
            span=self.make_span(start, self.current)
        )
    
    def parse_module(self, is_public: bool) -> ModStmt:
        """Parse a module declaration."""
        start = self.expect_keyword('mod')
        name = self.expect(TokenType.IDENTIFIER, "Expected module name").value
        
        if self.match(TokenType.SEMICOLON):
            return ModStmt(name=name, is_public=is_public, span=self.make_span(start, self.current))
        
        self.expect(TokenType.LBRACE, "Expected '{' after module name")
        
        items = []
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            item = self.parse_item()
            if item:
                items.append(item)
        
        self.expect(TokenType.RBRACE, "Expected '}' after module body")
        
        return ModStmt(
            name=name,
            items=items,
            is_public=is_public,
            span=self.make_span(start, self.current)
        )
    
    def parse_use(self, is_public: bool) -> UseStmt:
        """Parse a use statement."""
        start = self.advance()
        
        path = []
        while True:
            path.append(self.expect(TokenType.IDENTIFIER, "Expected identifier in path").value)
            if self.match(TokenType.COLON_COLON):
                path.append(self.advance().value)
                if not self.check(TokenType.IDENTIFIER):
                    path.append(self.advance().value)
            else:
                break
        
        path_str = '::'.join(path)
        
        alias = None
        if self.match_keyword('as'):
            alias = self.expect(TokenType.IDENTIFIER, "Expected alias name").value
        
        self.expect(TokenType.SEMICOLON, "Expected ';'")
        
        return UseStmt(path=path_str, alias=alias, is_public=is_public)
    
    # ==================== STATEMENTS ====================
    
    def parse_stmt(self) -> Optional[Stmt]:
        """Parse a statement."""
        self.skip_newlines()
        
        if self.check_keyword('let'):
            return self.parse_let()
        elif self.check_keyword('if'):
            return self.parse_if()
        elif self.check_keyword('match'):
            return self.parse_match()
        elif self.check_keyword('loop'):
            return self.parse_loop()
        elif self.check_keyword('while'):
            return self.parse_while()
        elif self.check_keyword('for'):
            return self.parse_for()
        elif self.check_keyword('return'):
            return self.parse_return()
        elif self.check_keyword('break'):
            return self.parse_break()
        elif self.check_keyword('continue'):
            return self.parse_continue()
        elif self.check(TokenType.LBRACE):
            return ExprStmt(expr=self.parse_block_expr())
        elif self.check(TokenType.SEMICOLON):
            self.advance()
            return EmptyStmt()
        else:
            expr = self.parse_expr()
            self.skip_newlines()
            if self.check(TokenType.ASSIGN) or self.check(TokenType.PLUS_ASSIGN) or \
               self.check(TokenType.MINUS_ASSIGN) or self.check(TokenType.STAR_ASSIGN) or \
               self.check(TokenType.SLASH_ASSIGN):
                op = self.advance().value
                value = self.parse_expr()
                self.skip_newlines()
                return AssignStmt(target=expr, op=op, value=value)
            return ExprStmt(expr=expr)
    
    def parse_let(self) -> LetStmt:
        """Parse a let statement."""
        start = self.expect_keyword('let')
        
        is_mutable = self.match_keyword('mut')
        
        name = self.expect(TokenType.IDENTIFIER, "Expected variable name").value
        
        type_annotation = None
        if self.match(TokenType.COLON):
            type_annotation = self.parse_type()
        
        value = None
        if self.match(TokenType.ASSIGN):
            value = self.parse_expr()
        
        self.skip_newlines()
        self.expect(TokenType.SEMICOLON, "Expected ';'")
        
        return LetStmt(
            name=name,
            type_annotation=type_annotation,
            value=value,
            is_mutable=is_mutable,
            span=self.make_span(start, self.current)
        )
    
    def parse_if(self) -> IfExpr:
        """Parse an if expression/statement."""
        start = self.expect_keyword('if')
        
        condition = self.parse_expr()
        then_block = self.parse_block()
        
        else_block = None
        else_ifs = []
        
        if self.match_keyword('else'):
            if self.check_keyword('if'):
                else_if = self.parse_if()
                else_ifs.append(else_if)
            else:
                else_block = self.parse_block()
        
        return IfExpr(
            condition=condition,
            then_block=then_block,
            else_block=else_block,
            else_if=else_ifs
        )
    
    def parse_match(self) -> MatchExpr:
        """Parse a match expression."""
        self.expect_keyword('match')
        
        value = self.parse_expr()
        self.expect(TokenType.LBRACE, "Expected '{' after match value")
        
        arms = []
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            pattern = self.parse_pattern()
            
            if self.match(TokenType.FAT_ARROW):
                body = self.parse_expr()
            else:
                body = self.parse_block()
            
            arms.append(MatchArm(pattern=pattern, body=body))
            self.match(TokenType.COMMA)
            self.skip_newlines()
        
        self.expect(TokenType.RBRACE, "Expected '}' after match arms")
        
        return MatchExpr(value=value, arms=arms)
    
    def parse_pattern(self) -> Pattern:
        """Parse a pattern."""
        if self.match(TokenType.UNDERSCORE):
            return Pattern(kind='wildcard')
        
        if self.check(TokenType.INTEGER):
            value = self.advance().value
            return Pattern(kind='literal', value=int(value))
        
        if self.check(TokenType.STRING):
            value = self.advance().value
            return Pattern(kind='literal', value=value)
        
        if self.check(TokenType.BOOL):
            value = self.advance().value == 'true'
            return Pattern(kind='literal', value=value)
        
        if self.match(TokenType.LPAREN):
            patterns = []
            while not self.check(TokenType.RPAREN):
                patterns.append(self.parse_pattern())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RPAREN, "Expected ')'")
            return Pattern(kind='tuple', subpatterns=patterns)
        
        if self.match(TokenType.LBRACKET):
            patterns = []
            while not self.check(TokenType.RBRACKET):
                patterns.append(self.parse_pattern())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACKET, "Expected ']'")
            return Pattern(kind='array', subpatterns=patterns)
        
        if self.check(TokenType.IDENTIFIER):
            name = self.advance().value
            
            # Check for enum variant
            if self.match(TokenType.LPAREN):
                subpatterns = []
                while not self.check(TokenType.RPAREN):
                    subpatterns.append(self.parse_pattern())
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RPAREN, "Expected ')'")
                return Pattern(kind='variant', value=name, subpatterns=subpatterns)
            
            # Check for record pattern
            if self.match(TokenType.LBRACE):
                fields = []
                while not self.check(TokenType.RBRACE):
                    field_name = self.expect(TokenType.IDENTIFIER, "Expected field name").value
                    if self.match(TokenType.COLON):
                        subpattern = self.parse_pattern()
                    else:
                        subpattern = Pattern(kind='bind', binding=field_name)
                        field_name = subpattern.binding
                    fields.append((field_name, subpattern))
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RBRACE, "Expected '}'")
                return Pattern(kind='struct', value=name, subpatterns=fields)
            
            return Pattern(kind='bind', value=name, binding=name)
        
        raise ParseError("Expected pattern", self.current)
    
    def parse_loop(self) -> LoopExpr:
        """Parse a loop expression."""
        start = self.expect_keyword('loop')
        self.loop_depth += 1
        body = self.parse_block()
        self.loop_depth -= 1
        return LoopExpr(body=body)
    
    def parse_while(self) -> WhileExpr:
        """Parse a while expression."""
        self.expect_keyword('while')
        condition = self.parse_expr()
        self.loop_depth += 1
        body = self.parse_block()
        self.loop_depth -= 1
        return WhileExpr(condition=condition, body=body)
    
    def parse_for(self) -> ForExpr:
        """Parse a for loop."""
        self.expect_keyword('for')
        variable = self.expect(TokenType.IDENTIFIER, "Expected variable name").value
        self.expect_keyword('in')
        iterable = self.parse_expr()
        self.loop_depth += 1
        body = self.parse_block()
        self.loop_depth -= 1
        return ForExpr(variable=variable, iterable=iterable, body=body)
    
    def parse_return(self) -> ReturnStmt:
        """Parse a return statement."""
        start = self.expect_keyword('return')
        
        value = None
        if not self.check(TokenType.SEMICOLON) and not self.check(TokenType.NEWLINE) and \
           not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            value = self.parse_expr()
        
        self.skip_newlines()
        return ReturnStmt(value=value)
    
    def parse_break(self) -> BreakStmt:
        """Parse a break statement."""
        start = self.expect_keyword('break')
        value = None
        label = None
        
        if not self.check(TokenType.SEMICOLON) and not self.check(TokenType.NEWLINE):
            if self.check(TokenType.IDENTIFIER):
                label = self.advance().value
            else:
                value = self.parse_expr()
        
        self.skip_newlines()
        return BreakStmt(value=value, label=label)
    
    def parse_continue(self) -> ContinueStmt:
        """Parse a continue statement."""
        start = self.expect_keyword('continue')
        label = None
        
        if self.check(TokenType.IDENTIFIER):
            label = self.advance().value
        
        self.skip_newlines()
        return ContinueStmt(label=label)
    
    def parse_block(self) -> Block:
        """Parse a block expression."""
        return self.parse_block_expr()
    
    def parse_block_expr(self) -> Block:
        """Parse a block expression (explicit)."""
        start = self.expect(TokenType.LBRACE, "Expected '{'")
        
        self.scope_depth += 1
        stmts = []
        
        while not self.check(TokenType.RBRACE):
            self.skip_newlines()
            if self.check(TokenType.RBRACE):
                break
            
            stmt = self.parse_stmt()
            if stmt:
                stmts.append(stmt)
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        self.scope_depth -= 1
        
        # Check for trailing expression
        expr = None
        if stmts and isinstance(stmts[-1], ExprStmt):
            trailing = stmts.pop()
            expr = trailing.expr
        
        return Block(stmts=stmts, expr=expr, scope_id=self.scope_depth)
    
    # ==================== EXPRESSIONS ====================
    
    def parse_expr(self) -> Expr:
        """Parse an expression."""
        return self.parse_assign()
    
    def parse_assign(self) -> Expr:
        """Parse an assignment expression."""
        expr = self.parse_or()
        
        if self.match(TokenType.ASSIGN):
            value = self.parse_assign()
            return AssignStmt(target=expr, value=value)
        elif self.match(TokenType.PLUS_ASSIGN):
            value = self.parse_assign()
            return BinaryExpr(op=BinaryOp.ADD, left=expr, right=value)
        elif self.match(TokenType.MINUS_ASSIGN):
            value = self.parse_assign()
            return BinaryExpr(op=BinaryOp.SUB, left=expr, right=value)
        elif self.match(TokenType.STAR_ASSIGN):
            value = self.parse_assign()
            return BinaryExpr(op=BinaryOp.MUL, left=expr, right=value)
        elif self.match(TokenType.SLASH_ASSIGN):
            value = self.parse_assign()
            return BinaryExpr(op=BinaryOp.DIV, left=expr, right=value)
        
        return expr
    
    def parse_or(self) -> Expr:
        """Parse a logical OR expression."""
        left = self.parse_and()
        
        while self.match(TokenType.OR):
            right = self.parse_and()
            left = BinaryExpr(op=BinaryOp.OR, left=left, right=right)
        
        return left
    
    def parse_and(self) -> Expr:
        """Parse a logical AND expression."""
        left = self.parse_bitwise_or()
        
        while self.match(TokenType.AND):
            right = self.parse_bitwise_or()
            left = BinaryExpr(op=BinaryOp.AND, left=left, right=right)
        
        return left
    
    def parse_bitwise_or(self) -> Expr:
        """Parse a bitwise OR expression."""
        left = self.parse_bitwise_xor()
        
        while self.match(TokenType.PIPE):
            right = self.parse_bitwise_xor()
            left = BinaryExpr(op=BinaryOp.OR, left=left, right=right)
        
        return left
    
    def parse_bitwise_xor(self) -> Expr:
        """Parse a bitwise XOR expression."""
        left = self.parse_bitwise_and()
        
        while self.match(TokenType.CARET):
            right = self.parse_bitwise_and()
            left = BinaryExpr(op=BinaryOp.XOR, left=left, right=right)
        
        return left
    
    def parse_bitwise_and(self) -> Expr:
        """Parse a bitwise AND expression."""
        left = self.parse_shift()
        
        while self.match(TokenType.AMPERSAND):
            right = self.parse_shift()
            left = BinaryExpr(op=BinaryOp.AND, left=left, right=right)
        
        return left
    
    def parse_shift(self) -> Expr:
        """Parse shift expressions."""
        left = self.parse_comparison()
        
        while True:
            if self.match(TokenType.SHL):
                right = self.parse_comparison()
                left = BinaryExpr(op=BinaryOp.SHL, left=left, right=right)
            elif self.match(TokenType.SHR):
                right = self.parse_comparison()
                left = BinaryExpr(op=BinaryOp.SHR, left=left, right=right)
            else:
                break
        
        return left
    
    def parse_comparison(self) -> Expr:
        """Parse comparison expressions."""
        left = self.parse_term()
        
        while True:
            if self.match(TokenType.EQ):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.EQ, left=left, right=right)
            elif self.match(TokenType.NE):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.NE, left=left, right=right)
            elif self.match(TokenType.LT):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.LT, left=left, right=right)
            elif self.match(TokenType.GT):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.GT, left=left, right=right)
            elif self.match(TokenType.LE):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.LE, left=left, right=right)
            elif self.match(TokenType.GE):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.GE, left=left, right=right)
            else:
                break
        
        return left
    
    def parse_term(self) -> Expr:
        """Parse addition/subtraction."""
        left = self.parse_factor()
        
        while True:
            if self.match(TokenType.PLUS):
                right = self.parse_factor()
                left = BinaryExpr(op=BinaryOp.ADD, left=left, right=right)
            elif self.match(TokenType.MINUS):
                right = self.parse_factor()
                left = BinaryExpr(op=BinaryOp.SUB, left=left, right=right)
            else:
                break
        
        return left
    
    def parse_factor(self) -> Expr:
        """Parse multiplication/division."""
        left = self.parse_unary()
        
        while True:
            if self.match(TokenType.STAR):
                right = self.parse_unary()
                left = BinaryExpr(op=BinaryOp.MUL, left=left, right=right)
            elif self.match(TokenType.SLASH):
                right = self.parse_unary()
                left = BinaryExpr(op=BinaryOp.DIV, left=left, right=right)
            elif self.match(TokenType.PERCENT):
                right = self.parse_unary()
                left = BinaryExpr(op=BinaryOp.REM, left=left, right=right)
            else:
                break
        
        return left
    
    def parse_unary(self) -> Expr:
        """Parse unary expressions."""
        if self.match(TokenType.MINUS):
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.NEG, operand=operand)
        
        if self.match(TokenType.BANG):
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.NOT, operand=operand)
        
        if self.match(TokenType.TILDE):
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.BITNOT, operand=operand)
        
        if self.match(TokenType.AMPERSAND):
            is_mut = self.match_keyword('mut')
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.MUT_REF if is_mut else UnaryOp.REF, operand=operand)
        
        if self.match(TokenType.STAR):
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.DEREF, operand=operand)
        
        return self.parse_call()
    
    def parse_call(self) -> Expr:
        """Parse function calls and method calls."""
        expr = self.parse_primary()
        
        while True:
            if self.match(TokenType.LPAREN):
                # Function call
                args = []
                if not self.check(TokenType.RPAREN):
                    while True:
                        # Check for named arguments
                        if self.check(TokenType.IDENTIFIER) and self.peek().type == TokenType.COLON:
                            name = self.advance().value
                            self.advance()  # colon
                            value = self.parse_expr()
                            args.append((name, value))
                        else:
                            args.append((None, self.parse_expr()))
                        
                        if not self.match(TokenType.COMMA):
                            break
                
                self.expect(TokenType.RPAREN, "Expected ')' after arguments")
                
                # Separate positional and named args
                positional = [a[1] for a in args if a[0] is None]
                named = {a[0]: a[1] for a in args if a[0] is not None}
                
                expr = CallExpr(func=expr, args=positional, type_args=named)
            
            elif self.match(TokenType.DOT):
                # Field or method access
                if self.check(TokenType.INTEGER):
                    # Tuple index
                    idx = int(self.advance().value)
                    expr = TupleIndexExpr(base=expr, index=idx)
                else:
                    field = self.expect(TokenType.IDENTIFIER, "Expected field name").value
                    
                    if self.match(TokenType.LPAREN):
                        # Method call
                        args = []
                        if not self.check(TokenType.RPAREN):
                            while True:
                                args.append(self.parse_expr())
                                if not self.match(TokenType.COMMA):
                                    break
                        
                        self.expect(TokenType.RPAREN, "Expected ')' after method arguments")
                        expr = CallExpr(
                            func=FieldAccessExpr(base=expr, field=field, is_method=True),
                            args=args
                        )
                    else:
                        expr = FieldAccessExpr(base=expr, field=field)
            
            elif self.match(TokenType.LBRACKET):
                # Index access
                index = self.parse_expr()
                self.expect(TokenType.RBRACKET, "Expected ']'")
                expr = IndexExpr(base=expr, index=index)
            
            elif self.match(TokenType.QUESTION):
                # Try operator (monadic error handling)
                expr = CallExpr(func=expr, args=[])
                expr.is_try = True
            
            else:
                break
        
        return expr
    
    def parse_primary(self) -> Expr:
        """Parse primary expressions."""
        # Literals
        if self.check(TokenType.INTEGER):
            value = self.advance().value
            return LiteralExpr(value=int(value), token_type='int')
        
        if self.check(TokenType.FLOAT):
            value = self.advance().value
            return LiteralExpr(value=float(value), token_type='float')
        
        if self.check(TokenType.STRING):
            value = self.advance().value
            return LiteralExpr(value=value, token_type='string')
        
        if self.check(TokenType.CHAR):
            value = self.advance().value
            return LiteralExpr(value=value, token_type='char')
        
        if self.check(TokenType.BOOL):
            value = self.advance().value == 'true'
            return LiteralExpr(value=value, token_type='bool')
        
        # Parenthesized expression
        if self.match(TokenType.LPAREN):
            if self.check(TokenType.RPAREN):
                self.advance()
                return TupleExpr(elements=[])
            
            # Check for tuple
            expr = self.parse_expr()
            
            if self.match(TokenType.COMMA):
                elements = [expr]
                while True:
                    elements.append(self.parse_expr())
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RPAREN, "Expected ')'")
                return TupleExpr(elements=elements)
            
            self.expect(TokenType.RPAREN, "Expected ')'")
            return expr
        
        # Block expression
        if self.check(TokenType.LBRACE):
            return self.parse_block_expr()
        
        # If expression
        if self.check_keyword('if'):
            return self.parse_if()
        
        # Match expression
        if self.check_keyword('match'):
            return self.parse_match()
        
        # Loop expressions
        if self.check_keyword('loop'):
            return self.parse_loop()
        
        if self.check_keyword('while'):
            return self.parse_while()
        
        if self.check_keyword('for'):
            return self.parse_for()
        
        # Return expression
        if self.check_keyword('return'):
            start = self.advance()
            value = None
            if not self.check(TokenType.SEMICOLON) and not self.check(TokenType.NEWLINE) and \
               not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
                value = self.parse_expr()
            return ReturnExpr(value=value)
        
        # Break expression
        if self.check_keyword('break'):
            start = self.advance()
            value = None
            label = None
            if self.check(TokenType.IDENTIFIER):
                label = self.advance().value
            elif not self.check(TokenType.SEMICOLON) and not self.check(TokenType.NEWLINE):
                value = self.parse_expr()
            return BreakExpr(value=value, label=label)
        
        # Continue expression
        if self.check_keyword('continue'):
            self.advance()
            label = None
            if self.check(TokenType.IDENTIFIER):
                label = self.advance().value
            return ContinueExpr(label=label)
        
        # SizeOf expression
        if self.check_keyword('sizeof'):
            self.advance()
            self.expect(TokenType.LT, "Expected '<'")
            type_arg = self.parse_type()
            self.expect(TokenType.GT, "Expected '>'")
            return SizeOfExpr(type_arg=type_arg)
        
        # Array literal
        if self.match(TokenType.LBRACKET):
            elements = []
            if not self.check(TokenType.RBRACKET):
                while True:
                    elements.append(self.parse_expr())
                    if not self.match(TokenType.COMMA):
                        break
            self.expect(TokenType.RBRACKET, "Expected ']'")
            return ArrayExpr(elements=elements)
        
        # Range expression
        if self.match(TokenType.DOTDOT):
            end = self.parse_or()
            return RangeExpr(end=end)
        
        if self.match(TokenType.DOTDOTDOT):
            end = self.parse_or()
            return RangeExpr(end=end, inclusive=True)
        
        # Identifier
        if self.check(TokenType.IDENTIFIER):
            name = self.advance().value
            return IdentifierExpr(name=name)
        
        # Struct literal
        if self.check(TokenType.IDENTIFIER) and self.peek().type == TokenType.LBRACE:
            name = self.advance().value
            self.expect(TokenType.LBRACE, "Expected '{'")
            
            fields = {}
            base = None
            
            if not self.check(TokenType.RBRACE):
                while True:
                    if self.match(TokenType.DOTDOT):
                        base = self.parse_expr()
                        break
                    
                    field_name = self.expect(TokenType.IDENTIFIER, "Expected field name").value
                    self.expect(TokenType.COLON, "Expected ':'")
                    value = self.parse_expr()
                    fields[field_name] = value
                    
                    if not self.match(TokenType.COMMA):
                        break
            
            self.expect(TokenType.RBRACE, "Expected '}'")
            return StructExpr(name=name, fields=fields, base=base)
        
        raise ParseError(f"Expected expression, found {self.current.type.name}", self.current)
