"""
Test suite for EonLang compiler.
"""

import unittest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.lexer import Lexer, LexerError
from src.tokens import TokenType, Token
from src.parser import Parser, ParseError
from src.ast import *
from src.typeinfer import TypeInferrer
from src.borrow import BorrowChecker


class TestLexer(unittest.TestCase):
    """Tests for the lexer."""
    
    def test_keywords(self):
        """Test keyword tokenization."""
        source = "fn let if else while for return"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        keywords = [TokenType.FN, TokenType.LET, TokenType.IF, 
                   TokenType.ELSE, TokenType.WHILE, TokenType.FOR, 
                   TokenType.RETURN]
        
        for i, token_type in enumerate(keywords):
            self.assertEqual(tokens[i].type, token_type)
    
    def test_identifiers(self):
        """Test identifier tokenization."""
        source = "foo bar baz123 _underscore"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].value, "foo")
        self.assertEqual(tokens[1].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[1].value, "bar")
        self.assertEqual(tokens[2].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[2].value, "baz123")
        self.assertEqual(tokens[3].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[3].value, "_underscore")
    
    def test_integers(self):
        """Test integer literal tokenization."""
        source = "42 123_456 0xFF 0b1010 0o755"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.INTEGER)
        self.assertEqual(tokens[0].value, "42")
        self.assertEqual(tokens[1].type, TokenType.INTEGER)
        self.assertEqual(tokens[1].value, "123_456")
    
    def test_floats(self):
        """Test float literal tokenization."""
        source = "3.14 1.5e10 2.5E-3"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.FLOAT)
        self.assertEqual(tokens[0].value, "3.14")
        self.assertEqual(tokens[1].type, TokenType.FLOAT)
        self.assertEqual(tokens[1].value, "1.5e10")
    
    def test_strings(self):
        """Test string literal tokenization."""
        source = '"hello" "world\\n" "escaped: \\t \\r"'
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.STRING)
        self.assertEqual(tokens[0].value, "hello")
    
    def test_operators(self):
        """Test operator tokenization."""
        source = "+ - * / % == != < > <= >="
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.PLUS)
        self.assertEqual(tokens[1].type, TokenType.MINUS)
        self.assertEqual(tokens[2].type, TokenType.STAR)
        self.assertEqual(tokens[3].type, TokenType.SLASH)
        self.assertEqual(tokens[4].type, TokenType.PERCENT)
        self.assertEqual(tokens[5].type, TokenType.EQ)
        self.assertEqual(tokens[6].type, TokenType.NE)
        self.assertEqual(tokens[7].type, TokenType.LT)
        self.assertEqual(tokens[8].type, TokenType.GT)
        self.assertEqual(tokens[9].type, TokenType.LE)
        self.assertEqual(tokens[10].type, TokenType.GE)
    
    def test_arrows(self):
        """Test arrow tokenization."""
        source = "-> =>"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.ARROW)
        self.assertEqual(tokens[1].type, TokenType.FAT_ARROW)
    
    def test_comments(self):
        """Test comment handling."""
        source = "x // comment\\n y"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        # Should skip the comment
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)  # x
        self.assertEqual(tokens[0].value, "x")
        self.assertEqual(tokens[1].type, TokenType.IDENTIFIER)  # y
        self.assertEqual(tokens[1].value, "y")
    
    def test_multiline_comments(self):
        """Test multiline comment handling."""
        source = "x /* comment */ y"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].value, "x")
        self.assertEqual(tokens[1].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[1].value, "y")


class TestParser(unittest.TestCase):
    """Tests for the parser."""
    
    def parse(self, source: str) -> SourceFile:
        """Parse source code."""
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        return parser.parse_source_file()
    
    def test_empty_program(self):
        """Test parsing empty program."""
        ast = self.parse("")
        self.assertEqual(len(ast.items), 0)
    
    def test_function(self):
        """Test parsing a function."""
        source = "fn main() -> i32 { return 42; }"
        ast = self.parse(source)
        
        self.assertEqual(len(ast.items), 1)
        self.assertIsInstance(ast.items[0], FuncStmt)
        
        func = ast.items[0]
        self.assertEqual(func.name, "main")
        self.assertEqual(len(func.params), 0)
        self.assertEqual(func.return_type.name, "i32")
    
    def test_function_with_params(self):
        """Test parsing a function with parameters."""
        source = "fn add(x: i32, y: i32) -> i32 { return x + y; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        self.assertEqual(func.name, "add")
        self.assertEqual(len(func.params), 2)
        self.assertEqual(func.params[0][0], "x")
        self.assertEqual(func.params[1][0], "y")
    
    def test_let_statement(self):
        """Test parsing let statements."""
        source = "fn test() { let x = 42; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertIsInstance(let_stmt, LetStmt)
        self.assertEqual(let_stmt.name, "x")
    
    def test_mutable_let(self):
        """Test parsing mutable let."""
        source = "fn test() { let mut x = 42; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertTrue(let_stmt.is_mutable)
    
    def test_if_expression(self):
        """Test parsing if expressions."""
        source = "fn test() { if true { 1 } else { 2 } }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        if_expr = block.stmts[0]
        
        self.assertIsInstance(if_expr, IfExpr)
    
    def test_match_expression(self):
        """Test parsing match expressions."""
        source = """
        fn test(x: i32) -> i32 {
            match x {
                1 => 10,
                2 => 20,
                _ => 0
            }
        }
        """
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        match_expr = block.stmts[0]
        
        self.assertIsInstance(match_expr, MatchExpr)
        self.assertEqual(len(match_expr.arms), 3)
    
    def test_struct(self):
        """Test parsing structs."""
        source = """
        struct Point {
            x: i32,
            y: i32
        }
        """
        ast = self.parse(source)
        
        struct_stmt = ast.items[0]
        self.assertIsInstance(struct_stmt, StructStmt)
        self.assertEqual(struct_stmt.name, "Point")
        self.assertEqual(len(struct_stmt.fields), 2)
    
    def test_enum(self):
        """Test parsing enums."""
        source = """
        enum Color {
            Red,
            Green,
            Blue
        }
        """
        ast = self.parse(source)
        
        enum_stmt = ast.items[0]
        self.assertIsInstance(enum_stmt, EnumStmt)
        self.assertEqual(enum_stmt.name, "Color")
        self.assertEqual(len(enum_stmt.variants), 3)
    
    def test_loop(self):
        """Test parsing loops."""
        source = "fn test() { loop { break; } }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        loop_expr = block.stmts[0]
        
        self.assertIsInstance(loop_expr, LoopExpr)
    
    def test_while_loop(self):
        """Test parsing while loops."""
        source = "fn test() { while true { x = x + 1; } }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        while_expr = block.stmts[0]
        
        self.assertIsInstance(while_expr, WhileExpr)
    
    def test_for_loop(self):
        """Test parsing for loops."""
        source = "fn test() { for i in 0..10 { } }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        for_expr = block.stmts[0]
        
        self.assertIsInstance(for_expr, ForExpr)
        self.assertEqual(for_expr.variable, "i")
    
    def test_binary_expressions(self):
        """Test parsing binary expressions."""
        source = "fn test() { let x = 1 + 2 * 3 - 4 / 2; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertIsInstance(let_stmt, LetStmt)
        self.assertIsInstance(let_stmt.value, BinaryExpr)
    
    def test_unary_expressions(self):
        """Test parsing unary expressions."""
        source = "fn test() { let x = -42; let y = !true; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        
        let1 = block.stmts[0]
        self.assertIsInstance(let1.value, UnaryExpr)
        
        let2 = block.stmts[1]
        self.assertIsInstance(let2.value, UnaryExpr)
    
    def test_array_literal(self):
        """Test parsing array literals."""
        source = "fn test() { let arr = [1, 2, 3]; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertIsInstance(let_stmt.value, ArrayExpr)
        self.assertEqual(len(let_stmt.value.elements), 3)
    
    def test_tuple_literal(self):
        """Test parsing tuple literals."""
        source = "fn test() { let t = (1, 2, 3); }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertIsInstance(let_stmt.value, TupleExpr)
        self.assertEqual(len(let_stmt.value.elements), 3)
    
    def test_field_access(self):
        """Test parsing field access."""
        source = "fn test() { let x = point.x; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertIsInstance(let_stmt.value, FieldAccessExpr)
        self.assertEqual(let_stmt.value.field, "x")
    
    def test_method_call(self):
        """Test parsing method calls."""
        source = "fn test() { let len = text.len(); }"
        ast = self.parse(source)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertIsInstance(let_stmt.value, CallExpr)
    
    def test_generic_function(self):
        """Test parsing generic functions."""
        source = "fn identity<T>(x: T) -> T { return x; }"
        ast = self.parse(source)
        
        func = ast.items[0]
        self.assertEqual(len(func.type_params), 1)
        self.assertEqual(func.type_params[0], "T")


class TestTypeInference(unittest.TestCase):
    """Tests for type inference."""
    
    def test_simple_inference(self):
        """Test simple type inference."""
        source = "fn test() { let x = 42; }"
        
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse_source_file()
        
        inferrer = TypeInferrer()
        inferrer.infer(ast)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertEqual(let_stmt.value.type.name, "i32")
    
    def test_binary_expr_types(self):
        """Test type inference for binary expressions."""
        source = "fn test() { let x = 1 + 2; }"
        
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse_source_file()
        
        inferrer = TypeInferrer()
        inferrer.infer(ast)
        
        func = ast.items[0]
        block = func.body
        let_stmt = block.stmts[0]
        
        self.assertEqual(let_stmt.value.type.name, "i32")


class TestIntegration(unittest.TestCase):
    """Integration tests for the compiler."""
    
    def test_fibonacci(self):
        """Test compiling a fibonacci function."""
        source = """
        fn fib(n: i32) -> i32 {
            if n <= 1 {
                return n;
            }
            return fib(n - 1) + fib(n - 2);
        }
        
        fn main() -> i32 {
            return fib(10);
        }
        """
        
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse_source_file()
        
        # Should not raise any errors
        inferrer = TypeInferrer()
        inferrer.infer(ast)
        
        borrow_checker = BorrowChecker()
        borrow_checker.check_file(ast)
        
        # Check that we have the right functions
        self.assertEqual(len(ast.items), 2)
        self.assertEqual(ast.items[0].name, "fib")
        self.assertEqual(ast.items[1].name, "main")


if __name__ == '__main__':
    unittest.main()
