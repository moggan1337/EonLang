"""
Trait system and generic constraints for EonLang.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from .ast import *


class TraitError(Exception):
    """Raised when trait resolution fails."""
    def __init__(self, message: str, span: Optional[Span] = None):
        self.message = message
        self.span = span
        super().__init__(f"Trait error: {message}")


@dataclass
class TraitConstraint:
    """A constraint that a type must implement a trait."""
    type_param: str
    trait_name: str
    trait_params: List[Type] = field(default_factory=list)


@dataclass
class ImplInstance:
    """An instance of a trait implementation."""
    trait_name: str
    type_name: str
    type_params: List[Type] = field(default_factory=list)
    impl: ImplStmt
    method_impls: Dict[str, FuncStmt] = field(default_factory=dict)


@dataclass
class TraitResolution:
    """Trait resolution context."""
    constraints: List[TraitConstraint] = field(default_factory=list)
    impls: List[ImplInstance] = field(default_factory=list)
    selected_impls: Dict[str, ImplInstance] = field(default_factory=dict)


class TraitResolver:
    """
    Trait resolver for EonLang.
    
    Handles:
    - Trait constraint solving
    - Method resolution
    - Trait bounds checking
    - Default method implementations
    """
    
    def __init__(self, type_inferrer):
        self.type_inferrer = type_inferrer
        self.traits: Dict[str, TraitStmt] = {}
        self.impls: List[ImplStmt] = []
        self.instances: List[ImplInstance] = []
        self.resolution_stack: List[str] = []  # For cycle detection
    
    def register_trait(self, trait: TraitStmt):
        """Register a trait declaration."""
        self.traits[trait.name] = trait
    
    def register_impl(self, impl: ImplStmt):
        """Register an impl block."""
        self.impls.append(impl)
        
        if impl.trait_name:
            instance = ImplInstance(
                trait_name=impl.trait_name,
                type_name=impl.type_name,
                impl=impl,
                method_impls={m.name: m for m in impl.methods}
            )
            self.instances.append(instance)
    
    def resolve_bounds(self, type_params: List[str], 
                     trait_bounds: List[TraitRef]) -> List[TraitConstraint]:
        """Resolve trait bounds for type parameters."""
        constraints = []
        
        for type_param in type_params:
            for bound in trait_bounds:
                if bound.name:
                    constraints.append(TraitConstraint(
                        type_param=type_param,
                        trait_name=bound.name,
                        trait_params=bound.type_params
                    ))
        
        return constraints
    
    def select_impl(self, trait_name: str, type_: Type) -> Optional[ImplInstance]:
        """Select an impl for a trait and type."""
        # Look for a matching impl
        for instance in self.instances:
            if instance.trait_name == trait_name:
                if instance.type_name == type_.name:
                    return instance
        
        # Look for a blanket impl
        for impl in self.impls:
            if impl.trait_name == trait_name:
                # Check if there's a blanket impl
                if impl.type_name == type_.name:
                    return ImplInstance(
                        trait_name=trait_name,
                        type_name=impl.type_name,
                        impl=impl
                    )
        
        return None
    
    def resolve_method(self, trait_name: str, method_name: str, 
                     type_: Type) -> Optional[FuncStmt]:
        """Resolve a method for a type implementing a trait."""
        # Check cycle
        key = f"{trait_name}::{method_name}"
        if key in self.resolution_stack:
            raise TraitError(f"Cycle in trait resolution: {key}")
        
        self.resolution_stack.append(key)
        
        try:
            # Look for impl method
            instance = self.select_impl(trait_name, type_)
            if instance and method_name in instance.method_impls:
                return instance.method_impls[method_name]
            
            # Look for default trait method
            if trait_name in self.traits:
                trait = self.traits[trait_name]
                for method in trait.methods:
                    if method.name == method_name:
                        return method
            
            return None
        
        finally:
            self.resolution_stack.pop()
    
    def check_trait_bounds(self, type_: Type, bounds: List[TraitRef]) -> bool:
        """Check if a type satisfies trait bounds."""
        for bound in bounds:
            impl = self.select_impl(bound.name, type_)
            if not impl:
                return False
        
        return True
    
    def unify_trait_bounds(self, bounds1: List[TraitRef], 
                          bounds2: List[TraitRef]) -> List[TraitRef]:
        """Unify two sets of trait bounds."""
        seen = set()
        result = []
        
        for bound in bounds1 + bounds2:
            key = (bound.name, tuple(str(t) for t in bound.type_params))
            if key not in seen:
                seen.add(key)
                result.append(bound)
        
        return result
    
    def merge_trait_bounds(self, bounds1: List[TraitRef], 
                          bounds2: List[TraitRef]) -> List[TraitRef]:
        """Merge two sets of trait bounds."""
        return self.unify_trait_bounds(bounds1, bounds2)
    
    def infer_trait_bounds(self, expr: Expr) -> List[TraitRef]:
        """Infer trait bounds from an expression."""
        bounds = []
        
        if isinstance(expr, BinaryExpr):
            bounds.extend(self.infer_trait_bounds(expr.left))
            bounds.extend(self.infer_trait_bounds(expr.right))
            
            # Arithmetic traits
            if expr.op in (BinaryOp.ADD, BinaryOp.SUB, BinaryOp.MUL, BinaryOp.DIV):
                bounds.append(TraitRef(name='Add'))
            elif expr.op in (BinaryOp.EQ, BinaryOp.NE):
                bounds.append(TraitRef(name='PartialEq'))
        
        elif isinstance(expr, CallExpr):
            # Look up the function's trait bounds
            if isinstance(expr.func, IdentifierExpr):
                func_name = expr.func.name
                if func_name in self.type_inferrer.functions:
                    func = self.type_inferrer.functions[func_name]
                    # Check trait bounds on parameters
                    pass
        
        return bounds
    
    def check_coherence(self) -> List[TraitError]:
        """Check for coherence violations (overlapping impls)."""
        errors = []
        
        # Check for overlapping impls
        for i, impl1 in enumerate(self.impls):
            for impl2 in self.impls[i+1:]:
                if self.impls_overlap(impl1, impl2):
                    errors.append(TraitError(
                        f"Overlapping impls for {impl1.type_name}"
                    ))
        
        return errors
    
    def impls_overlap(self, impl1: ImplStmt, impl2: ImplStmt) -> bool:
        """Check if two impls could overlap."""
        if impl1.type_name != impl2.type_name:
            return False
        
        # Check type parameters
        if len(impl1.type_params) != len(impl2.type_params):
            return True
        
        return True  # Simplified
    
    def validate_trait_hierarchy(self) -> List[TraitError]:
        """Validate trait hierarchy (no cycles, etc.)."""
        errors = []
        
        for trait_name, trait in self.traits.items():
            # Check for trait cycles
            if self.trait_has_cycle(trait_name, set()):
                errors.append(TraitError(f"Cycle in trait hierarchy: {trait_name}"))
        
        return errors
    
    def trait_has_cycle(self, trait_name: str, visited: Set[str]) -> bool:
        """Check if a trait has a cycle in its hierarchy."""
        if trait_name in visited:
            return True
        
        visited.add(trait_name)
        
        if trait_name in self.traits:
            trait = self.traits[trait_name]
            # Check supertraits
            for method in trait.methods:
                # Recursively check any trait bounds on methods
                pass
        
        return False


@dataclass
class TraitInfo:
    """Information about a trait."""
    name: str
    type_params: List[str]
    methods: Dict[str, 'MethodInfo'] = field(default_factory=dict)
    associated_types: Dict[str, Type] = field(default_factory=dict)
    supertraits: List[str] = field(default_factory=list)


@dataclass 
class MethodInfo:
    """Information about a trait method."""
    name: str
    params: List[Tuple[str, Type]]  # (name, type)
    return_type: Type
    body: Optional[Block] = None
    has_default: bool = False


class TraitChecker:
    """
    Type checker for trait-related code.
    """
    
    def __init__(self, trait_resolver: TraitResolver):
        self.resolver = trait_resolver
        self.type_inferrer = trait_resolver.type_inferrer
    
    def check_impl(self, impl: ImplStmt):
        """Check that an impl block is valid."""
        if impl.trait_name:
            # Verify trait exists
            if impl.trait_name not in self.resolver.traits:
                raise TraitError(f"Unknown trait: {impl.trait_name}")
            
            trait = self.resolver.traits[impl.trait_name]
            
            # Check that all trait methods are implemented
            for trait_method in trait.methods:
                found = any(m.name == trait_method.name for m in impl.methods)
                if not found and not self.has_default_impl(trait, trait_method):
                    raise TraitError(
                        f"Missing implementation for method: {trait_method.name}"
                    )
            
            # Check associated types
            for type_name, default_type in trait.associated_types.items():
                # Look for associated type definition in impl
                pass
        
        # Type check all methods
        for method in impl.methods:
            self.type_inferrer.infer_function(method)
    
    def has_default_impl(self, trait: TraitStmt, method: FuncStmt) -> bool:
        """Check if a trait method has a default implementation."""
        return method.body is not None
    
    def check_object_safety(self, trait: TraitStmt) -> List[str]:
        """Check if a trait is object-safe (can be used as trait objects)."""
        errors = []
        
        # Trait cannot have methods with generic parameters
        for method in trait.methods:
            if method.type_params:
                errors.append(f"Method {method.name} has generic parameters")
            
            # Cannot have methods that return Self
            if method.return_type.name == 'Self':
                errors.append(f"Method {method.name} returns Self")
        
        # Cannot have associated constants
        if trait.associated_types:
            errors.append("Trait has associated types")
        
        return errors
    
    def check_trait_bound_satisfaction(self, type_: Type, 
                                       bounds: List[TraitRef]) -> bool:
        """Check if a type satisfies trait bounds."""
        for bound in bounds:
            impl = self.resolver.select_impl(bound.name, type_)
            if not impl:
                return False
        
        return True


# Standard library traits
STANDARD_TRAITS = {
    'Debug': TraitInfo(
        name='Debug',
        type_params=[],
        methods={
            'debug_str': MethodInfo(
                name='debug_str',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(TypeKind.STRING),
                has_default=False
            )
        }
    ),
    'Display': TraitInfo(
        name='Display',
        type_params=[],
        methods={
            'display_str': MethodInfo(
                name='display_str',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(TypeKind.STRING),
                has_default=False
            )
        }
    ),
    'PartialEq': TraitInfo(
        name='PartialEq',
        type_params=['Self'],
        methods={
            'eq': MethodInfo(
                name='eq',
                params=[
                    ('self', Type(TypeKind.REFERENCE)),
                    ('other', Type(kind=TypeKind.GENERIC, name='Self'))
                ],
                return_type=Type(TypeKind.BOOL),
                has_default=False
            )
        }
    ),
    'Eq': TraitInfo(
        name='Eq',
        type_params=[],
        methods={},
        supertraits=['PartialEq']
    ),
    'PartialOrd': TraitInfo(
        name='PartialOrd',
        type_params=['Self'],
        methods={
            'cmp': MethodInfo(
                name='cmp',
                params=[
                    ('self', Type(TypeKind.REFERENCE)),
                    ('other', Type(kind=TypeKind.GENERIC, name='Self'))
                ],
                return_type=Type(TypeKind.INT),
                has_default=True
            )
        },
        supertraits=['PartialEq']
    ),
    'Ord': TraitInfo(
        name='Ord',
        type_params=[],
        methods={},
        supertraits=['PartialOrd']
    ),
    'Clone': TraitInfo(
        name='Clone',
        type_params=['Self'],
        methods={
            'clone': MethodInfo(
                name='clone',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(kind=TypeKind.GENERIC, name='Self'),
                has_default=False
            )
        }
    ),
    'Copy': TraitInfo(
        name='Copy',
        type_params=['Self'],
        methods={},
        supertraits=['Clone']
    ),
    'Drop': TraitInfo(
        name='Drop',
        type_params=[],
        methods={
            'drop': MethodInfo(
                name='drop',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(TypeKind.UNIT),
                has_default=False
            )
        }
    ),
    'Add': TraitInfo(
        name='Add',
        type_params=['Rhs'],
        methods={
            'add': MethodInfo(
                name='add',
                params=[
                    ('self', Type(TypeKind.REFERENCE)),
                    ('rhs', Type(kind=TypeKind.GENERIC, name='Rhs'))
                ],
                return_type=Type(kind=TypeKind.GENERIC, name='Output'),
                has_default=False
            )
        }
    ),
    'Iterator': TraitInfo(
        name='Iterator',
        type_params=['Item'],
        methods={
            'next': MethodInfo(
                name='next',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(kind=TypeKind.REFERENCE, 
                              generic_params=[Type(kind=TypeKind.GENERIC, name='Item')]),
                has_default=False
            )
        }
    ),
    'IntoIterator': TraitInfo(
        name='IntoIterator',
        type_params=['Item', 'IntoIter'],
        methods={
            'into_iter': MethodInfo(
                name='into_iter',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(kind=TypeKind.GENERIC, name='IntoIter'),
                has_default=False
            )
        }
    ),
    'From': TraitInfo(
        name='From',
        type_params=['T'],
        methods={
            'from': MethodInfo(
                name='from',
                params=[('t', Type(kind=TypeKind.GENERIC, name='T'))],
                return_type=Type(kind=TypeKind.GENERIC, name='Self'),
                has_default=False
            )
        }
    ),
    'TryFrom': TraitInfo(
        name='TryFrom',
        type_params=['T'],
        methods={
            'try_from': MethodInfo(
                name='try_from',
                params=[('t', Type(kind=TypeKind.GENERIC, name='T'))],
                return_type=Type(kind=TypeKind.GENERIC, name='Result'),
                has_default=False
            )
        }
    ),
    'AsRef': TraitInfo(
        name='AsRef',
        type_params=['T'],
        methods={
            'as_ref': MethodInfo(
                name='as_ref',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(kind=TypeKind.REFERENCE, 
                              generic_params=[Type(kind=TypeKind.GENERIC, name='T')]),
                has_default=False
            )
        }
    ),
    'AsMut': TraitInfo(
        name='AsMut',
        type_params=['T'],
        methods={
            'as_mut': MethodInfo(
                name='as_mut',
                params=[('self', Type(TypeKind.REFERENCE))],
                return_type=Type(kind=TypeKind.REFERENCE, 
                              generic_params=[Type(kind=TypeKind.GENERIC, name='T')]),
                has_default=False
            )
        }
    ),
    'Default': TraitInfo(
        name='Default',
        type_params=[],
        methods={
            'default': MethodInfo(
                name='default',
                params=[],
                return_type=Type(kind=TypeKind.GENERIC, name='Self'),
                has_default=True
            )
        }
    ),
}
