"""
Type inference using Hindley-Milner algorithm.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from .ast import *
from .ir import *


class TypeError(Exception):
    """Raised when type checking fails."""
    def __init__(self, message: str, span: Optional[Span] = None):
        self.message = message
        self.span = span
        super().__init__(f"Type error: {message}")


@dataclass
class Substitution:
    """A substitution mapping type variables to types."""
    map: Dict[str, Type] = field(default_factory=dict)
    
    def __add__(self, other: 'Substitution') -> 'Substitution':
        """Compose two substitutions."""
        result = Substitution(map=self.map.copy())
        result.map.update(other.map)
        return result
    
    def apply(self, type_: Type) -> Type:
        """Apply substitution to a type."""
        if type_.id and type_.id in self.map:
            return self.map[type_.id]
        
        new_type = type_.copy()
        new_type.generic_params = [self.apply(p) for p in new_type.generic_params]
        new_type.fields = {k: self.apply(v) for k, v in new_type.fields.items()}
        return new_type
    
    def apply_expr(self, expr: Expr) -> Expr:
        """Apply substitution to an expression's type."""
        if expr.type:
            expr.type = self.apply(expr.type)
        return expr


class TypeUnificationError(Exception):
    """Raised when type unification fails."""
    pass


class TypeInferrer:
    """
    Hindley-Milner type inference for EonLang.
    
    Implements Algorithm W with extensions for:
    - Records and struct types
    - Subtyping
    - Lifetime annotations
    - Trait constraints
    """
    
    def __init__(self):
        self.type_vars: Dict[str, int] = {}  # Name to unique ID
        self.var_counter = 0
        self.constraints: List[Tuple[Type, Type]] = []
        self.env: Dict[str, Type] = {}
        self.structs: Dict[str, StructStmt] = {}
        self.enums: Dict[str, EnumStmt] = {}
        self.traits: Dict[str, TraitStmt] = {}
        self.impls: List[ImplStmt] = []
        self.functions: Dict[str, FuncStmt] = {}
        self.builtins: Dict[str, Type] = {}
        self._init_builtins()
    
    def _init_builtins(self):
        """Initialize built-in types and functions."""
        # Primitive types
        self.env['i8'] = Type(TypeKind.INT, name='i8', size=1)
        self.env['i16'] = Type(TypeKind.INT, name='i16', size=2)
        self.env['i32'] = Type(TypeKind.INT, name='i32', size=4)
        self.env['i64'] = Type(TypeKind.INT, name='i64', size=8)
        self.env['i128'] = Type(TypeKind.INT, name='i128', size=16)
        self.env['isize'] = Type(TypeKind.INT, name='isize', size=8)
        
        self.env['u8'] = Type(TypeKind.UINT, name='u8', size=1)
        self.env['u16'] = Type(TypeKind.UINT, name='u16', size=2)
        self.env['u32'] = Type(TypeKind.UINT, name='u32', size=4)
        self.env['u64'] = Type(TypeKind.UINT, name='u64', size=8)
        self.env['u128'] = Type(TypeKind.UINT, name='u128', size=16)
        self.env['usize'] = Type(TypeKind.UINT, name='usize', size=8)
        
        self.env['f32'] = Type(TypeKind.FLOAT, name='f32', size=4)
        self.env['f64'] = Type(TypeKind.DOUBLE, name='f64', size=8)
        
        self.env['bool'] = Type(TypeKind.BOOL, name='bool')
        self.env['char'] = Type(TypeKind.CHAR, name='char')
        self.env['str'] = Type(TypeKind.STRING, name='str')
        self.env['void'] = Type(TypeKind.UNIT, name='void')
        self.env['unit'] = Type(TypeKind.UNIT, name='void')
        self.env['never'] = Type(TypeKind.NEVER, name='!')
        
        # Built-in functions
        self.builtins['print'] = Type(
            kind=TypeKind.FUNCTION,
            name='fn',
            generic_params=[Type(TypeKind.GENERIC, name='T'), Type(TypeKind.UNIT)]
        )
        self.builtins['println'] = Type(
            kind=TypeKind.FUNCTION,
            name='fn',
            generic_params=[Type(TypeKind.GENERIC, name='T'), Type(TypeKind.UNIT)]
        )
        self.builtins['panic'] = Type(
            kind=TypeKind.FUNCTION,
            name='fn',
            generic_params=[Type(TypeKind.STRING), Type(TypeKind.NEVER)]
        )
        self.builtins['assert'] = Type(
            kind=TypeKind.FUNCTION,
            name='fn',
            generic_params=[Type(TypeKind.BOOL, name='bool'), Type(TypeKind.UNIT)]
        )
    
    def new_type_var(self, name: str = "") -> Type:
        """Create a new type variable."""
        if name:
            var_name = f"'{name}_{self.type_vars.get(name, 0)}"
            if name in self.type_vars:
                self.type_vars[name] += 1
            else:
                self.type_vars[name] = 0
        else:
            self.var_counter += 1
            var_name = f"'t{self.var_counter}"
        
        return Type(kind=TypeKind.TYPE_VAR, id=var_name)
    
    def fresh(self, type_: Type) -> Type:
        """Create a fresh copy of a type with new variables."""
        if type_.id:
            return self.new_type_var()
        
        new_type = type_.copy()
        new_type.generic_params = [self.fresh(p) for p in new_type.generic_params]
        new_type.fields = {k: self.fresh(v) for k, v in new_type.fields.items()}
        return new_type
    
    def occurs_check(self, var: str, type_: Type) -> bool:
        """Check if a type variable occurs in a type."""
        if type_.id == var:
            return True
        for param in type_.generic_params:
            if self.occurs_check(var, param):
                return True
        for field_type in type_.fields.values():
            if self.occurs_check(var, field_type):
                return True
        return False
    
    def unify(self, t1: Type, t2: Type) -> Substitution:
        """Unify two types."""
        # Apply any existing substitutions
        t1 = t1 if not t1.id else t1
        t2 = t2 if not t2.id else t2
        
        # Same type
        if t1.kind == t2.kind and t1.name == t2.name:
            if t1.kind not in (TypeKind.GENERIC, TypeKind.FUNCTION, TypeKind.TUPLE):
                return Substitution()
        
        # Type variable
        if t1.kind == TypeKind.TYPE_VAR:
            if t1.id == t2.id:
                return Substitution()
            if self.occurs_check(t1.id, t2):
                raise TypeUnificationError(f"Recursive type detected: {t1.id} in {t2}")
            return Substitution(map={t1.id: t2})
        
        if t2.kind == TypeKind.TYPE_VAR:
            if self.occurs_check(t2.id, t1):
                raise TypeUnificationError(f"Recursive type detected: {t2.id} in {t1}")
            return Substitution(map={t2.id: t1})
        
        # Reference types
        if t1.kind == TypeKind.REFERENCE and t2.kind == TypeKind.REFERENCE:
            sub = self.unify(t1.generic_params[0], t2.generic_params[0])
            return sub
        
        # Pointer types
        if t1.kind == TypeKind.POINTER and t2.kind == TypeKind.POINTER:
            return self.unify(t1.generic_params[0], t2.generic_params[0])
        
        # Array types
        if t1.kind == TypeKind.ARRAY and t2.kind == TypeKind.ARRAY:
            return self.unify(t1.generic_params[0], t2.generic_params[0])
        
        # Tuple types
        if t1.kind == TypeKind.TUPLE and t2.kind == TypeKind.TUPLE:
            if len(t1.generic_params) != len(t2.generic_params):
                raise TypeUnificationError(f"Tuple length mismatch: {t1} vs {t2}")
            sub = Substitution()
            for p1, p2 in zip(t1.generic_params, t2.generic_params):
                sub = sub + self.unify(sub.apply(p1), sub.apply(p2))
            return sub
        
        # Function types
        if t1.kind == TypeKind.FUNCTION and t2.kind == TypeKind.FUNCTION:
            if len(t1.generic_params) != len(t2.generic_params):
                raise TypeUnificationError(f"Function parameter count mismatch")
            sub = Substitution()
            for p1, p2 in zip(t1.generic_params, t2.generic_params):
                sub = sub + self.unify(sub.apply(p1), sub.apply(p2))
            return sub
        
        # Struct types
        if t1.kind == TypeKind.STRUCT and t2.kind == TypeKind.STRUCT:
            if t1.name != t2.name:
                raise TypeUnificationError(f"Struct name mismatch: {t1.name} vs {t2.name}")
            sub = Substitution()
            for (f1, tp1), (f2, tp2) in zip(t1.fields.items(), t2.fields.items()):
                if f1 != f2:
                    raise TypeUnificationError(f"Field name mismatch: {f1} vs {f2}")
                sub = sub + self.unify(sub.apply(tp1), sub.apply(tp2))
            return sub
        
        # Generic types
        if t1.kind == TypeKind.GENERIC and t2.kind == TypeKind.GENERIC:
            if t1.name != t2.name:
                raise TypeUnificationError(f"Generic type mismatch: {t1.name} vs {t2.name}")
            if len(t1.generic_params) != len(t2.generic_params):
                raise TypeUnificationError(f"Generic parameter count mismatch")
            sub = Substitution()
            for p1, p2 in zip(t1.generic_params, t2.generic_params):
                sub = sub + self.unify(sub.apply(p1), sub.apply(p2))
            return sub
        
        # Unknown type (inferred later)
        if t1.kind == TypeKind.UNKNOWN:
            return Substitution()
        if t2.kind == TypeKind.UNKNOWN:
            return Substitution()
        
        raise TypeUnificationError(f"Cannot unify {t1} with {t2}")
    
    def infer(self, ast: SourceFile) -> Dict[str, Type]:
        """Infer types for a complete source file."""
        type_map: Dict[str, Type] = {}
        
        # First pass: collect declarations
        for item in ast.items:
            if isinstance(item, FuncStmt):
                self.functions[item.name] = item
            elif isinstance(item, StructStmt):
                self.structs[item.name] = item
            elif isinstance(item, EnumStmt):
                self.enums[item.name] = item
            elif isinstance(item, TraitStmt):
                self.traits[item.name] = item
            elif isinstance(item, ImplStmt):
                self.impls.append(item)
        
        # Second pass: type inference
        for item in ast.items:
            if isinstance(item, FuncStmt):
                func_type = self.infer_function(item)
                type_map[item.name] = func_type
                self.env[item.name] = func_type
            elif isinstance(item, StructStmt):
                struct_type = self.infer_struct(item)
                type_map[item.name] = struct_type
                self.env[item.name] = struct_type
            elif isinstance(item, EnumStmt):
                enum_type = self.infer_enum(item)
                type_map[item.name] = enum_type
                self.env[item.name] = enum_type
            elif isinstance(item, TraitStmt):
                self.infer_trait(item)
            elif isinstance(item, ImplStmt):
                self.infer_impl(item)
        
        return type_map
    
    def infer_function(self, func: FuncStmt) -> Type:
        """Infer types for a function."""
        # Create fresh type variables for type parameters
        type_params = {tp: self.new_type_var(tp) for tp in func.type_params}
        
        # Build function type
        param_types = []
        for name, param_type, is_mut in func.params:
            t = self.resolve_type(param_type, type_params)
            param_types.append(t)
        
        ret_type = self.resolve_type(func.return_type, type_params)
        
        func_type = Type(
            kind=TypeKind.FUNCTION,
            name=func.name,
            generic_params=[*param_types, ret_type]
        )
        
        # Infer body if present
        if func.body:
            # Create new environment with function params
            local_env = self.env.copy()
            for (name, param_type, is_mut), param_t in zip(func.params, param_types):
                local_env[name] = param_t
            
            try:
                body_type = self.infer_expr(func.body, local_env)
                
                # Unify return type
                sub = self.unify(ret_type, body_type)
                
                # Apply substitutions
                func_type = sub.apply(func_type)
            except TypeUnificationError as e:
                raise TypeError(str(e), func.span)
        
        return func_type
    
    def infer_struct(self, struct: StructStmt) -> Type:
        """Infer types for a struct."""
        type_params = {tp: self.new_type_var(tp) for tp in struct.type_params}
        
        fields = {}
        for field_name, field_type, _ in struct.fields:
            fields[field_name] = self.resolve_type(field_type, type_params)
        
        struct_type = Type(
            kind=TypeKind.STRUCT,
            name=struct.name,
            fields=fields
        )
        
        return struct_type
    
    def infer_enum(self, enum: EnumStmt) -> Type:
        """Infer types for an enum."""
        type_params = {tp: self.new_type_var(tp) for tp in enum.type_params}
        
        variants = []
        for var_name, var_types in enum.variants:
            if var_types is None:
                variants.append((var_name, []))
            elif isinstance(var_types, list):
                resolved = [self.resolve_type(t, type_params) for t in var_types]
                variants.append((var_name, resolved))
            else:
                variants.append((var_name, var_types))
        
        enum_type = Type(
            kind=TypeKind.ENUM,
            name=enum.name,
            variants=variants
        )
        
        return enum_type
    
    def infer_trait(self, trait: TraitStmt) -> Type:
        """Infer types for a trait."""
        type_params = {tp: self.new_type_var(tp) for tp in trait.type_params}
        
        methods = []
        for method in trait.methods:
            method_type = self.infer_function(method)
            methods.append((method.name, method_type))
        
        return Type(
            kind=TypeKind.TRAIT,
            name=trait.name,
            methods=dict(methods)
        )
    
    def infer_impl(self, impl: ImplStmt) -> Type:
        """Infer types for an impl block."""
        for method in impl.methods:
            self.infer_function(method)
        
        return Type(
            kind=TypeKind.IMPL,
            name=impl.type_name
        )
    
    def resolve_type(self, type_: Type, type_params: Dict[str, Type]) -> Type:
        """Resolve a type with given type parameters."""
        if type_.id in type_params:
            return type_params[type_.id]
        
        if type_.kind == TypeKind.GENERIC:
            resolved_params = [self.resolve_type(p, type_params) for p in type_.generic_params]
            return Type(
                kind=TypeKind.GENERIC,
                name=type_.name,
                generic_params=resolved_params
            )
        
        return type_
    
    def infer_expr(self, expr: Expr, env: Dict[str, Type]) -> Type:
        """Infer the type of an expression."""
        if isinstance(expr, LiteralExpr):
            return self.infer_literal(expr)
        elif isinstance(expr, IdentifierExpr):
            return self.infer_identifier(expr, env)
        elif isinstance(expr, UnaryExpr):
            return self.infer_unary(expr, env)
        elif isinstance(expr, BinaryExpr):
            return self.infer_binary(expr, env)
        elif isinstance(expr, CallExpr):
            return self.infer_call(expr, env)
        elif isinstance(expr, IfExpr):
            return self.infer_if(expr, env)
        elif isinstance(expr, MatchExpr):
            return self.infer_match(expr, env)
        elif isinstance(expr, Block):
            return self.infer_block(expr, env)
        elif isinstance(expr, ReturnExpr):
            return self.infer_return(expr, env)
        elif isinstance(expr, LoopExpr):
            return self.infer_loop(expr, env)
        elif isinstance(expr, WhileExpr):
            return self.infer_while(expr, env)
        elif isinstance(expr, ForExpr):
            return self.infer_for(expr, env)
        elif isinstance(expr, TupleExpr):
            return self.infer_tuple(expr, env)
        elif isinstance(expr, ArrayExpr):
            return self.infer_array(expr, env)
        elif isinstance(expr, FieldAccessExpr):
            return self.infer_field_access(expr, env)
        elif isinstance(expr, IndexExpr):
            return self.infer_index(expr, env)
        elif isinstance(expr, StructExpr):
            return self.infer_struct_expr(expr, env)
        elif isinstance(expr, CastExpr):
            return self.infer_cast(expr, env)
        elif isinstance(expr, RangeExpr):
            return self.infer_range(expr, env)
        elif isinstance(expr, SizeOfExpr):
            expr.type = Type(TypeKind.UINT, name='usize')
            return expr.type
        elif isinstance(expr, LetExpr):
            return self.infer_let_expr(expr, env)
        else:
            return Type(TypeKind.UNKNOWN)
    
    def infer_literal(self, expr: LiteralExpr) -> Type:
        """Infer type of a literal."""
        if expr.token_type == 'int':
            expr.type = Type(TypeKind.INT, name='i32', size=4)
        elif expr.token_type == 'float':
            expr.type = Type(TypeKind.FLOAT, name='f64', size=8)
        elif expr.token_type == 'string':
            expr.type = Type(TypeKind.STRING, name='str')
        elif expr.token_type == 'char':
            expr.type = Type(TypeKind.CHAR, name='char')
        elif expr.token_type == 'bool':
            expr.type = Type(TypeKind.BOOL, name='bool')
        else:
            expr.type = Type(TypeKind.UNKNOWN)
        return expr.type
    
    def infer_identifier(self, expr: IdentifierExpr, env: Dict[str, Type]) -> Type:
        """Infer type of an identifier."""
        if expr.name in env:
            expr.type = env[expr.name]
        elif expr.name in self.env:
            expr.type = self.env[expr.name]
        else:
            raise TypeError(f"Undefined variable: {expr.name}")
        return expr.type
    
    def infer_unary(self, expr: UnaryExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a unary expression."""
        operand_type = self.infer_expr(expr.operand, env)
        
        if expr.op == UnaryOp.NEG:
            if operand_type.kind in (TypeKind.INT, TypeKind.FLOAT, TypeKind.DOUBLE):
                expr.type = operand_type
            else:
                raise TypeError(f"Cannot negate type: {operand_type}")
        elif expr.op == UnaryOp.NOT:
            expr.type = Type(TypeKind.BOOL, name='bool')
        elif expr.op == UnaryOp.BITNOT:
            if operand_type.kind == TypeKind.INT or operand_type.kind == TypeKind.UINT:
                expr.type = operand_type
            else:
                raise TypeError(f"Cannot bitwise negate type: {operand_type}")
        elif expr.op == UnaryOp.REF:
            expr.type = Type(kind=TypeKind.REFERENCE, generic_params=[operand_type])
        elif expr.op == UnaryOp.MUT_REF:
            expr.type = Type(kind=TypeKind.REFERENCE, generic_params=[operand_type], is_mutable=True)
        elif expr.op == UnaryOp.DEREF:
            if operand_type.kind == TypeKind.REFERENCE or operand_type.kind == TypeKind.POINTER:
                expr.type = operand_type.generic_params[0]
            else:
                raise TypeError(f"Cannot dereference type: {operand_type}")
        else:
            expr.type = Type(TypeKind.UNKNOWN)
        
        return expr.type
    
    def infer_binary(self, expr: BinaryExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a binary expression."""
        left_type = self.infer_expr(expr.left, env)
        right_type = self.infer_expr(expr.right, env)
        
        # Arithmetic operators
        if expr.op in (BinaryOp.ADD, BinaryOp.SUB, BinaryOp.MUL, BinaryOp.DIV, BinaryOp.REM):
            self.unify(left_type, right_type)
            expr.type = left_type
        # Comparison operators
        elif expr.op in (BinaryOp.EQ, BinaryOp.NE, BinaryOp.LT, BinaryOp.GT, BinaryOp.LE, BinaryOp.GE):
            expr.type = Type(TypeKind.BOOL, name='bool')
        # Logical operators
        elif expr.op in (BinaryOp.AND, BinaryOp.OR):
            self.unify(left_type, Type(TypeKind.BOOL, name='bool'))
            self.unify(right_type, Type(TypeKind.BOOL, name='bool'))
            expr.type = Type(TypeKind.BOOL, name='bool')
        # Bitwise operators
        elif expr.op in (BinaryOp.AND, BinaryOp.OR, BinaryOp.XOR, BinaryOp.SHL, BinaryOp.SHR):
            expr.type = left_type
        else:
            expr.type = Type(TypeKind.UNKNOWN)
        
        return expr.type
    
    def infer_call(self, expr: CallExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a function call."""
        func_type = self.infer_expr(expr.func, env)
        
        if func_type.kind != TypeKind.FUNCTION:
            raise TypeError(f"Cannot call non-function type: {func_type}")
        
        # Infer argument types
        arg_types = [self.infer_expr(arg, env) for arg in expr.args]
        
        # Check parameter count
        expected_params = func_type.generic_params[:-1]
        if len(arg_types) != len(expected_params):
            raise TypeError(
                f"Expected {len(expected_params)} arguments, got {len(arg_types)}"
            )
        
        # Unify argument types with parameter types
        for arg_type, param_type in zip(arg_types, expected_params):
            self.unify(arg_type, param_type)
        
        expr.type = func_type.generic_params[-1]
        return expr.type
    
    def infer_if(self, expr: IfExpr, env: Dict[str, Type]) -> Type:
        """Infer type of an if expression."""
        cond_type = self.infer_expr(expr.condition, env)
        self.unify(cond_type, Type(TypeKind.BOOL, name='bool'))
        
        then_type = self.infer_expr(expr.then_block, env)
        
        if expr.else_block:
            else_type = self.infer_expr(expr.else_block, env)
            expr.type = self.unify(then_type, else_type).apply(then_type)
        elif expr.else_if:
            else_type = self.infer_expr(expr.else_if[0], env)
            for else_if in expr.else_if[1:]:
                else_if_type = self.infer_expr(else_if, env)
                else_type = self.unify(else_type, else_if_type).apply(else_type)
            expr.type = self.unify(then_type, else_type).apply(then_type)
        else:
            expr.type = Type(TypeKind.UNIT, name='void')
        
        return expr.type
    
    def infer_match(self, expr: MatchExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a match expression."""
        self.infer_expr(expr.value, env)
        
        if not expr.arms:
            return Type(TypeKind.UNKNOWN)
        
        # Infer all arm types
        arm_types = []
        for arm in expr.arms:
            arm_type = self.infer_expr(arm.body, env)
            arm_types.append(arm_type)
        
        # Unify all arm types
        result_type = arm_types[0]
        for arm_type in arm_types[1:]:
            result_type = self.unify(result_type, arm_type).apply(result_type)
        
        expr.type = result_type
        return result_type
    
    def infer_block(self, expr: Block, env: Dict[str, Type]) -> Type:
        """Infer type of a block expression."""
        local_env = env.copy()
        
        for stmt in expr.stmts:
            if isinstance(stmt, LetStmt):
                self.infer_let(stmt, local_env)
            elif isinstance(stmt, ExprStmt):
                self.infer_expr(stmt.expr, local_env)
        
        if expr.expr:
            expr.type = self.infer_expr(expr.expr, local_env)
        else:
            expr.type = Type(TypeKind.UNIT, name='void')
        
        return expr.type
    
    def infer_let(self, stmt: LetStmt, env: Dict[str, Type]):
        """Infer type of a let statement."""
        if stmt.value:
            value_type = self.infer_expr(stmt.value, env)
        else:
            value_type = self.new_type_var()
        
        if stmt.type_annotation:
            annotated_type = self.resolve_type(stmt.type_annotation, {})
            self.unify(value_type, annotated_type)
            stmt.value.type = annotated_type
            env[stmt.name] = annotated_type
        else:
            env[stmt.name] = value_type
    
    def infer_return(self, expr: ReturnExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a return expression."""
        if expr.value:
            expr.type = self.infer_expr(expr.value, env)
        else:
            expr.type = Type(TypeKind.UNIT, name='void')
        return expr.type
    
    def infer_loop(self, expr: LoopExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a loop expression."""
        self.infer_expr(expr.body, env)
        expr.type = Type(TypeKind.NEVER, name='!')
        return expr.type
    
    def infer_while(self, expr: WhileExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a while expression."""
        cond_type = self.infer_expr(expr.condition, env)
        self.unify(cond_type, Type(TypeKind.BOOL, name='bool'))
        self.infer_expr(expr.body, env)
        expr.type = Type(TypeKind.UNIT, name='void')
        return expr.type
    
    def infer_for(self, expr: ForExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a for loop."""
        iter_type = self.infer_expr(expr.iterable, env)
        
        local_env = env.copy()
        local_env[expr.variable] = iter_type
        
        self.infer_expr(expr.body, local_env)
        expr.type = Type(TypeKind.UNIT, name='void')
        return expr.type
    
    def infer_tuple(self, expr: TupleExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a tuple literal."""
        element_types = [self.infer_expr(e, env) for e in expr.elements]
        expr.type = Type(kind=TypeKind.TUPLE, generic_params=element_types)
        return expr.type
    
    def infer_array(self, expr: ArrayExpr, env: Dict[str, Type]) -> Type:
        """Infer type of an array literal."""
        if not expr.elements:
            expr.type = Type(kind=TypeKind.ARRAY, generic_params=[Type(TypeKind.UNKNOWN)])
            return expr.type
        
        element_types = [self.infer_expr(e, env) for e in expr.elements]
        
        # Unify all element types
        element_type = element_types[0]
        for et in element_types[1:]:
            element_type = self.unify(element_type, et).apply(element_type)
        
        expr.type = Type(kind=TypeKind.ARRAY, generic_params=[element_type])
        return expr.type
    
    def infer_field_access(self, expr: FieldAccessExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a field access expression."""
        base_type = self.infer_expr(expr.base, env)
        
        if base_type.kind == TypeKind.STRUCT:
            if expr.field in base_type.fields:
                expr.type = base_type.fields[expr.field]
            else:
                raise TypeError(f"Struct {base_type.name} has no field {expr.field}")
        elif base_type.kind == TypeKind.TUPLE:
            # Handle tuple field access
            try:
                idx = int(expr.field)
                expr.type = base_type.generic_params[idx]
            except (ValueError, IndexError):
                raise TypeError(f"Invalid tuple index: {expr.field}")
        else:
            raise TypeError(f"Cannot access field on type: {base_type}")
        
        return expr.type
    
    def infer_index(self, expr: IndexExpr, env: Dict[str, Type]) -> Type:
        """Infer type of an index expression."""
        base_type = self.infer_expr(expr.base, env)
        self.infer_expr(expr.index, env)
        
        if base_type.kind == TypeKind.ARRAY:
            expr.type = base_type.generic_params[0]
        elif base_type.kind == TypeKind.REFERENCE:
            expr.type = base_type.generic_params[0]
        else:
            raise TypeError(f"Cannot index type: {base_type}")
        
        return expr.type
    
    def infer_struct_expr(self, expr: StructExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a struct literal."""
        if expr.name in self.structs:
            struct = self.structs[expr.name]
            field_types = {}
            for field_name, field_type, _ in struct.fields:
                if field_name in expr.fields:
                    field_types[field_name] = self.infer_expr(expr.fields[field_name], env)
                else:
                    field_types[field_name] = field_type
            expr.type = Type(kind=TypeKind.STRUCT, name=expr.name, fields=field_types)
        else:
            raise TypeError(f"Unknown struct: {expr.name}")
        
        return expr.type
    
    def infer_cast(self, expr: CastExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a cast expression."""
        self.infer_expr(expr.value, env)
        expr.type = expr.target_type
        return expr.type
    
    def infer_range(self, expr: RangeExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a range expression."""
        if expr.start:
            start_type = self.infer_expr(expr.start, env)
            expr.type = Type(kind=TypeKind.STRUCT, name='Range', 
                           generic_params=[start_type])
        if expr.end:
            end_type = self.infer_expr(expr.end, env)
            if expr.type:
                self.unify(expr.type, end_type)
            else:
                expr.type = Type(kind=TypeKind.STRUCT, name='Range',
                               generic_params=[end_type])
        return expr.type
    
    def infer_let_expr(self, expr: LetExpr, env: Dict[str, Type]) -> Type:
        """Infer type of a let expression."""
        value_type = self.infer_expr(expr.value, env)
        
        local_env = env.copy()
        if expr.pattern.kind == 'bind':
            local_env[expr.pattern.binding] = value_type
        elif expr.pattern.kind == 'wildcard':
            pass  # Wildcard doesn't bind
        
        expr.type = self.infer_expr(expr.body, local_env)
        return expr.type
