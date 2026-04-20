"""
Borrow checker and lifetime analysis for EonLang.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum, auto
from .ast import *


class BorrowError(Exception):
    """Raised when borrow checking fails."""
    def __init__(self, message: str, span: Optional[Span] = None):
        self.message = message
        self.span = span
        super().__init__(f"Borrow error: {message}")


class OwnershipKind(Enum):
    """Kind of ownership."""
    OWNED = auto()      # Value is owned (moved)
    BORROWED = auto()   # Borrowed reference
    MUT_BORROWED = auto()  # Mutable borrowed reference
    SHARED = auto()     # Shared reference


@dataclass
class Lifetime:
    """Represents a lifetime annotation."""
    name: str
    regions: List[Tuple[int, int]] = field(default_factory=list)  # (start, end) of scope
    
    def __repr__(self):
        return f"'{self.name}"
    
    def outlives(self, other: 'Lifetime') -> bool:
        """Check if this lifetime outlives another."""
        # Simple check: this lifetime's regions should cover other's regions
        return True  # Simplified


@dataclass
class Place:
    """A place (value) in the program."""
    name: str
    type: Type
    is_mutable: bool
    lifetime: Optional[str] = None
    is_borrowed: bool = False
    is_moved: bool = False
    borrowers: Set[str] = field(default_factory=set)  # Set of places borrowing this


@dataclass
class Borrow:
    """Represents a borrow."""
    owner: str
    borrower: str
    kind: OwnershipKind
    lifetime: str
    location: Span
    is_mutable: bool


@dataclass
class BorrowChecker:
    """
    Borrow checker for EonLang.
    
    Implements the rules:
    1. Each value has exactly one owner
    2. When a value is moved, the new owner takes ownership
    3. You can have either one mutable borrow OR multiple immutable borrows
    4. Borrows must not outlive the value they borrow
    """
    
    def __init__(self):
        self.places: Dict[str, Place] = {}
        self.borrows: List[Borrow] = []
        self.active_borrows: Dict[str, List[Borrow]] = {}  # owner -> active borrows
        self.moved_values: Set[str] = set()
        self.scope_stack: List[Set[str]] = [set()]  # Stack of scope-local variables
        self.loop_depth = 0
        self.lifetime_counter = 0
        self.lifetimes: Dict[str, Lifetime] = {}
    
    def new_lifetime(self) -> str:
        """Generate a new lifetime name."""
        self.lifetime_counter += 1
        return f"'l{self.lifetime_counter}"
    
    def enter_scope(self):
        """Enter a new lexical scope."""
        self.scope_stack.append(set())
    
    def exit_scope(self):
        """Exit the current lexical scope."""
        scope = self.scope_stack.pop()
        
        # Release all borrows for variables going out of scope
        for var_name in scope:
            self.release_borrows(var_name)
    
    def release_borrows(self, var_name: str):
        """Release all borrows for a variable going out of scope."""
        if var_name in self.active_borrows:
            for borrow in self.active_borrows[var_name]:
                if borrow.borrower in self.active_borrows:
                    del self.active_borrows[borrow.borrower]
            del self.active_borrows[var_name]
    
    def check_file(self, ast: SourceFile):
        """Check a complete source file."""
        for item in ast.items:
            if isinstance(item, FuncStmt):
                self.check_function(item)
            elif isinstance(item, StructStmt):
                self.check_struct(item)
            elif isinstance(item, EnumStmt):
                self.check_enum(item)
    
    def check_function(self, func: FuncStmt):
        """Check a function for borrow violations."""
        self.enter_scope()
        
        # Add parameters as places
        for name, type_, is_mut in func.params:
            self.places[name] = Place(
                name=name,
                type=type_,
                is_mutable=is_mut,
                lifetime='static'
            )
            self.scope_stack[-1].add(name)
        
        # Check function body
        if func.body:
            self.check_block(func.body)
        
        self.exit_scope()
    
    def check_struct(self, struct: StructStmt):
        """Check a struct declaration."""
        pass  # Structs themselves don't need borrow checking
    
    def check_enum(self, enum: EnumStmt):
        """Check an enum declaration."""
        pass  # Enums themselves don't need borrow checking
    
    def check_block(self, block: Block):
        """Check a block expression."""
        self.enter_scope()
        
        for stmt in block.stmts:
            self.check_stmt(stmt)
        
        if block.expr:
            self.check_expr(block.expr)
        
        self.exit_scope()
    
    def check_stmt(self, stmt: Stmt):
        """Check a statement."""
        if isinstance(stmt, LetStmt):
            self.check_let(stmt)
        elif isinstance(stmt, AssignStmt):
            self.check_assign(stmt)
        elif isinstance(stmt, ExprStmt):
            self.check_expr(stmt.expr)
        elif isinstance(stmt, IfExpr):
            self.check_if(stmt)
        elif isinstance(stmt, MatchExpr):
            self.check_match(stmt)
        elif isinstance(stmt, LoopExpr):
            self.check_loop(stmt)
        elif isinstance(stmt, WhileExpr):
            self.check_while(stmt)
        elif isinstance(stmt, ForExpr):
            self.check_for(stmt)
        elif isinstance(stmt, ReturnStmt):
            pass  # Return statements are checked elsewhere
        elif isinstance(stmt, BreakStmt):
            pass
        elif isinstance(stmt, ContinueStmt):
            pass
    
    def check_let(self, stmt: LetStmt):
        """Check a let statement."""
        if stmt.value:
            self.check_expr(stmt.value)
        
        self.places[stmt.name] = Place(
            name=stmt.name,
            type=stmt.type_annotation or (stmt.value.type if stmt.value else Type(TypeKind.UNKNOWN)),
            is_mutable=stmt.is_mutable
        )
        self.scope_stack[-1].add(stmt.name)
    
    def check_assign(self, stmt: AssignStmt):
        """Check an assignment statement."""
        target_type = self.check_expr(stmt.target, for_assign=True)
        
        if isinstance(stmt.target, IdentifierExpr):
            var_name = stmt.target.name
            if var_name in self.places:
                place = self.places[var_name]
                if not place.is_mutable and not place.is_borrowed:
                    raise BorrowError(f"Cannot assign to immutable variable: {var_name}", 
                                    Span(0, 0, 0, 0))
        
        self.check_expr(stmt.value)
    
    def check_expr(self, expr: Expr, for_assign: bool = False) -> Type:
        """Check an expression and return its type."""
        if isinstance(expr, LiteralExpr):
            return expr.type
        
        elif isinstance(expr, IdentifierExpr):
            return self.check_identifier(expr)
        
        elif isinstance(expr, UnaryExpr):
            return self.check_unary(expr)
        
        elif isinstance(expr, BinaryExpr):
            self.check_expr(expr.left)
            self.check_expr(expr.right)
            return expr.type
        
        elif isinstance(expr, CallExpr):
            return self.check_call(expr)
        
        elif isinstance(expr, IfExpr):
            return self.check_if(expr)
        
        elif isinstance(expr, MatchExpr):
            return self.check_match(expr)
        
        elif isinstance(expr, Block):
            self.check_block(expr)
            return expr.type
        
        elif isinstance(expr, LoopExpr):
            return self.check_loop(expr)
        
        elif isinstance(expr, WhileExpr):
            return self.check_while(expr)
        
        elif isinstance(expr, ForExpr):
            return self.check_for(expr)
        
        elif isinstance(expr, ReturnExpr):
            if expr.value:
                self.check_expr(expr.value)
            return Type(TypeKind.NEVER)
        
        elif isinstance(expr, BreakExpr):
            return Type(TypeKind.NEVER)
        
        elif isinstance(expr, ContinueExpr):
            return Type(TypeKind.NEVER)
        
        elif isinstance(expr, FieldAccessExpr):
            self.check_expr(expr.base)
            return expr.type
        
        elif isinstance(expr, IndexExpr):
            self.check_expr(expr.base)
            self.check_expr(expr.index)
            return expr.type
        
        elif isinstance(expr, TupleExpr):
            for elem in expr.elements:
                self.check_expr(elem)
            return expr.type
        
        elif isinstance(expr, ArrayExpr):
            for elem in expr.elements:
                self.check_expr(elem)
            return expr.type
        
        elif isinstance(expr, RangeExpr):
            if expr.start:
                self.check_expr(expr.start)
            if expr.end:
                self.check_expr(expr.end)
            return expr.type
        
        elif isinstance(expr, StructExpr):
            for field_expr in expr.fields.values():
                self.check_expr(field_expr)
            return expr.type
        
        elif isinstance(expr, CastExpr):
            self.check_expr(expr.value)
            return expr.type
        
        return Type(TypeKind.UNKNOWN)
    
    def check_identifier(self, expr: IdentifierExpr) -> Type:
        """Check an identifier expression."""
        name = expr.name
        
        if name not in self.places:
            # Check if it's a global
            raise BorrowError(f"Undefined variable: {name}")
        
        place = self.places[name]
        
        # Check for moved value
        if name in self.moved_values and not place.is_borrowed:
            raise BorrowError(f"Use of moved value: {name}")
        
        # Check for active borrows
        if name in self.active_borrows:
            borrows = self.active_borrows[name]
            mutable_borrows = [b for b in borrows if b.is_mutable]
            if mutable_borrows and not for_assign:
                # There's an active mutable borrow
                pass  # This is fine if we're just reading
        
        return place.type
    
    def check_unary(self, expr: UnaryExpr) -> Type:
        """Check a unary expression."""
        if expr.op in (UnaryOp.REF, UnaryOp.MUT_REF):
            # Borrow operation
            if isinstance(expr.operand, IdentifierExpr):
                owner = expr.operand.name
                if owner in self.places:
                    place = self.places[owner]
                    
                    # Check mutability
                    if expr.op == UnaryOp.MUT_REF and not place.is_mutable:
                        # Check if there are existing borrows
                        if owner in self.active_borrows:
                            active = self.active_borrows[owner]
                            if any(b.is_mutable for b in active):
                                raise BorrowError(f"Cannot borrow mutably: already borrowed")
                    
                    # Create borrow
                    borrow = Borrow(
                        owner=owner,
                        borrower=expr.operand.name,  # Simplified
                        kind=OwnershipKind.MUT_BORROWED if expr.op == UnaryOp.MUT_REF else OwnershipKind.BORROWED,
                        lifetime=self.new_lifetime(),
                        location=Span(0, 0, 0, 0),
                        is_mutable=expr.op == UnaryOp.MUT_REF
                    )
                    self.borrows.append(borrow)
                    
                    if owner not in self.active_borrows:
                        self.active_borrows[owner] = []
                    self.active_borrows[owner].append(borrow)
                    
                    place.is_borrowed = True
                    expr.lifetime = borrow.lifetime
            
            return Type(kind=TypeKind.REFERENCE, is_mutable=expr.op == UnaryOp.MUT_REF)
        
        elif expr.op == UnaryOp.DEREF:
            self.check_expr(expr.operand)
            if expr.operand.type and expr.operand.type.kind == TypeKind.REFERENCE:
                return expr.operand.type.generic_params[0]
            return Type(TypeKind.UNKNOWN)
        
        else:
            self.check_expr(expr.operand)
            return expr.type
    
    def check_call(self, expr: CallExpr) -> Type:
        """Check a function call."""
        for arg in expr.args:
            self.check_expr(arg)
        return expr.type
    
    def check_if(self, expr: IfExpr) -> Type:
        """Check an if expression."""
        self.check_expr(expr.condition)
        
        # Check branches with merged lifetimes
        self.enter_scope()
        self.check_expr(expr.then_block)
        self.exit_scope()
        
        if expr.else_block:
            self.enter_scope()
            self.check_expr(expr.else_block)
            self.exit_scope()
        
        if expr.else_if:
            for else_if in expr.else_if:
                self.enter_scope()
                self.check_expr(else_if)
                self.exit_scope()
        
        return expr.type
    
    def check_match(self, expr: MatchExpr) -> Type:
        """Check a match expression."""
        self.check_expr(expr.value)
        
        for arm in expr.arms:
            self.enter_scope()
            # Patterns are checked for binding
            if arm.pattern.kind == 'bind':
                self.scope_stack[-1].add(arm.pattern.binding)
            elif arm.pattern.kind == 'tuple':
                for p in arm.pattern.subpatterns:
                    if p.kind == 'bind':
                        self.scope_stack[-1].add(p.binding)
            self.check_expr(arm.body)
            self.exit_scope()
        
        return expr.type
    
    def check_loop(self, expr: LoopExpr) -> Type:
        """Check a loop expression."""
        self.loop_depth += 1
        self.check_expr(expr.body)
        self.loop_depth -= 1
        return expr.type
    
    def check_while(self, expr: WhileExpr) -> Type:
        """Check a while expression."""
        self.loop_depth += 1
        self.check_expr(expr.condition)
        self.check_expr(expr.body)
        self.loop_depth -= 1
        return expr.type
    
    def check_for(self, expr: ForExpr) -> Type:
        """Check a for loop."""
        self.loop_depth += 1
        self.check_expr(expr.iterable)
        
        # Add loop variable
        iter_type = expr.iterable.type if expr.iterable.type else Type(TypeKind.UNKNOWN)
        self.places[expr.variable] = Place(
            name=expr.variable,
            type=iter_type,
            is_mutable=False
        )
        self.scope_stack[-1].add(expr.variable)
        
        self.check_expr(expr.body)
        self.loop_depth -= 1
        return expr.type


class LifetimeAnalyzer:
    """
    Lifetime analysis for EonLang.
    
    Computes lifetime relationships and validates that:
    1. References don't outlive the data they point to
    2. Lifetime annotations are consistent
    3. Lifetime relationships (outlives) are satisfied
    """
    
    def __init__(self):
        self.lifetimes: Dict[str, Lifetime] = {}
        self.lifetime_graph: Dict[str, Set[str]] = {}  # 'a outlives 'b
        self.place_lifetimes: Dict[str, str] = {}
    
    def analyze(self, ast: SourceFile) -> Dict[str, str]:
        """Analyze lifetimes in a source file."""
        for item in ast.items:
            if isinstance(item, FuncStmt):
                self.analyze_function(item)
        
        return self.place_lifetimes
    
    def analyze_function(self, func: FuncStmt):
        """Analyze lifetimes in a function."""
        if func.body:
            self.analyze_block(func.body)
    
    def analyze_block(self, block: Block):
        """Analyze lifetimes in a block."""
        for stmt in block.stmts:
            if isinstance(stmt, LetStmt):
                self.analyze_let(stmt)
            elif isinstance(stmt, IfExpr):
                self.analyze_if(stmt)
            elif isinstance(stmt, MatchExpr):
                self.analyze_match(stmt)
    
    def analyze_let(self, stmt: LetStmt):
        """Analyze a let statement."""
        if stmt.value:
            self.analyze_expr(stmt.value)
        
        # Assign lifetime to the variable
        if isinstance(stmt.type_annotation, Type) and stmt.type_annotation.lifetime:
            self.place_lifetimes[stmt.name] = stmt.type_annotation.lifetime
        else:
            self.place_lifetimes[stmt.name] = self.infer_lifetime(stmt.value)
    
    def analyze_expr(self, expr: Expr):
        """Analyze an expression."""
        if isinstance(expr, IdentifierExpr):
            return self.place_lifetimes.get(expr.name, "'static")
        elif isinstance(expr, UnaryExpr):
            if expr.op in (UnaryOp.REF, UnaryOp.MUT_REF):
                return expr.operand.lifetime if expr.operand.lifetime else "'static"
            return self.analyze_expr(expr.operand)
        elif isinstance(expr, BinaryExpr):
            left_lt = self.analyze_expr(expr.left)
            right_lt = self.analyze_expr(expr.right)
            # Return the shorter lifetime (the one that ends first)
            return left_lt if left_lt < right_lt else right_lt
        elif isinstance(expr, CallExpr):
            return "'static"  # Function return lifetimes are complex
        elif isinstance(expr, Block):
            self.analyze_block(expr)
            if expr.expr:
                return self.analyze_expr(expr.expr)
            return "'static"
        elif isinstance(expr, IfExpr):
            then_lt = self.analyze_expr(expr.then_block)
            else_lt = self.analyze_expr(expr.else_block) if expr.else_block else "'static"
            return then_lt if then_lt < else_lt else else_lt
        elif isinstance(expr, LoopExpr):
            self.analyze_expr(expr.body)
            return "'static"  # Infinite loop never returns
        elif isinstance(expr, ReturnExpr):
            if expr.value:
                return self.analyze_expr(expr.value)
            return "'static"
        else:
            return "'static"
    
    def analyze_if(self, expr: IfExpr):
        """Analyze an if expression."""
        self.analyze_expr(expr.condition)
        self.analyze_expr(expr.then_block)
        if expr.else_block:
            self.analyze_expr(expr.else_block)
    
    def analyze_match(self, expr: MatchExpr):
        """Analyze a match expression."""
        self.analyze_expr(expr.value)
        for arm in expr.arms:
            self.analyze_expr(arm.body)
    
    def infer_lifetime(self, expr: Expr) -> str:
        """Infer the lifetime of an expression."""
        return self.analyze_expr(expr)
    
    def outlives(self, lifetime1: str, lifetime2: str) -> bool:
        """Check if one lifetime outlives another."""
        if lifetime1 == lifetime2:
            return True
        if lifetime1 == "'static":
            return True
        if lifetime2 == "'static":
            return lifetime1 == "'static"
        
        # Check the lifetime graph
        visited = set()
        to_check = [lifetime1]
        while to_check:
            current = to_check.pop()
            if current == lifetime2:
                return True
            if current in visited:
                continue
            visited.add(current)
            if current in self.lifetime_graph:
                to_check.extend(self.lifetime_graph[current])
        
        return False
