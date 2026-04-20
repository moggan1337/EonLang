"""
LLVM IR generation for EonLang.
"""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from .ir import *
from .ast import *


@dataclass
class LLVMType:
    """LLVM type representation."""
    kind: str
    name: str = ""
    width: int = 0
    params: List['LLVMType'] = field(default_factory=list)
    element_type: Optional['LLVMType'] = None
    size: int = 0
    alignment: int = 1
    
    def __str__(self) -> str:
        if self.kind == 'void':
            return 'void'
        elif self.kind == 'int':
            return f'i{self.width}'
        elif self.kind == 'float':
            return 'float'
        elif self.kind == 'double':
            return 'double'
        elif self.kind == 'ptr':
            return f'{self.element_type}*'
        elif self.kind == 'array':
            return f'[{self.size} x {self.element_type}]'
        elif self.kind == 'struct':
            fields = ', '.join(str(f) for f in self.params)
            return f'<{{ {fields} }}>'
        elif self.kind == 'func':
            params = ', '.join(str(p) for p in self.params)
            return f'{self.params[-1]} ({params})*'
        elif self.kind == 'label':
            return 'label'
        elif self.kind == 'metadata':
            return 'metadata'
        elif self.kind == 'opaque':
            return f'%{self.name}'
        else:
            return self.kind


# Type mappings
PRIMITIVE_TYPES = {
    'i8': LLVMType(kind='int', width=8),
    'i16': LLVMType(kind='int', width=16),
    'i32': LLVMType(kind='int', width=32),
    'i64': LLVMType(kind='int', width=64),
    'i128': LLVMType(kind='int', width=128),
    'isize': LLVMType(kind='int', width=64),
    'u8': LLVMType(kind='int', width=8),
    'u16': LLVMType(kind='int', width=16),
    'u32': LLVMType(kind='int', width=32),
    'u64': LLVMType(kind='int', width=64),
    'u128': LLVMType(kind='int', width=128),
    'usize': LLVMType(kind='int', width=64),
    'f32': LLVMType(kind='float'),
    'f64': LLVMType(kind='double'),
    'bool': LLVMType(kind='int', width=1),
    'char': LLVMType(kind='int', width=32),
    'void': LLVMType(kind='void'),
    'unit': LLVMType(kind='void'),
    'never': LLVMType(kind='void'),
}


@dataclass
class LLVMBuilder:
    """
    Builder that generates LLVM IR from EonLang IR.
    """
    
    module: Module
    current_function: Optional[Function] = None
    current_block: Optional[BasicBlock] = None
    
    types: Dict[str, LLVMType] = field(default_factory=dict)
    values: Dict[str, str] = field(default_factory=dict)  # SSA name to LLVM name
    strings: List[str] = field(default_factory=list)
    
    value_counter: int = 0
    block_counter: int = 0
    string_counter: int = 0
    
    def __init__(self, module: Module):
        self.module = module
        self.types = PRIMITIVE_TYPES.copy()
        self._init_builtin_types()
    
    def _init_builtin_types(self):
        """Initialize built-in LLVM types."""
        # Initialize primitive types
        for name, llvm_type in PRIMITIVE_TYPES.items():
            self.types[name] = llvm_type
    
    def new_value(self) -> str:
        """Generate a new value name."""
        name = f"%{self.value_counter}"
        self.value_counter += 1
        return name
    
    def new_block_name(self, prefix: str = "") -> str:
        """Generate a new block name."""
        name = f"{prefix}.{self.block_counter}" if prefix else f"bb{self.block_counter}"
        self.block_counter += 1
        return name
    
    def get_llvm_type(self, type_: Type) -> LLVMType:
        """Convert an EonLang type to an LLVM type."""
        if type_.kind == TypeKind.INT:
            width = type_.size * 8 if type_.size else 32
            return LLVMType(kind='int', width=width)
        elif type_.kind == TypeKind.UINT:
            width = type_.size * 8 if type_.size else 32
            return LLVMType(kind='int', width=width)
        elif type_.kind == TypeKind.FLOAT:
            return LLVMType(kind='float')
        elif type_.kind == TypeKind.DOUBLE:
            return LLVMType(kind='double')
        elif type_.kind == TypeKind.BOOL:
            return LLVMType(kind='int', width=1)
        elif type_.kind == TypeKind.CHAR:
            return LLVMType(kind='int', width=32)
        elif type_.kind == TypeKind.UNIT or type_.kind == TypeKind.NEVER:
            return LLVMType(kind='void')
        elif type_.kind == TypeKind.STRING:
            return LLVMType(kind='ptr', element_type=LLVMType(kind='int', width=8))
        elif type_.kind == TypeKind.REFERENCE:
            pointee = self.get_llvm_type(type_.generic_params[0])
            return LLVMType(kind='ptr', element_type=pointee)
        elif type_.kind == TypeKind.POINTER:
            pointee = self.get_llvm_type(type_.generic_params[0])
            return LLVMType(kind='ptr', element_type=pointee)
        elif type_.kind == TypeKind.ARRAY:
            elem = self.get_llvm_type(type_.generic_params[0])
            size_str = type_.fields.get('size', '?')
            if isinstance(size_str, int):
                return LLVMType(kind='array', element_type=elem, size=size_str)
            return LLVMType(kind='ptr', element_type=elem)
        elif type_.kind == TypeKind.TUPLE:
            fields = [self.get_llvm_type(t) for t in type_.generic_params]
            return LLVMType(kind='struct', params=fields)
        elif type_.kind == TypeKind.FUNCTION:
            param_types = [self.get_llvm_type(t) for t in type_.generic_params[:-1]]
            ret_type = self.get_llvm_type(type_.generic_params[-1]) if type_.generic_params else LLVMType(kind='void')
            return LLVMType(kind='func', params=[*param_types, ret_type])
        elif type_.kind == TypeKind.STRUCT:
            if type_.name in self.types:
                return self.types[type_.name]
            fields = [self.get_llvm_type(t) for t in type_.fields.values()]
            return LLVMType(kind='struct', name=type_.name, params=fields)
        elif type_.kind == TypeKind.ENUM:
            # Represent enums as structs with a tag
            return LLVMType(kind='struct', name=type_.name)
        elif type_.kind == TypeKind.GENERIC:
            # Resolve generic type
            if type_.name in ('Option', 'Some', 'None'):
                if type_.generic_params:
                    return self.get_llvm_type(type_.generic_params[0])
            return LLVMType(kind='ptr', element_type=LLVMType(kind='int', width=8))
        elif type_.kind == TypeKind.TYPE_VAR:
            return LLVMType(kind='ptr', element_type=LLVMType(kind='int', width=8))
        else:
            return LLVMType(kind='int', width=64)
    
    def emit_module(self) -> str:
        """Emit the complete LLVM module."""
        output = []
        
        # Target declaration
        output.append('; Module target')
        output.append(f'target datalayout = "e-m:e-i64:64-f80:128-n8:16:32:64-S128"')
        output.append('target triple = "x86_64-unknown-linux-gnu"')
        output.append('')
        
        # Type declarations
        output.append('; Type declarations')
        for name, llvm_type in sorted(self.types.items()):
            if llvm_type.kind == 'struct' and llvm_type.name:
                output.append(f'%{name} = type {{ {", ".join(str(f) for f in llvm_type.params)} }}')
        
        # String constants
        for i, s in enumerate(self.strings):
            escaped = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\0A').replace('\t', '\\09')
            output.append(f'@.str.{i} = private constant [{len(s)+1} x i8] c"{escaped}\\00"')
        output.append('')
        
        # Global variables
        output.append('; Global variables')
        for name, gv in self.module.global_vars.items():
            llvm_type = self.get_llvm_type(gv.type)
            linkage = 'external' if gv.linkage == 'external' else 'private'
            const = 'constant' if gv.is_constant else 'global'
            if gv.init:
                output.append(f'@{name} = {linkage} {const} {llvm_type} {self.emit_constant(gv.init)}')
            else:
                output.append(f'@{name} = {linkage} {const} {llvm_type} zeroinitializer')
        output.append('')
        
        # Function declarations
        output.append('; Function declarations')
        for name, func in self.module.functions.items():
            if func.is_extern:
                output.append(self.emit_function_decl(func))
        
        output.append('')
        
        # Function definitions
        output.append('; Function definitions')
        for name, func in self.module.functions.items():
            if not func.is_extern:
                output.append(self.emit_function(func))
        
        return '\n'.join(output)
    
    def emit_function_decl(self, func: Function) -> str:
        """Emit a function declaration."""
        param_types = []
        for name, type_, is_mut in func.params:
            llvm_type = self.get_llvm_type(type_)
            param_types.append(llvm_type)
        
        ret_type = self.get_llvm_type(func.return_type)
        
        params = ', '.join(str(t) for t in param_types)
        return f'declare {ret_type} @{func.extern_name or func.name}({params})'
    
    def emit_function(self, func: Function) -> str:
        """Emit a function definition."""
        self.current_function = func
        
        param_types = []
        for name, type_, is_mut in func.params:
            llvm_type = self.get_llvm_type(type_)
            param_types.append(llvm_type)
        
        ret_type = self.get_llvm_type(func.return_type)
        
        params = []
        for i, (name, type_, is_mut) in enumerate(func.params):
            llvm_type = self.get_llvm_type(type_)
            params.append(f'{llvm_type} %arg{i}')
            self.values[name] = f'%arg{i}'
        
        params_str = ', '.join(params)
        output = [f'define {ret_type} @{func.name}({params_str}) {{']
        
        # Create entry block
        entry = func.add_block('entry')
        entry.is_entry = True
        self.emit_basic_block(entry)
        
        for block in func.basic_blocks:
            output.append(f'{block.name}:')
            for inst in block.instructions:
                output.append(f'  {self.emit_instruction(inst)}')
        
        output.append('}')
        
        self.current_function = None
        return '\n'.join(output)
    
    def emit_basic_block(self, block: BasicBlock):
        """Emit a basic block."""
        self.current_block = block
        
        for inst in block.instructions:
            self.emit_instruction(inst)
    
    def emit_instruction(self, inst: Instruction) -> str:
        """Emit a single instruction."""
        opcode = inst.opcode
        
        if opcode == OpCode.ALLOCA:
            llvm_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = alloca {llvm_type}'
        
        elif opcode == OpCode.LOAD:
            ptr = self.get_value_name(inst.operands[0])
            llvm_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = load {llvm_type}, {llvm_type}* {ptr}'
        
        elif opcode == OpCode.STORE:
            val = self.get_value_name(inst.operands[0])
            ptr = self.get_value_name(inst.operands[1])
            val_type = self.get_llvm_type(inst.operands[0].type) if hasattr(inst.operands[0], 'type') else 'i64'
            return f'store {val_type} {val}, {val_type}* {ptr}'
        
        elif opcode == OpCode.RET:
            val = self.get_value_name(inst.operands[0])
            val_type = self.get_llvm_type(inst.operands[0].type) if hasattr(inst.operands[0], 'type') else 'i64'
            return f'ret {val_type} {val}'
        
        elif opcode == OpCode.RET_VOID:
            return 'ret void'
        
        elif opcode == OpCode.BR:
            target = inst.operands[0]
            return f'br label %{target.name}'
        
        elif opcode == OpCode.CBR:
            cond = self.get_value_name(inst.operands[0])
            true_block = inst.operands[1].name
            false_block = inst.operands[2].name
            return f'br i1 {cond}, label %{true_block}, label %{false_block}'
        
        elif opcode == OpCode.ADD:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = add {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.SUB:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = sub {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.MUL:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = mul {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.SDIV:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = sdiv {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.AND:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = and {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.OR:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = or {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.XOR:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = xor {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.SHL:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = shl {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.LSHR:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = lshr {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.ASHR:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = ashr {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.ICMP:
            kind = inst.cmp_kind.name.lower()
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = icmp {kind} {inst.operands[0].type} {left}, {right}'
        
        elif opcode == OpCode.FCMP:
            kind = inst.cmp_kind.name.lower()
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = fcmp {kind} {inst.operands[0].type} {left}, {right}'
        
        elif opcode == OpCode.SELECT:
            cond = self.get_value_name(inst.operands[0])
            true_val = self.get_value_name(inst.operands[1])
            false_val = self.get_value_name(inst.operands[2])
            result_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = select i1 {cond}, {result_type} {true_val}, {result_type} {false_val}'
        
        elif opcode == OpCode.CALL:
            func = inst.operands[0]
            args = [self.get_value_name(a) for a in inst.operands[1:]]
            func_type = self.get_llvm_type(func.type) if hasattr(func, 'type') else LLVMType(kind='func')
            result_type = self.get_llvm_type(inst.result_type)
            args_str = ', '.join(args)
            
            if inst.name:
                return f'{inst.name} = call {result_type} @{func.name}({args_str})'
            else:
                return f'call {result_type} @{func.name}({args_str})'
        
        elif opcode == OpCode.PHI:
            result_type = self.get_llvm_type(inst.result_type)
            pairs = []
            for val, block in inst.metadata.get('incoming', []):
                val_name = self.get_value_name(val)
                pairs.append(f'[{val_name}, %{block.name}]')
            pairs_str = ', '.join(pairs)
            return f'{inst.name} = phi {result_type} {pairs_str}'
        
        elif opcode == OpCode.GEP:
            ptr = self.get_value_name(inst.operands[0])
            indices = [self.get_value_name(i) for i in inst.operands[1:]]
            result_type = self.get_llvm_type(inst.result_type)
            indices_str = ', '.join(indices)
            return f'{inst.name} = getelementptr {inst.operands[0].type}, {ptr.type}* {ptr}, i64 0, i32 {indices_str}'
        
        elif opcode == OpCode.BITCAST:
            val = self.get_value_name(inst.operands[0])
            from_type = self.get_llvm_type(inst.operands[0].type)
            to_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = bitcast {from_type} {val} to {to_type}'
        
        elif opcode == OpCode.ZEXT:
            val = self.get_value_name(inst.operands[0])
            from_type = self.get_llvm_type(inst.operands[0].type)
            to_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = zext {from_type} {val} to {to_type}'
        
        elif opcode == OpCode.SEXT:
            val = self.get_value_name(inst.operands[0])
            from_type = self.get_llvm_type(inst.operands[0].type)
            to_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = sext {from_type} {val} to {to_type}'
        
        elif opcode == OpCode.TRUNC:
            val = self.get_value_name(inst.operands[0])
            from_type = self.get_llvm_type(inst.operands[0].type)
            to_type = self.get_llvm_type(inst.result_type)
            return f'{inst.name} = trunc {from_type} {val} to {to_type}'
        
        elif opcode == OpCode.FADD:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = fadd {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.FSUB:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = fsub {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.FMUL:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = fmul {inst.result_type} {left}, {right}'
        
        elif opcode == OpCode.FDIV:
            left = self.get_value_name(inst.operands[0])
            right = self.get_value_name(inst.operands[1])
            return f'{inst.name} = fdiv {inst.result_type} {left}, {right}'
        
        return f'; Unknown opcode: {opcode}'
    
    def get_value_name(self, value: Value) -> str:
        """Get the LLVM name for a value."""
        if isinstance(value, Constant):
            return self.emit_constant(value)
        elif isinstance(value, BasicBlock):
            return value.name
        elif value.name:
            return value.name
        else:
            return f'%{id(value) & 0xFFFF:04d}'
    
    def emit_constant(self, const: Constant) -> str:
        """Emit a constant value."""
        if isinstance(const, ConstantInt):
            return str(const.value)
        elif isinstance(const, ConstantFloat):
            return str(const.value)
        elif isinstance(const, ConstantString):
            idx = len(self.strings)
            self.strings.append(const.value)
            return f'@.str.{idx}'
        elif isinstance(const, ConstantArray):
            elements = ', '.join(self.emit_constant(e) for e in const.elements)
            elem_type = self.get_llvm_type(const.elements[0].type) if const.elements else LLVMType(kind='int')
            return f'[{len(const.elements)} x {elem_type}] [{elements}]'
        elif isinstance(const, ConstantStruct):
            fields = ', '.join(self.emit_constant(f) for f in const.fields)
            return f'{{{fields}}}'
        return '0'
