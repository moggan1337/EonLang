"""
Intermediate Representation (IR) for EonLang in SSA form.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Any
from enum import Enum, auto
from .ast import Type, TypeKind, BinaryOp, UnaryOp


class OpCode(Enum):
    """IR operation codes."""
    # Constants
    CONST_INT = auto()
    CONST_FLOAT = auto()
    CONST_STRING = auto()
    CONST_BOOL = auto()
    CONST_NULL = auto()
    CONST_ZEROINIT = auto()
    
    # Memory operations
    ALLOCA = auto()
    LOAD = auto()
    STORE = auto()
    GEP = auto()  # GetElementPtr
    PTRCAST = auto()
    BITCAST = auto()
    ZEXT = auto()
    SEXT = auto()
    TRUNC = auto()
    FPTRUNC = auto()
    FPEXT = auto()
    FPTOUI = auto()
    FPTOSI = auto()
    UITOFP = auto()
    SITOFP = auto()
    
    # Arithmetic
    ADD = auto()
    SUB = auto()
    MUL = auto()
    SDIV = auto()
    UDIV = auto()
    SREM = auto()
    UREM = auto()
    AND = auto()
    OR = auto()
    XOR = auto()
    SHL = auto()
    LSHR = auto()
    ASHR = auto()
    
    # Floating point
    FADD = auto()
    FSUB = auto()
    FMUL = auto()
    FDIV = auto()
    FREM = auto()
    FNeg = auto()
    
    # Comparison
    ICMP = auto()  # Integer compare
    FCMP = auto()  # Float compare
    
    # Control flow
    BR = auto()    # Unconditional branch
    CBR = auto()   # Conditional branch
    SWITCH = auto()
    RET = auto()
    RET_VOID = auto()
    
    # Function operations
    CALL = auto()
    INVOKE = auto()
    
    # PHI node
    PHI = auto()
    
    # Select
    SELECT = auto()
    
    # Aggregate operations
    INSERTVALUE = auto()
    EXTRACTVALUE = auto()
    EXTRACTELT = auto()
    INSERTELEMENT = auto()
    
    # Atomics
    FENCE = auto()
    ATOMICRMW = auto()
    ATOMICCMPXCHG = auto()
    
    # Variadic
    VAARG = auto()
    VASTART = auto()
    VAEND = auto()
    
    #landingpad
    LANDINGPAD = auto()
    RESUME = auto()


class IcmpKind(Enum):
    """Integer comparison kinds."""
    EQ = auto()
    NE = auto()
    UGT = auto()
    UGE = auto()
    ULT = auto()
    ULE = auto()
    SGT = auto()
    SGE = auto()
    SLT = auto()
    SLE = auto()


class FcmpKind(Enum):
    """Float comparison kinds."""
    FALSE = auto()
    OEQ = auto()  # Ordered equal
    OGT = auto()
    OGE = auto()
    OLT = auto()
    OLE = auto()
    ONE = auto()  # Ordered not equal
    ORD = auto()  # Ordered (no NaN)
    UNO = auto()  # Unordered (NaN possible)
    UEQ = auto()  # Unordered equal
    UGT = auto()
    UGE = auto()
    ULT = auto()
    ULE = auto()
    UNE = auto()  # Unordered not equal
    TRUE = auto()


@dataclass
class Value:
    """Base class for IR values."""
    name: str = ""
    type: Type = field(default_factory=lambda: Type(TypeKind.UNKNOWN))
    
    def __repr__(self):
        return self.name or f"%{id(self) & 0xFFFF:04d}"


@dataclass
class BasicBlock(Value):
    """A basic block in the IR."""
    instructions: List['Instruction'] = field(default_factory=list)
    predecessors: List['BasicBlock'] = field(default_factory=list)
    successors: List['BasicBlock'] = field(default_factory=list)
    is_entry: bool = False
    function: Optional['Function'] = None
    
    @property
    def terminator(self) -> Optional['Instruction']:
        """Get the terminator instruction."""
        if self.instructions and isinstance(self.instructions[-1].opcode, tuple):
            if self.instructions[-1].opcode[0] in (OpCode.BR, OpCode.CBR, OpCode.RET, OpCode.RET_VOID, OpCode.SWITCH):
                return self.instructions[-1]
        elif self.instructions:
            last = self.instructions[-1]
            if last.opcode in (OpCode.BR, OpCode.CBR, OpCode.RET, OpCode.RET_VOID, OpCode.SWITCH):
                return last
        return None


@dataclass 
class Function(Value):
    """An IR function."""
    name: str
    return_type: Type = field(default_factory=lambda: Type(TypeKind.UNIT))
    params: List[tuple] = field(default_factory=list)  # (name, type, is_mutable)
    basic_blocks: List[BasicBlock] = field(default_factory=list)
    entry_block: Optional[BasicBlock] = None
    type_params: List[str] = field(default_factory=list)
    is_extern: bool = False
    extern_name: Optional[str] = None
    variables: Dict[str, 'AllocInfo'] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def add_block(self, name: str = "") -> BasicBlock:
        """Add a basic block to this function."""
        block = BasicBlock(name=name, function=self)
        self.basic_blocks.append(block)
        return block


@dataclass
class GlobalVariable(Value):
    """A global variable."""
    name: str
    type: Type
    init: Optional['Constant'] = None
    is_constant: bool = False
    linkage: str = "private"  # private, internal, external, weak
    visibility: str = "default"


@dataclass
class GlobalValue(Value):
    """Base for global values."""
    pass


@dataclass
class Constant(Value):
    """A constant value."""
    value: Any = None
    type: Type = field(default_factory=lambda: Type(TypeKind.UNKNOWN))
    
    def __repr__(self):
        return str(self.value)


@dataclass
class ConstantInt(Constant):
    """Integer constant."""
    value: int = 0
    
    def __repr__(self):
        return str(self.value)


@dataclass
class ConstantFloat(Constant):
    """Float constant."""
    value: float = 0.0
    
    def __repr__(self):
        return str(self.value)


@dataclass
class ConstantString(Constant):
    """String constant."""
    value: str = ""
    
    def __repr__(self):
        return f'"{self.value}"'


@dataclass
class ConstantArray(Constant):
    """Array constant."""
    elements: List[Constant] = field(default_factory=list)


@dataclass
class ConstantStruct(Constant):
    """Struct constant."""
    fields: List[Constant] = field(default_factory=list)


@dataclass
class UndefValue(Value):
    """Undefined value."""
    pass


@dataclass
class Instruction(Value):
    """An IR instruction."""
    opcode: OpCode
    operands: List[Value] = field(default_factory=list)
    result_type: Type = field(default_factory=lambda: Type(TypeKind.UNKNOWN))
    name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For specific operations
    cmp_kind: Any = None  # IcmpKind or FcmpKind
    
    def __repr__(self):
        if self.opcode in (OpCode.RET, OpCode.RET_VOID, OpCode.BR, OpCode.CBR):
            return f"{self.opcode.name} {', '.join(str(o) for o in self.operands)}"
        
        result = f"%{self.name} = {self.opcode.name}"
        if self.cmp_kind:
            result += f" {self.cmp_kind.name}"
        if self.operands:
            result += f" {', '.join(str(o) for o in self.operands)}"
        return result


@dataclass
class AllocInfo:
    """Information about an allocated value."""
    alloca: Instruction
    is_mutable: bool
    lifetime: Optional[str] = None
    is_reference: bool = False


@dataclass
class Module:
    """An IR module containing functions and global variables."""
    name: str = "main"
    functions: Dict[str, Function] = field(default_factory=dict)
    global_vars: Dict[str, GlobalVariable] = field(default_factory=dict)
    types: Dict[str, Type] = field(default_factory=dict)
    strings: List[str] = field(default_factory=list)  # String constants
    
    def add_function(self, func: Function) -> Function:
        """Add a function to the module."""
        self.functions[func.name] = func
        return func
    
    def add_global(self, gv: GlobalVariable) -> GlobalVariable:
        """Add a global variable to the module."""
        self.global_vars[gv.name] = gv
        return gv


class IRBuilder:
    """
    Builder for constructing IR in SSA form.
    """
    
    def __init__(self, module: Module):
        self.module = module
        self.current_function: Optional[Function] = None
        self.current_block: Optional[BasicBlock] = None
        self.value_counter = 0
        self.block_counter = 0
        self named_values: Dict[str, Value] = {}
        self.phi_incoming: Dict[str, List[tuple]] = {}  # For PHI nodes
    
    def new_value(self) -> str:
        """Generate a new SSA value name."""
        name = f"%v{self.value_counter}"
        self.value_counter += 1
        return name
    
    def new_block(self, name: str = "") -> str:
        """Generate a new basic block name."""
        block_name = f"{name}.{self.block_counter}" if name else f"bb{self.block_counter}"
        self.block_counter += 1
        return block_name
    
    def set_block(self, block: BasicBlock):
        """Set the current block."""
        self.current_block = block
    
    def set_function(self, func: Function):
        """Set the current function."""
        self.current_function = func
        self.named_values.clear()
    
    def emit(self, inst: Instruction):
        """Emit an instruction to the current block."""
        if self.current_block:
            self.current_block.instructions.append(inst)
        return inst
    
    def alloca(self, type_: Type, name: str = "", is_mutable: bool = True) -> Instruction:
        """Create an alloca instruction."""
        inst = Instruction(
            opcode=OpCode.ALLOCA,
            result_type=type_,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def load(self, ptr: Value, type_: Type, name: str = "") -> Instruction:
        """Create a load instruction."""
        inst = Instruction(
            opcode=OpCode.LOAD,
            operands=[ptr],
            result_type=type_,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def store(self, value: Value, ptr: Value) -> Instruction:
        """Create a store instruction."""
        inst = Instruction(
            opcode=OpCode.STORE,
            operands=[value, ptr]
        )
        return self.emit(inst)
    
    def ret(self, value: Value) -> Instruction:
        """Create a return instruction."""
        inst = Instruction(
            opcode=OpCode.RET,
            operands=[value]
        )
        return self.emit(inst)
    
    def ret_void(self) -> Instruction:
        """Create a void return instruction."""
        inst = Instruction(opcode=OpCode.RET_VOID)
        return self.emit(inst)
    
    def br(self, block: BasicBlock) -> Instruction:
        """Create an unconditional branch."""
        inst = Instruction(
            opcode=OpCode.BR,
            operands=[block]
        )
        return self.emit(inst)
    
    def cbr(self, cond: Value, true_block: BasicBlock, false_block: BasicBlock) -> Instruction:
        """Create a conditional branch."""
        inst = Instruction(
            opcode=OpCode.CBR,
            operands=[cond, true_block, false_block]
        )
        return self.emit(inst)
    
    def binary_op(self, opcode: OpCode, left: Value, right: Value, type_: Type, name: str = "") -> Instruction:
        """Create a binary operation."""
        inst = Instruction(
            opcode=opcode,
            operands=[left, right],
            result_type=type_,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def add(self, left: Value, right: Value, type_: Type, name: str = "") -> Instruction:
        return self.binary_op(OpCode.ADD, left, right, type_, name)
    
    def sub(self, left: Value, right: Value, type_: Type, name: str = "") -> Instruction:
        return self.binary_op(OpCode.SUB, left, right, type_, name)
    
    def mul(self, left: Value, right: Value, type_: Type, name: str = "") -> Instruction:
        return self.binary_op(OpCode.MUL, left, right, type_, name)
    
    def sdiv(self, left: Value, right: Value, type_: Type, name: str = "") -> Instruction:
        return self.binary_op(OpCode.SDIV, left, right, type_, name)
    
    def icmp(self, kind: IcmpKind, left: Value, right: Value, name: str = "") -> Instruction:
        """Create an integer comparison."""
        inst = Instruction(
            opcode=OpCode.ICMP,
            operands=[left, right],
            cmp_kind=kind,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def fcmp(self, kind: FcmpKind, left: Value, right: Value, name: str = "") -> Instruction:
        """Create a float comparison."""
        inst = Instruction(
            opcode=OpCode.FCMP,
            operands=[left, right],
            cmp_kind=kind,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def call(self, func: Value, args: List[Value], type_: Type, name: str = "") -> Instruction:
        """Create a function call."""
        inst = Instruction(
            opcode=OpCode.CALL,
            operands=[func, *args],
            result_type=type_,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def phi(self, type_: Type, incoming: List[tuple], name: str = "") -> Instruction:
        """Create a PHI node."""
        inst = Instruction(
            opcode=OpCode.PHI,
            operands=[v for v, b in incoming],
            result_type=type_,
            name=name or self.new_value()
        )
        # Store incoming block info
        inst.metadata['incoming'] = incoming
        return self.emit(inst)
    
    def select(self, cond: Value, true_val: Value, false_val: Value, type_: Type, name: str = "") -> Instruction:
        """Create a select instruction."""
        inst = Instruction(
            opcode=OpCode.SELECT,
            operands=[cond, true_val, false_val],
            result_type=type_,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def gep(self, ptr: Value, indices: List[Value], type_: Type, name: str = "") -> Instruction:
        """Create a getelementptr instruction."""
        inst = Instruction(
            opcode=OpCode.GEP,
            operands=[ptr, *indices],
            result_type=type_,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def bitcast(self, value: Value, to_type: Type, name: str = "") -> Instruction:
        """Create a bitcast instruction."""
        inst = Instruction(
            opcode=OpCode.BITCAST,
            operands=[value],
            result_type=to_type,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def zext(self, value: Value, to_type: Type, name: str = "") -> Instruction:
        """Create a zero-extend instruction."""
        inst = Instruction(
            opcode=OpCode.ZEXT,
            operands=[value],
            result_type=to_type,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def sext(self, value: Value, to_type: Type, name: str = "") -> Instruction:
        """Create a sign-extend instruction."""
        inst = Instruction(
            opcode=OpCode.SEXT,
            operands=[value],
            result_type=to_type,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def trunc(self, value: Value, to_type: Type, name: str = "") -> Instruction:
        """Create a truncate instruction."""
        inst = Instruction(
            opcode=OpCode.TRUNC,
            operands=[value],
            result_type=to_type,
            name=name or self.new_value()
        )
        return self.emit(inst)
    
    def const_int(self, value: int, type_: Type, name: str = "") -> ConstantInt:
        """Create a constant integer."""
        return ConstantInt(value=value, type=type_)
    
    def const_float(self, value: float, type_: Type, name: str = "") -> ConstantFloat:
        """Create a constant float."""
        return ConstantFloat(value=value, type=type_)
    
    def const_string(self, value: str) -> ConstantString:
        """Create a constant string."""
        return ConstantString(value=value, type=Type(TypeKind.STRING))
    
    def getelementptr_struct(self, ptr: Value, field_idx: int, type_: Type, name: str = "") -> Instruction:
        """Create a GEP for struct field access."""
        zero = ConstantInt(value=0, type=Type(TypeKind.INT, name='i32'))
        idx = ConstantInt(value=field_idx, type=Type(TypeKind.INT, name='i32'))
        return self.gep(ptr, [zero, idx], type_, name)
    
    def getelementptr_array(self, ptr: Value, index: Value, type_: Type, name: str = "") -> Instruction:
        """Create a GEP for array element access."""
        zero = ConstantInt(value=0, type=Type(TypeKind.INT, name='i32'))
        return self.gep(ptr, [zero, index], type_, name)
