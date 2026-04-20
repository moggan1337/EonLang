"""
Code generator for EonLang - Converts AST to IR.
"""

from typing import Dict, List, Optional, Set, Any
from .ast import *
from .ir import *
from .typeinfer import TypeInferrer
from .borrow import BorrowChecker


class CodegenError(Exception):
    """Raised when code generation fails."""
    def __init__(self, message: str, span: Optional[Span] = None):
        self.message = message
        self.span = span
        super().__init__(f"Codegen error: {message}")


@dataclass
class Codegen:
    """
    Code generator for EonLang.
    
    Generates IR from the AST, handling:
    - Control flow
    - Function calls
    - Memory management
    - Pattern matching compilation
    """
    
    module: Module
    type_inferrer: TypeInferrer
    borrow_checker: BorrowChecker
    
    current_function: Optional[Function] = None
    current_block: Optional[BasicBlock] = None
    builder: Optional[IRBuilder] = None
    
    locals: Dict[str, Value] = {}
    blocks: List[BasicBlock] = []
    break_targets: List[BasicBlock] = []
    continue_targets: List[BasicBlock] = []
    
    def __init__(self):
        self.module = Module()
        self.type_inferrer = TypeInferrer()
        self.borrow_checker = BorrowChecker()
        self.builder = IRBuilder(self.module)
    
    def generate(self, ast: SourceFile) -> Module:
        """Generate IR from an AST."""
        # Type check first
        self.type_inferrer.infer(ast)
        
        # Borrow check
        self.borrow_checker.check_file(ast)
        
        # Generate IR
        for item in ast.items:
            if isinstance(item, FuncStmt):
                self.generate_function(item)
            elif isinstance(item, StructStmt):
                self.generate_struct(item)
            elif isinstance(item, EnumStmt):
                self.generate_enum(item)
            elif isinstance(item, GlobalVariable):
                self.generate_global(item)
        
        return self.module
    
    def generate_function(self, func: FuncStmt):
        """Generate IR for a function."""
        ir_func = Function(
            name=func.name,
            return_type=func.return_type
        )
        ir_func.params = func.params
        
        self.module.add_function(ir_func)
        self.current_function = ir_func
        
        # Create entry block
        entry = ir_func.add_block('entry')
        entry.is_entry = True
        self.builder.set_function(ir_func)
        self.builder.set_block(entry)
        
        # Allocate parameters
        self.locals.clear()
        for i, (name, type_, is_mut) in enumerate(func.params):
            alloca = self.builder.alloca(type_, name)
            self.builder.store(ConstantInt(value=i), alloca)
            self.locals[name] = alloca
        
        # Generate body
        if func.body:
            self.generate_block(func.body)
        
        # Ensure function has a terminator
        if not self.current_block.terminator:
            if func.return_type.kind == TypeKind.UNIT:
                self.builder.ret_void()
            else:
                # Function should have returned
                self.builder.unreachable()
        
        self.current_function = None
    
    def generate_struct(self, struct: StructStmt):
        """Generate IR for a struct type."""
        # Structs are represented as aggregate types in LLVM
        pass  # Types are handled by the type system
    
    def generate_enum(self, enum: EnumStmt):
        """Generate IR for an enum type."""
        # Enums are represented with a tag and optional data
        pass
    
    def generate_global(self, gv: GlobalVariable):
        """Generate IR for a global variable."""
        self.module.add_global(gv)
    
    def generate_block(self, block: Block):
        """Generate IR for a block."""
        prev_block = self.current_block
        
        for stmt in block.stmts:
            self.generate_stmt(stmt)
        
        if block.expr:
            self.generate_expr(block.expr)
            if block.expr.type and block.expr.type.kind != TypeKind.UNIT:
                if not self.current_block.terminator:
                    self.builder.ret(self.locals.get(block.expr.name, 
                                                   ConstantInt(value=0)))
        
        self.current_block = prev_block
    
    def generate_stmt(self, stmt: Stmt):
        """Generate IR for a statement."""
        if isinstance(stmt, LetStmt):
            self.generate_let(stmt)
        elif isinstance(stmt, ExprStmt):
            self.generate_expr(stmt.expr)
        elif isinstance(stmt, AssignStmt):
            self.generate_assign(stmt)
        elif isinstance(stmt, IfExpr):
            self.generate_if(stmt)
        elif isinstance(stmt, MatchExpr):
            self.generate_match(stmt)
        elif isinstance(stmt, LoopExpr):
            self.generate_loop(stmt)
        elif isinstance(stmt, WhileExpr):
            self.generate_while(stmt)
        elif isinstance(stmt, ForExpr):
            self.generate_for(stmt)
        elif isinstance(stmt, ReturnStmt):
            self.generate_return(stmt)
        elif isinstance(stmt, BreakStmt):
            self.generate_break(stmt)
        elif isinstance(stmt, ContinueStmt):
            self.generate_continue(stmt)
    
    def generate_let(self, stmt: LetStmt):
        """Generate IR for a let statement."""
        value = None
        if stmt.value:
            value = self.generate_expr(stmt.value)
        
        # Allocate variable
        type_ = stmt.type_annotation or (stmt.value.type if stmt.value else Type(TypeKind.UNKNOWN))
        alloca = self.builder.alloca(type_, stmt.name)
        
        if value is not None:
            self.builder.store(value, alloca)
        
        self.locals[stmt.name] = alloca
    
    def generate_assign(self, stmt: AssignStmt):
        """Generate IR for an assignment."""
        target = self.generate_lvalue(stmt.target)
        value = self.generate_expr(stmt.value)
        
        if stmt.op:
            # Compound assignment (+=, -=, etc.)
            current = self.builder.load(target, stmt.target.type)
            op = self.get_binary_op_for_assign(stmt.op)
            result = self.builder.binary_op(op, current, value, stmt.target.type)
            value = result
        
        self.builder.store(value, target)
    
    def generate_assign_op(self, left: Value, right: Value, op: str, type_: Type) -> Value:
        """Generate a compound assignment operation."""
        opcode = self.get_binary_op_for_assign(op)
        return self.builder.binary_op(opcode, left, right, type_)
    
    def get_binary_op_for_assign(self, op: str) -> OpCode:
        """Get the IR opcode for an assignment operator."""
        mapping = {
            '+=': OpCode.ADD,
            '-=': OpCode.SUB,
            '*=': OpCode.MUL,
            '/=': OpCode.SDIV,
        }
        return mapping.get(op, OpCode.ADD)
    
    def generate_if(self, stmt: IfExpr):
        """Generate IR for an if expression."""
        cond = self.generate_expr(stmt.condition)
        
        # Create blocks
        then_block = self.current_function.add_block('if.then')
        else_block = self.current_function.add_block('if.else')
        merge_block = self.current_function.add_block('if.end')
        
        # Conditional branch
        self.builder.cbr(cond, then_block, else_block)
        
        # Then block
        self.builder.set_block(then_block)
        self.generate_block(stmt.then_block)
        if not then_block.terminator:
            self.builder.br(merge_block)
        
        # Else block
        self.builder.set_block(else_block)
        if stmt.else_block:
            self.generate_block(stmt.else_block)
        elif stmt.else_if:
            self.generate_if(stmt.else_if[0])
        if not else_block.terminator:
            self.builder.br(merge_block)
        
        # Merge block
        self.builder.set_block(merge_block)
    
    def generate_match(self, stmt: MatchExpr):
        """Generate IR for a match expression."""
        value = self.generate_expr(stmt.value)
        
        # Create blocks for each arm
        arm_blocks = []
        for i, arm in enumerate(stmt.arms):
            arm_block = self.current_function.add_block(f'match.arm{i}')
            arm_blocks.append(arm_block)
        
        # Generate switch/if-else chain
        self.generate_match_value(value, stmt.arms, arm_blocks, 0)
        
        # Generate arm bodies
        prev_block = self.current_block
        for arm, block in zip(stmt.arms, arm_blocks):
            self.builder.set_block(block)
            result = self.generate_expr(arm.body)
            
            if not block.terminator:
                # Match is an expression, need to return the value
                # This is simplified - real implementation would use phi nodes
                pass
        
        self.current_block = prev_block
    
    def generate_match_value(self, value: Value, arms: List[MatchArm], 
                            blocks: List[BasicBlock], idx: int):
        """Recursively generate match arms."""
        if idx >= len(arms):
            return
        
        arm = arms[idx]
        pattern = arm.pattern
        
        # Simple pattern matching
        if pattern.kind == 'wildcard':
            self.builder.br(blocks[idx])
        elif pattern.kind == 'literal':
            # Compare with literal
            cmp_result = self.builder.icmp(IcmpKind.EQ, value, 
                                         ConstantInt(value=pattern.value))
            next_block = blocks[idx + 1] if idx + 1 < len(blocks) else blocks[-1]
            self.builder.cbr(cmp_result, blocks[idx], next_block)
        elif pattern.kind == 'bind':
            # Always matches, just binds the value
            self.builder.br(blocks[idx])
        else:
            self.builder.br(blocks[idx])
    
    def generate_loop(self, stmt: LoopExpr):
        """Generate IR for a loop expression."""
        loop_block = self.current_function.add_block('loop')
        body_block = self.current_function.add_block('loop.body')
        end_block = self.current_function.add_block('loop.end')
        
        self.break_targets.append(end_block)
        self.continue_targets.append(body_block)
        
        # Enter loop
        self.builder.br(loop_block)
        
        # Loop condition (always true)
        self.builder.set_block(loop_block)
        self.builder.br(body_block)
        
        # Loop body
        self.builder.set_block(body_block)
        self.generate_block(stmt.body)
        if not body_block.terminator:
            self.builder.br(loop_block)
        
        # End block
        self.builder.set_block(end_block)
        
        self.break_targets.pop()
        self.continue_targets.pop()
    
    def generate_while(self, stmt: WhileExpr):
        """Generate IR for a while loop."""
        cond_block = self.current_function.add_block('while.cond')
        body_block = self.current_function.add_block('while.body')
        end_block = self.current_function.add_block('while.end')
        
        self.break_targets.append(end_block)
        self.continue_targets.append(cond_block)
        
        # Enter condition
        self.builder.br(cond_block)
        
        # Condition check
        self.builder.set_block(cond_block)
        cond = self.generate_expr(stmt.condition)
        self.builder.cbr(cond, body_block, end_block)
        
        # Loop body
        self.builder.set_block(body_block)
        self.generate_block(stmt.body)
        if not body_block.terminator:
            self.builder.br(cond_block)
        
        # End block
        self.builder.set_block(end_block)
        
        self.break_targets.pop()
        self.continue_targets.pop()
    
    def generate_for(self, stmt: ForExpr):
        """Generate IR for a for loop."""
        iterable = self.generate_expr(stmt.iterable)
        
        # Simplified: iterate from 0 to length
        body_block = self.current_function.add_block('for.body')
        end_block = self.current_function.add_block('for.end')
        
        self.break_targets.append(end_block)
        self.continue_targets.append(body_block)
        
        # Create loop variable
        idx_alloca = self.builder.alloca(Type(TypeKind.INT), stmt.variable)
        self.builder.store(ConstantInt(value=0), idx_alloca)
        self.locals[stmt.variable] = idx_alloca
        
        # Simplified loop (just a single iteration for demo)
        self.builder.br(body_block)
        
        self.builder.set_block(body_block)
        
        idx = self.builder.load(idx_alloca, Type(TypeKind.INT))
        # Check bounds and body
        self.generate_block(stmt.body)
        
        # Increment and branch
        one = ConstantInt(value=1)
        next_idx = self.builder.add(idx, one, Type(TypeKind.INT))
        self.builder.store(next_idx, idx_alloca)
        
        if not body_block.terminator:
            self.builder.br(body_block)
        
        self.builder.set_block(end_block)
        
        self.break_targets.pop()
        self.continue_targets.pop()
    
    def generate_return(self, stmt: ReturnStmt):
        """Generate IR for a return statement."""
        if stmt.value:
            value = self.generate_expr(stmt.value)
            self.builder.ret(value)
        else:
            self.builder.ret_void()
    
    def generate_break(self, stmt: BreakStmt):
        """Generate IR for a break statement."""
        if self.break_targets:
            target = self.break_targets[-1]
            self.builder.br(target)
    
    def generate_continue(self, stmt: ContinueStmt):
        """Generate IR for a continue statement."""
        if self.continue_targets:
            target = self.continue_targets[-1]
            self.builder.br(target)
    
    def generate_expr(self, expr: Expr) -> Value:
        """Generate IR for an expression."""
        if isinstance(expr, LiteralExpr):
            return self.generate_literal(expr)
        elif isinstance(expr, IdentifierExpr):
            return self.generate_identifier(expr)
        elif isinstance(expr, UnaryExpr):
            return self.generate_unary(expr)
        elif isinstance(expr, BinaryExpr):
            return self.generate_binary(expr)
        elif isinstance(expr, CallExpr):
            return self.generate_call(expr)
        elif isinstance(expr, IfExpr):
            return self.generate_if_expr(expr)
        elif isinstance(expr, MatchExpr):
            return self.generate_match_expr(expr)
        elif isinstance(expr, Block):
            return self.generate_block_expr(expr)
        elif isinstance(expr, TupleExpr):
            return self.generate_tuple(expr)
        elif isinstance(expr, ArrayExpr):
            return self.generate_array(expr)
        elif isinstance(expr, FieldAccessExpr):
            return self.generate_field_access(expr)
        elif isinstance(expr, IndexExpr):
            return self.generate_index(expr)
        elif isinstance(expr, StructExpr):
            return self.generate_struct_expr(expr)
        elif isinstance(expr, RangeExpr):
            return self.generate_range(expr)
        elif isinstance(expr, SizeOfExpr):
            return self.generate_sizeof(expr)
        elif isinstance(expr, CastExpr):
            return self.generate_cast(expr)
        elif isinstance(expr, ReturnExpr):
            return self.generate_return_expr(expr)
        
        return ConstantInt(value=0)
    
    def generate_literal(self, expr: LiteralExpr) -> Value:
        """Generate IR for a literal."""
        if expr.token_type == 'int':
            return ConstantInt(value=expr.value, type=expr.type)
        elif expr.token_type == 'float':
            return ConstantFloat(value=expr.value, type=expr.type)
        elif expr.token_type == 'string':
            const = ConstantString(value=expr.value, type=expr.type)
            return const
        elif expr.token_type == 'bool':
            return ConstantInt(value=1 if expr.value else 0, type=Type(TypeKind.BOOL))
        elif expr.token_type == 'char':
            return ConstantInt(value=ord(expr.value), type=Type(TypeKind.CHAR))
        return ConstantInt(value=0)
    
    def generate_identifier(self, expr: IdentifierExpr) -> Value:
        """Generate IR for an identifier."""
        if expr.name in self.locals:
            alloca = self.locals[expr.name]
            return self.builder.load(alloca, expr.type)
        raise CodegenError(f"Undefined variable: {expr.name}")
    
    def generate_unary(self, expr: UnaryExpr) -> Value:
        """Generate IR for a unary expression."""
        operand = self.generate_expr(expr.operand)
        
        if expr.op == UnaryOp.NEG:
            if expr.operand.type.kind in (TypeKind.INT, TypeKind.UINT):
                zero = ConstantInt(value=0, type=expr.operand.type)
                return self.builder.sub(zero, operand, expr.type)
            else:
                return self.builder.binary_op(OpCode.FNEG, operand, operand, expr.type)
        
        elif expr.op == UnaryOp.NOT:
            one = ConstantInt(value=1)
            return self.builder.xor(operand, one, Type(TypeKind.INT, width=1))
        
        elif expr.op == UnaryOp.BITNOT:
            mask = ConstantInt(value=-1)
            return self.builder.xor(operand, mask, expr.type)
        
        elif expr.op == UnaryOp.REF:
            # Address of - already in memory
            if expr.operand.name in self.locals:
                return self.locals[expr.operand.name]
            return operand
        
        elif expr.op == UnaryOp.MUT_REF:
            if expr.operand.name in self.locals:
                return self.locals[expr.operand.name]
            return operand
        
        elif expr.op == UnaryOp.DEREF:
            return self.builder.load(operand, expr.type)
        
        return operand
    
    def generate_binary(self, expr: BinaryExpr) -> Value:
        """Generate IR for a binary expression."""
        left = self.generate_expr(expr.left)
        right = self.generate_expr(expr.right)
        
        if expr.op == BinaryOp.ADD:
            return self.builder.add(left, right, expr.type)
        elif expr.op == BinaryOp.SUB:
            return self.builder.sub(left, right, expr.type)
        elif expr.op == BinaryOp.MUL:
            return self.builder.mul(left, right, expr.type)
        elif expr.op == BinaryOp.DIV:
            return self.builder.sdiv(left, right, expr.type)
        elif expr.op == BinaryOp.REM:
            return self.builder.binary_op(OpCode.SREM, left, right, expr.type)
        elif expr.op == BinaryOp.AND:
            return self.builder.binary_op(OpCode.AND, left, right, expr.type)
        elif expr.op == BinaryOp.OR:
            return self.builder.binary_op(OpCode.OR, left, right, expr.type)
        elif expr.op == BinaryOp.XOR:
            return self.builder.binary_op(OpCode.XOR, left, right, expr.type)
        elif expr.op == BinaryOp.SHL:
            return self.builder.binary_op(OpCode.SHL, left, right, expr.type)
        elif expr.op == BinaryOp.SHR:
            return self.builder.binary_op(OpCode.LSHR, left, right, expr.type)
        elif expr.op == BinaryOp.EQ:
            return self.builder.icmp(IcmpKind.EQ, left, right)
        elif expr.op == BinaryOp.NE:
            return self.builder.icmp(IcmpKind.NE, left, right)
        elif expr.op == BinaryOp.LT:
            return self.builder.icmp(IcmpKind.SLT, left, right)
        elif expr.op == BinaryOp.GT:
            return self.builder.icmp(IcmpKind.SGT, left, right)
        elif expr.op == BinaryOp.LE:
            return self.builder.icmp(IcmpKind.SLE, left, right)
        elif expr.op == BinaryOp.GE:
            return self.builder.icmp(IcmpKind.SGE, left, right)
        
        return left
    
    def generate_call(self, expr: CallExpr) -> Value:
        """Generate IR for a function call."""
        func = self.generate_expr(expr.func)
        args = [self.generate_expr(arg) for arg in expr.args]
        
        return self.builder.call(func, args, expr.type)
    
    def generate_if_expr(self, expr: IfExpr) -> Value:
        """Generate IR for an if expression."""
        self.generate_if(expr)
        return ConstantInt(value=0)  # Simplified
    
    def generate_match_expr(self, expr: MatchExpr) -> Value:
        """Generate IR for a match expression."""
        self.generate_match(expr)
        return ConstantInt(value=0)  # Simplified
    
    def generate_block_expr(self, expr: Block) -> Value:
        """Generate IR for a block expression."""
        prev_locals = dict(self.locals)
        
        self.generate_block(expr)
        
        self.locals = prev_locals
        
        if expr.expr:
            return self.generate_expr(expr.expr)
        return ConstantInt(value=0)
    
    def generate_tuple(self, expr: TupleExpr) -> Value:
        """Generate IR for a tuple literal."""
        elements = [self.generate_expr(e) for e in expr.elements]
        # In real implementation, would allocate and store elements
        return elements[0] if elements else ConstantInt(value=0)
    
    def generate_array(self, expr: ArrayExpr) -> Value:
        """Generate IR for an array literal."""
        elements = [self.generate_expr(e) for e in expr.elements]
        # In real implementation, would allocate and store elements
        return elements[0] if elements else ConstantInt(value=0)
    
    def generate_field_access(self, expr: FieldAccessExpr) -> Value:
        """Generate IR for field access."""
        base = self.generate_expr(expr.base)
        
        if expr.is_method:
            # Return the method function
            return base
        
        # Get field index
        field_idx = 0
        if expr.base.type and expr.base.type.fields:
            for i, field_name in enumerate(expr.base.type.fields.keys()):
                if field_name == expr.field:
                    field_idx = i
                    break
        
        ptr = self.builder.getelementptr_struct(base, field_idx, expr.type)
        return self.builder.load(ptr, expr.type)
    
    def generate_index(self, expr: IndexExpr) -> Value:
        """Generate IR for index access."""
        base = self.generate_expr(expr.base)
        index = self.generate_expr(expr.index)
        
        ptr = self.builder.getelementptr_array(base, index, expr.type)
        return self.builder.load(ptr, expr.type)
    
    def generate_struct_expr(self, expr: StructExpr) -> Value:
        """Generate IR for a struct literal."""
        # Allocate struct
        alloca = self.builder.alloca(expr.type)
        
        # Initialize fields
        for field_name, field_expr in expr.fields.items():
            value = self.generate_expr(field_expr)
            # Get field index and store
            # Simplified
        
        return self.builder.load(alloca, expr.type)
    
    def generate_range(self, expr: RangeExpr) -> Value:
        """Generate IR for a range expression."""
        # Create range struct
        alloca = self.builder.alloca(Type(kind=TypeKind.STRUCT, name='Range'))
        return alloca
    
    def generate_sizeof(self, expr: SizeOfExpr) -> Value:
        """Generate IR for sizeof expression."""
        return ConstantInt(value=8, type=Type(TypeKind.USIZE))
    
    def generate_cast(self, expr: CastExpr) -> Value:
        """Generate IR for a type cast."""
        value = self.generate_expr(expr.value)
        
        if expr.value.type.kind in (TypeKind.INT, TypeKind.UINT) and \
           expr.target_type.kind in (TypeKind.INT, TypeKind.UINT):
            if expr.value.type.size < expr.target_type.size:
                return self.builder.sext(value, expr.target_type)
            else:
                return self.builder.trunc(value, expr.target_type)
        
        return value
    
    def generate_return_expr(self, expr: ReturnExpr) -> Value:
        """Generate IR for a return expression."""
        if expr.value:
            return self.generate_expr(expr.value)
        return ConstantInt(value=0)
    
    def generate_lvalue(self, expr: Expr) -> Value:
        """Generate IR for an lvalue (address of the value)."""
        if isinstance(expr, IdentifierExpr):
            if expr.name in self.locals:
                return self.locals[expr.name]
            raise CodegenError(f"Undefined variable: {expr.name}")
        elif isinstance(expr, FieldAccessExpr):
            base = self.generate_lvalue(expr.base)
            field_idx = 0
            return self.builder.getelementptr_struct(base, field_idx, expr.type)
        elif isinstance(expr, IndexExpr):
            base = self.generate_lvalue(expr.base)
            index = self.generate_expr(expr.index)
            return self.builder.getelementptr_array(base, index, expr.type)
        elif isinstance(expr, UnaryExpr) and expr.op == UnaryOp.DEREF:
            return self.generate_expr(expr.operand)
        
        raise CodegenError("Invalid lvalue")
    
    def unreachable(self):
        """Generate an unreachable instruction."""
        self.builder.emit(Instruction(opcode=OpCode.LANDINGPAD))
