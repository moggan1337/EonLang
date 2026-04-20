"""
Main compiler driver for EonLang.
"""

import os
import sys
import subprocess
from typing import List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

from .lexer import Lexer, LexerError
from .parser import Parser, ParseError
from .ast import SourceFile
from .typeinfer import TypeInferrer, TypeError
from .borrow import BorrowChecker, BorrowError
from .codegen import Codegen, CodegenError
from .llvm_backend import LLVMBuilder
from .patterns import PatternCompiler, PatternError
from .traits import TraitResolver, TraitChecker, TraitError
from .ir import Module


class EonLangError(Exception):
    """Base exception for EonLang compiler errors."""
    pass


class CompilationError(EonLangError):
    """Raised when compilation fails."""
    pass


@dataclass
class CompilerOptions:
    """Options for the EonLang compiler."""
    input_file: str = ""
    output_file: str = ""
    target: str = "x86_64-unknown-linux-gnu"
    optimization_level: int = 0  # 0-3
    debug_info: bool = False
    emit_llvm: bool = False
    emit_ir: bool = False
    run: bool = False
    print_ast: bool = False
    print_tokens: bool = False
    print_types: bool = False
    warnings_as_errors: bool = False
    lto: bool = False
    linker: str = "gcc"


@dataclass
class CompilerOutput:
    """Output from the compiler."""
    success: bool
    output_file: Optional[str]
    llvm_ir: Optional[str]
    errors: List[str]
    warnings: List[str]


class EonLangCompiler:
    """
    Main compiler driver for EonLang.
    
    Pipeline:
    1. Lexing - Tokenize source code
    2. Parsing - Build AST from tokens
    3. Type inference - Hindley-Milner type checking
    4. Borrow checking - Memory safety verification
    5. Pattern compilation - Exhaustiveness checking
    6. Trait resolution - Method lookup
    7. IR generation - Build SSA IR
    8. LLVM codegen - Generate LLVM IR
    9. Code generation - Compile to object file
    """
    
    def __init__(self, options: CompilerOptions = None):
        self.options = options or CompilerOptions()
        self.type_inferrer = TypeInferrer()
        self.borrow_checker = BorrowChecker()
        self.trait_resolver = TraitResolver(self.type_inferrer)
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def compile(self, source: str, filename: str = "<stdin>") -> CompilerOutput:
        """Compile EonLang source code."""
        self.errors.clear()
        self.warnings.clear()
        
        try:
            # Phase 1: Lexing
            lexer = Lexer(source, filename)
            tokens = lexer.tokenize()
            
            if self.options.print_tokens:
                for token in tokens:
                    print(f"{token.line:3d}:{token.column:3d} {token.type.name:15s} {token.value!r}")
                return CompilerOutput(success=True, output_file=None, llvm_ir=None,
                                   errors=[], warnings=[])
            
            # Phase 2: Parsing
            parser = Parser(tokens)
            ast = parser.parse_source_file()
            
            if self.options.print_ast:
                print(self.format_ast(ast))
                return CompilerOutput(success=True, output_file=None, llvm_ir=None,
                                   errors=[], warnings=[])
            
            # Phase 3: Type inference
            self.type_inferrer.infer(ast)
            
            if self.options.print_types:
                self.print_types(ast)
                return CompilerOutput(success=True, output_file=None, llvm_ir=None,
                                   errors=[], warnings=[])
            
            # Phase 4: Borrow checking
            self.borrow_checker.check_file(ast)
            
            # Phase 5: Trait resolution
            for item in ast.items:
                if isinstance(item, TraitStmt):
                    self.trait_resolver.register_trait(item)
                elif isinstance(item, ImplStmt):
                    self.trait_resolver.register_impl(item)
            
            # Phase 6: Pattern compilation
            pattern_compiler = PatternCompiler(self.create_codegen())
            self.compile_patterns(ast, pattern_compiler)
            
            # Phase 7 & 8: IR and LLVM generation
            codegen = self.create_codegen()
            module = codegen.generate(ast)
            
            # Phase 9: Emit LLVM IR
            llvm_builder = LLVMBuilder(module)
            llvm_ir = llvm_builder.emit_module()
            
            if self.options.emit_llvm:
                print(llvm_ir)
                return CompilerOutput(success=True, output_file=None,
                                   llvm_ir=llvm_ir, errors=[], warnings=[])
            
            # Phase 10: Code generation
            output_file = self.generate_code(llvm_ir)
            
            return CompilerOutput(
                success=True,
                output_file=output_file,
                llvm_ir=llvm_ir if self.options.emit_ir else None,
                errors=[],
                warnings=self.warnings
            )
            
        except LexerError as e:
            self.errors.append(f"Lexical error at {e.line}:{e.column}: {e.message}")
        except ParseError as e:
            self.errors.append(f"Syntax error at {e.token.line}:{e.token.column}: {e.message}")
        except TypeError as e:
            msg = f"Type error: {e.message}"
            if e.span:
                msg = f"Type error at {e.span.start_line}:{e.span.start_col}: {e.message}"
            self.errors.append(msg)
        except BorrowError as e:
            msg = f"Borrow error: {e.message}"
            if e.span:
                msg = f"Borrow error at {e.span.start_line}:{e.span.start_col}: {e.message}"
            self.errors.append(msg)
        except PatternError as e:
            msg = f"Pattern error: {e.message}"
            if e.span:
                msg = f"Pattern error at {e.span.start_line}:{e.span.start_col}: {e.message}"
            self.errors.append(msg)
        except TraitError as e:
            msg = f"Trait error: {e.message}"
            if e.span:
                msg = f"Trait error at {e.span.start_line}:{e.span.start_col}: {e.message}"
            self.errors.append(msg)
        except Exception as e:
            self.errors.append(f"Internal compiler error: {str(e)}")
        
        return CompilerOutput(
            success=False,
            output_file=None,
            llvm_ir=None,
            errors=self.errors,
            warnings=self.warnings
        )
    
    def compile_file(self, filename: str) -> CompilerOutput:
        """Compile an EonLang source file."""
        with open(filename, 'r') as f:
            source = f.read()
        
        self.options.input_file = filename
        return self.compile(source, filename)
    
    def create_codegen(self) -> Codegen:
        """Create a code generator."""
        return Codegen()
    
    def compile_patterns(self, ast: SourceFile, compiler: PatternCompiler):
        """Compile patterns in the AST."""
        for item in ast.items:
            if isinstance(item, FuncStmt) and item.body:
                self.compile_patterns_in_block(item.body, compiler)
    
    def compile_patterns_in_block(self, block, compiler: PatternCompiler):
        """Recursively compile patterns in a block."""
        for stmt in block.stmts:
            if isinstance(stmt, MatchExpr):
                compiler.compile_match(stmt)
            elif hasattr(stmt, 'body'):
                if hasattr(stmt.body, 'stmts'):
                    self.compile_patterns_in_block(stmt.body, compiler)
    
    def generate_code(self, llvm_ir: str) -> Optional[str]:
        """Generate machine code from LLVM IR."""
        # Create temporary files
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.ll', delete=False, mode='w') as f:
            llvm_file = f.name
            f.write(llvm_ir)
        
        try:
            # Compile LLVM IR to object file
            obj_file = llvm_file.replace('.ll', '.o')
            
            # Try to find LLVM tools
            llvm_config = self.find_llvm_config()
            
            if llvm_config:
                llc = llvm_config.get('llc', 'llc')
                clang = llvm_config.get('clang', 'clang')
                
                # Compile to object file
                llc_cmd = [llc, '-filetype=obj', '-o', obj_file, llvm_file]
                if self.options.optimization_level > 0:
                    llc_cmd.insert(1, f'-O{self.options.optimization_level}')
                
                result = subprocess.run(llc_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    self.errors.append(f"LLC failed: {result.stderr}")
                    return None
                
                # Link to executable
                output_file = self.options.output_file or 'a.out'
                link_cmd = [clang, '-o', output_file, obj_file]
                if self.options.debug_info:
                    link_cmd.append('-g')
                
                result = subprocess.run(link_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    self.errors.append(f"Linking failed: {result.stderr}")
                    return None
                
                return output_file
            else:
                # No LLVM available, just return LLVM IR
                output_file = self.options.output_file or llvm_file.replace('.ll', '.s')
                with open(output_file, 'w') as f:
                    f.write(llvm_ir)
                return output_file
        
        finally:
            # Clean up temp files
            if os.path.exists(llvm_file):
                os.unlink(llvm_file)
    
    def find_llvm_config(self) -> Optional[dict]:
        """Find LLVM tools on the system."""
        import shutil
        
        tools = {
            'llc': 'llc',
            'clang': 'clang',
            'opt': 'opt',
            'llvm-link': 'llvm-link',
        }
        
        result = {}
        for name, cmd in tools.items():
            path = shutil.which(cmd)
            if path:
                result[name] = path
        
        return result if result else None
    
    def format_ast(self, ast: SourceFile, indent: int = 0) -> str:
        """Format the AST for printing."""
        lines = []
        prefix = "  " * indent
        
        for item in ast.items:
            if isinstance(item, FuncStmt):
                lines.append(f"{prefix}fn {item.name}(")
                for name, type_, is_mut in item.params:
                    lines.append(f"{prefix}  {name}: {type_}")
                lines.append(f"{prefix}) -> {item.return_type}")
                if item.body:
                    lines.append(f"{prefix}{{")
                    lines.append(self.format_block(item.body, indent + 1))
                    lines.append(f"{prefix}}}")
            
            elif isinstance(item, StructStmt):
                lines.append(f"{prefix}struct {item.name} {{")
                for name, type_, _ in item.fields:
                    lines.append(f"{prefix}  {name}: {type_}")
                lines.append(f"{prefix}}}")
            
            elif isinstance(item, EnumStmt):
                lines.append(f"{prefix}enum {item.name} {{")
                for name, types in item.variants:
                    if types:
                        lines.append(f"{prefix}  {name}({', '.join(str(t) for t in types)})")
                    else:
                        lines.append(f"{prefix}  {name}")
                lines.append(f"{prefix}}}")
            
            elif isinstance(item, ExprStmt):
                lines.append(f"{prefix}{self.format_expr(item.expr)}")
        
        return '\n'.join(lines)
    
    def format_block(self, block, indent: int = 0) -> str:
        """Format a block for printing."""
        lines = []
        prefix = "  " * indent
        
        for stmt in block.stmts:
            if isinstance(stmt, LetStmt):
                mut = "mut " if stmt.is_mutable else ""
                lines.append(f"{prefix}let {mut}{stmt.name}: {stmt.type_annotation or '_'} = ...")
            elif isinstance(stmt, ExprStmt):
                lines.append(f"{prefix}{self.format_expr(stmt.expr)}")
        
        if block.expr:
            lines.append(f"{prefix}{self.format_expr(block.expr)}")
        
        return '\n'.join(lines)
    
    def format_expr(self, expr) -> str:
        """Format an expression for printing."""
        if expr is None:
            return ""
        
        from .ast import (
            LiteralExpr, IdentifierExpr, BinaryExpr, CallExpr,
            UnaryExpr, IfExpr, MatchExpr, Block
        )
        
        if isinstance(expr, LiteralExpr):
            return repr(expr.value)
        elif isinstance(expr, IdentifierExpr):
            return expr.name
        elif isinstance(expr, BinaryExpr):
            from .ast import BinaryOp
            op_map = {
                BinaryOp.ADD: '+', BinaryOp.SUB: '-', BinaryOp.MUL: '*',
                BinaryOp.DIV: '/', BinaryOp.EQ: '==', BinaryOp.NE: '!='
            }
            op = op_map.get(expr.op, '?')
            return f"({self.format_expr(expr.left)} {op} {self.format_expr(expr.right)})"
        elif isinstance(expr, CallExpr):
            args = ', '.join(self.format_expr(a) for a in expr.args)
            return f"{self.format_expr(expr.func)}({args})"
        elif isinstance(expr, UnaryExpr):
            from .ast import UnaryOp
            if expr.op == UnaryOp.NEG:
                return f"-{self.format_expr(expr.operand)}"
            elif expr.op == UnaryOp.NOT:
                return f"!{self.format_expr(expr.operand)}"
        elif isinstance(expr, Block):
            return f"{{ ... }}"
        elif isinstance(expr, IfExpr):
            return f"if {self.format_expr(expr.condition)} {{ ... }}"
        elif isinstance(expr, MatchExpr):
            return f"match {self.format_expr(expr.value)} {{ ... }}"
        
        return "..."
    
    def print_types(self, ast: SourceFile):
        """Print inferred types."""
        for item in ast.items:
            if hasattr(item, 'name') and hasattr(item, 'return_type'):
                if isinstance(item, FuncStmt):
                    print(f"fn {item.name}: {item.return_type}")
                elif isinstance(item, StructStmt):
                    print(f"struct {item.name}")
                    for name, type_, _ in item.fields:
                        print(f"  {name}: {type_}")


def main():
    """Main entry point for the compiler."""
    import argparse
    
    parser = argparse.ArgumentParser(description='EonLang Compiler')
    parser.add_argument('input', nargs='?', help='Input file')
    parser.add_argument('-o', '--output', help='Output file')
    parser.add_argument('-O', '--optimize', type=int, default=0, help='Optimization level')
    parser.add_argument('-g', '--debug', action='store_true', help='Generate debug info')
    parser.add_argument('-S', '--emit-llvm', action='store_true', help='Emit LLVM IR')
    parser.add_argument('--ir', action='store_true', help='Emit internal IR')
    parser.add_argument('-r', '--run', action='store_true', help='Run after compilation')
    parser.add_argument('--print-ast', action='store_true', help='Print AST')
    parser.add_argument('--print-tokens', action='store_true', help='Print tokens')
    parser.add_argument('--print-types', action='store_true', help='Print inferred types')
    parser.add_argument('-Werror', action='store_true', help='Treat warnings as errors')
    
    args = parser.parse_args()
    
    options = CompilerOptions(
        input_file=args.input or "",
        output_file=args.output or "",
        optimization_level=args.optimize,
        debug_info=args.debug,
        emit_llvm=args.emit_llvm,
        emit_ir=args.ir,
        run=args.run,
        print_ast=args.print_ast,
        print_tokens=args.print_tokens,
        print_types=args.print_types,
        warnings_as_errors=args.Werror
    )
    
    compiler = EonLangCompiler(options)
    
    if args.input:
        result = compiler.compile_file(args.input)
    else:
        # Read from stdin
        source = sys.stdin.read()
        result = compiler.compile(source)
    
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    
    if result.warnings:
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    
    if result.output_file and options.run:
        import subprocess
        subprocess.run([result.output_file])
    
    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()
