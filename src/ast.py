"""
AST (Abstract Syntax Tree) node definitions for EonLang.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum, auto


class TypeKind(Enum):
    """Kind of a type."""
    UNIT = auto()
    BOOL = auto()
    INT = auto()
    UINT = auto()
    FLOAT = auto()
    DOUBLE = auto()
    CHAR = auto()
    STRING = auto()
    ARRAY = auto()
    TUPLE = auto()
    POINTER = auto()
    REFERENCE = auto()
    FUNCTION = auto()
    STRUCT = auto()
    ENUM = auto()
    GENERIC = auto()
    TYPE_VAR = auto()
    TRAIT = auto()
    IMPL = auto()
    NEVER = auto()
    UNKNOWN = auto()


class BinaryOp(Enum):
    """Binary operators."""
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    REM = auto()
    AND = auto()
    OR = auto()
    XOR = auto()
    SHL = auto()
    SHR = auto()
    EQ = auto()
    NE = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()


class UnaryOp(Enum):
    """Unary operators."""
    NEG = auto()      # -x
    NOT = auto()      # !x
    BITNOT = auto()   # ~x
    DEREF = auto()    # *x
    REF = auto()      # &x
    MUT_REF = auto()  # &mut x


@dataclass
class Span:
    """Source code location span."""
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    filename: str = "<stdin>"
    
    def merge(self, other: 'Span') -> 'Span':
        """Merge two spans."""
        return Span(
            start_line=min(self.start_line, other.start_line),
            start_col=self.start_col if self.start_line <= other.start_line else other.start_col,
            end_line=max(self.end_line, other.end_line),
            end_col=other.end_col if other.end_line >= self.end_line else self.end_col,
            filename=self.filename
        )


@dataclass
class Type:
    """Type representation in the AST."""
    kind: TypeKind
    name: str = ""
    generic_params: List['Type'] = field(default_factory=list)
    fields: Dict[str, 'Type'] = field(default_factory=dict)
    methods: Dict[str, 'FunctionType'] = field(default_factory=dict)
    variants: List[tuple] = field(default_factory=list)  # For enums
    trait_bounds: List['TraitRef'] = field(default_factory=list)
    size: int = 0
    alignment: int = 1
    is_mutable: bool = False
    lifetime: Optional[str] = None
    
    # For type variables (generics)
    id: Optional[str] = None
    constraints: List['Type'] = field(default_factory=list)
    
    def __str__(self) -> str:
        if self.id:
            return f"'{self.id}"
        
        base = self.name or self.kind.name.lower()
        
        if self.generic_params:
            params = ", ".join(str(p) for p in self.generic_params)
            return f"{base}<{params}>"
        
        if self.kind == TypeKind.REFERENCE:
            mut = "mut " if self.is_mutable else ""
            lifetime = f"'{self.lifetime} " if self.lifetime else ""
            return f"&{lifetime}{mut}{self.generic_params[0]}"
        
        if self.kind == TypeKind.POINTER:
            mut = "mut " if self.is_mutable else ""
            return f"*{mut}{self.generic_params[0]}"
        
        if self.kind == TypeKind.ARRAY:
            return f"[{self.generic_params[0]}; {self.fields.get('size', '?')}]"
        
        if self.kind == TypeKind.TUPLE:
            fields = ", ".join(str(f) for f in self.generic_params)
            return f"({fields})"
        
        if self.kind == TypeKind.FUNCTION:
            params = ", ".join(str(p) for p in self.generic_params[:-1])
            ret = self.generic_params[-1] if self.generic_params else "()"
            return f"fn({params}) -> {ret}"
        
        return base
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Type):
            return False
        return self.kind == other.kind and self.name == other.name
    
    def copy(self) -> 'Type':
        """Create a shallow copy of this type."""
        return Type(
            kind=self.kind,
            name=self.name,
            generic_params=list(self.generic_params),
            fields=dict(self.fields),
            methods=dict(self.methods),
            variants=list(self.variants),
            size=self.size,
            alignment=self.alignment,
            is_mutable=self.is_mutable,
            lifetime=self.lifetime,
            id=self.id,
            constraints=list(self.constraints),
        )


@dataclass 
class FunctionType:
    """Function type signature."""
    params: List[Type] = field(default_factory=list)
    ret_type: Type = field(default_factory=lambda: Type(TypeKind.UNIT))
    is_variadic: bool = False
    lifetime: Optional[str] = None


@dataclass
class TraitRef:
    """Reference to a trait constraint."""
    name: str
    type_params: List[Type] = field(default_factory=list)
    method: Optional[str] = None


@dataclass
class Pattern:
    """Pattern matching pattern."""
    kind: str
    value: Any = None
    binding: Optional[str] = None
    types: List[Type] = field(default_factory=list)
    guard: Optional['Expr'] = None
    subpatterns: List['Pattern'] = field(default_factory=list)


@dataclass
class Node:
    """Base class for all AST nodes."""
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


# Expression nodes
@dataclass
class Expr(Node):
    """Base class for expressions."""
    type: Optional[Type] = None
    lifetime: Optional[str] = None
    is_lvalue: bool = False
    is_mutable: bool = False


@dataclass
class LiteralExpr(Expr):
    """Literal value (int, float, string, bool, char)."""
    value: Any = None
    token_type: str = ""


@dataclass
class IdentifierExpr(Expr):
    """Variable identifier."""
    name: str
    declaration: Optional['LetStmt'] = None
    is_weak_ref: bool = False  # For borrow checker


@dataclass
class UnaryExpr(Expr):
    """Unary operation."""
    op: UnaryOp
    operand: Expr


@dataclass
class BinaryExpr(Expr):
    """Binary operation."""
    op: BinaryOp
    left: Expr
    right: Expr


@dataclass
class CallExpr(Expr):
    """Function call."""
    func: Expr
    args: List[Expr] = field(default_factory=list)
    type_args: List[Type] = field(default_factory=list)


@dataclass
class IndexExpr(Expr):
    """Array/slice indexing."""
    base: Expr
    index: Expr


@dataclass
class FieldAccessExpr(Expr):
    """Struct field access."""
    base: Expr
    field: str
    is_method: bool = False


@dataclass
class TupleIndexExpr(Expr):
    """Tuple field access (t.0, t.1, etc.)."""
    base: Expr
    index: int


@dataclass
class RangeExpr(Expr):
    """Range expression (start..end, start..., ...end)."""
    start: Optional[Expr] = None
    end: Optional[Expr] = None
    inclusive: bool = False


@dataclass
class IfExpr(Expr):
    """If expression."""
    condition: Expr
    then_block: 'Block'
    else_block: Optional['Block'] = None
    else_if: List['IfExpr'] = field(default_factory=list)


@dataclass
class MatchExpr(Expr):
    """Match expression."""
    value: Expr
    arms: List['MatchArm'] = field(default_factory=list)


@dataclass
class MatchArm:
    """A single match arm."""
    pattern: Pattern
    body: Expr
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class LoopExpr(Expr):
    """Infinite loop."""
    body: 'Block'
    label: Optional[str] = None


@dataclass
class WhileExpr(Expr):
    """While loop."""
    condition: Expr
    body: 'Block'
    label: Optional[str] = None


@dataclass
class ForExpr(Expr):
    """For loop."""
    variable: str
    iterable: Expr
    body: 'Block'
    label: Optional[str] = None


@dataclass
class Block(Node):
    """Block expression."""
    stmts: List[Node] = field(default_factory=list)
    expr: Optional[Expr] = None
    scope_id: int = 0


@dataclass
class ReturnExpr(Expr):
    """Return statement."""
    value: Optional[Expr] = None


@dataclass
class BreakExpr(Expr):
    """Break statement."""
    value: Optional[Expr] = None
    label: Optional[str] = None


@dataclass
class ContinueExpr(Expr):
    """Continue statement."""
    label: Optional[str] = None


@dataclass
class ArrayExpr(Expr):
    """Array literal."""
    elements: List[Expr] = field(default_factory=list)


@dataclass
class TupleExpr(Expr):
    """Tuple literal."""
    elements: List[Expr] = field(default_factory=list)


@dataclass
class StructExpr(Expr):
    """Struct literal."""
    name: str
    fields: Dict[str, Expr] = field(default_factory=dict)
    base: Optional[Expr] = None  # For struct update syntax


@dataclass
class CastExpr(Expr):
    """Type cast."""
    value: Expr
    target_type: Type


@dataclass
class SizeOfExpr(Expr):
    """Size of type expression."""
    type_arg: Type


@dataclass
class AlignOfExpr(Expr):
    """Alignment of type expression."""
    type_arg: Type


@dataclass
class LetExpr(Expr):
    """Let binding expression (let x = expr; body)."""
    pattern: 'Pattern'
    value: Expr
    body: Expr


# Statement nodes
@dataclass
class Stmt(Node):
    """Base class for statements."""
    pass


@dataclass
class LetStmt(Stmt):
    """Let statement."""
    name: str
    type_annotation: Optional[Type] = None
    value: Optional[Expr] = None
    is_mutable: bool = False
    is_const: bool = False
    is_static: bool = False
    is_public: bool = False
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class ExprStmt(Stmt):
    """Expression statement."""
    expr: Expr


@dataclass
class AssignStmt(Stmt):
    """Assignment statement."""
    target: Expr
    op: Optional[str] = None  # For +=, -=, etc.
    value: Expr


@dataclass
class FuncStmt(Stmt):
    """Function declaration."""
    name: str
    params: List[tuple] = field(default_factory=list)  # (name, type, is_mutable)
    return_type: Type = field(default_factory=lambda: Type(TypeKind.UNIT))
    body: Optional[Block] = None
    type_params: List[str] = field(default_factory=list)
    is_public: bool = False
    is_extern: bool = False
    extern_name: Optional[str] = None
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class StructStmt(Stmt):
    """Struct declaration."""
    name: str
    fields: List[tuple] = field(default_factory=list)  # (name, type, is_public)
    methods: List[FuncStmt] = field(default_factory=list)
    type_params: List[str] = field(default_factory=list)
    is_public: bool = False
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class EnumStmt(Stmt):
    """Enum declaration."""
    name: str
    variants: List[tuple] = field(default_factory=list)  # (name, types) or (name,)
    type_params: List[str] = field(default_factory=list)
    is_public: bool = False
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class TraitStmt(Stmt):
    """Trait declaration."""
    name: str
    methods: List[FuncStmt] = field(default_factory=list)
    associated_types: Dict[str, Type] = field(default_factory=dict)
    type_params: List[str] = field(default_factory=list)
    is_public: bool = False
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class ImplStmt(Stmt):
    """Impl block."""
    type_params: List[str] = field(default_factory=list)
    trait_name: Optional[str] = None
    type_name: str = ""
    methods: List[FuncStmt] = field(default_factory=list)
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class UseStmt(Stmt):
    """Use statement (import)."""
    path: str
    alias: Optional[str] = None
    is_public: bool = False


@dataclass
class ModStmt(Stmt):
    """Module declaration."""
    name: str
    items: List[Node] = field(default_factory=list)
    is_public: bool = False
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class TypeStmt(Stmt):
    """Type alias."""
    name: str
    type_params: List[str] = field(default_factory=list)
    value: Type
    is_public: bool = False
    span: Span = field(default_factory=lambda: Span(0, 0, 0, 0))


@dataclass
class DeferStmt(Stmt):
    """Defer statement."""
    expr: Expr


@dataclass
class WhileStmt(Stmt):
    """While statement."""
    condition: Expr
    body: Block
    label: Optional[str] = None


@dataclass
class ForStmt(Stmt):
    """For statement."""
    variable: str
    iterable: Expr
    body: Block
    label: Optional[str] = None


@dataclass
class LoopStmt(Stmt):
    """Loop statement."""
    body: Block
    label: Optional[str] = None


@dataclass
class BreakStmt(Stmt):
    """Break statement."""
    value: Optional[Expr] = None
    label: Optional[str] = None


@dataclass
class ContinueStmt(Stmt):
    """Continue statement."""
    label: Optional[str] = None


@dataclass
class ReturnStmt(Stmt):
    """Return statement."""
    value: Optional[Expr] = None


@dataclass
class EmptyStmt(Stmt):
    """Empty statement (just a semicolon)."""
    pass


# Top-level nodes
@dataclass
class SourceFile(Node):
    """Complete source file."""
    items: List[Node] = field(default_factory=list)
    filename: str = "<stdin>"
