"""
Pattern matching compilation for EonLang.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum, auto
from .ast import *


class PatternError(Exception):
    """Raised when pattern matching fails."""
    def __init__(self, message: str, span: Optional[Span] = None):
        self.message = message
        self.span = span
        super().__init__(f"Pattern error: {message}")


@dataclass
class PatternBinding:
    """A binding created by a pattern."""
    name: str
    type: Type
    span: Span


@dataclass
class PatternMatrix:
    """
    Pattern matrix for exhaustiveness checking.
    
    A pattern matrix is a list of rows, where each row is a list of
    column patterns, and the last column is the action (what to do if
    all patterns in the row match).
    """
    rows: List[List[Pattern]] = field(default_factory=list)
    actions: List[Any] = field(default_factory=list)
    
    def add_row(self, patterns: List[Pattern], action: Any):
        """Add a row to the matrix."""
        self.rows.append(patterns)
        self.actions.append(action)
    
    def is_empty(self) -> bool:
        """Check if the matrix is empty."""
        return len(self.rows) == 0


class PatternCompiler:
    """
    Compiles pattern matching to decision trees.
    
    Implements the algorithm from Maranget's "Compiling Patterns" paper:
    1. Build pattern matrix from match expression
    2. Compute usefulness of patterns
    3. Generate decision tree
    4. Emit IR for decision tree
    """
    
    def __init__(self, codegen):
        self.codegen = codegen
        self.type_inferrer = codegen.type_inferrer
        self.structs: Dict[str, StructStmt] = {}
        self.enums: Dict[str, EnumStmt] = {}
    
    def compile_match(self, match: MatchExpr) -> 'DecisionTree':
        """Compile a match expression to a decision tree."""
        # Build pattern matrix
        matrix = PatternMatrix()
        
        for arm in match.arms:
            patterns = self.expand_pattern(arm.pattern)
            matrix.add_row(patterns, arm)
        
        # Check exhaustiveness
        if not self.is_exhaustive(matrix):
            raise PatternError("Non-exhaustive match patterns", match.span)
        
        # Check for redundant patterns
        self.check_redundancy(matrix)
        
        # Build decision tree
        tree = self.build_tree(matrix, [])
        
        return tree
    
    def expand_pattern(self, pattern: Pattern) -> List[Pattern]:
        """Expand a pattern to column form."""
        if pattern.kind == 'wildcard':
            return []
        elif pattern.kind == 'bind':
            return [pattern]
        elif pattern.kind == 'literal':
            return [pattern]
        elif pattern.kind == 'tuple':
            result = []
            for p in pattern.subpatterns:
                result.extend(self.expand_pattern(p))
            return result
        elif pattern.kind == 'array':
            result = []
            for p in pattern.subpatterns:
                result.extend(self.expand_pattern(p))
            return result
        elif pattern.kind == 'struct':
            result = []
            for field_name, subpattern in pattern.subpatterns:
                result.extend(self.expand_pattern(subpattern))
            return result
        elif pattern.kind == 'variant':
            result = [pattern]  # Variant patterns consume one column
            for p in pattern.subpatterns:
                result.extend(self.expand_pattern(p))
            return result
        
        return [pattern]
    
    def is_exhaustive(self, matrix: PatternMatrix) -> bool:
        """Check if the pattern matrix is exhaustive."""
        if len(matrix.rows) == 0:
            return False
        
        # Get the number of columns
        num_cols = len(matrix.rows[0]) if matrix.rows else 0
        
        # For simple types, check if wildcard is present
        for row in matrix.rows:
            for pattern in row:
                if pattern.kind == 'wildcard':
                    return True
        
        # For enums, check all variants are covered
        if num_cols == 1:
            patterns = [row[0] for row in matrix.rows]
            # Check if we have a wildcard or all enum variants
            has_wildcard = any(p.kind == 'wildcard' for p in patterns)
            
            if has_wildcard:
                return True
            
            # Check if all enum variants are covered
            # This is simplified - real implementation would check
            # that all enum variants have a pattern
            return True
        
        return True
    
    def check_redundancy(self, matrix: PatternMatrix):
        """Check for redundant patterns."""
        seen = set()
        for row, action in zip(matrix.rows, matrix.actions):
            key = tuple(str(p.kind) + str(p.value) for p in row)
            if key in seen:
                raise PatternError(f"Redundant pattern: {key}")
            seen.add(key)
    
    def build_tree(self, matrix: PatternMatrix, bindings: List[PatternBinding]) -> 'DecisionTree':
        """Build a decision tree from a pattern matrix."""
        if matrix.is_empty():
            return DecisionTree(kind='fail')
        
        # Get number of columns
        num_cols = len(matrix.rows[0]) if matrix.rows else 0
        
        if num_cols == 0:
            # All columns matched, return the action
            return DecisionTree(kind='leaf', action=matrix.actions[0])
        
        # Get the first column's patterns
        first_col = [row[0] for row in matrix.rows]
        
        # Specialize on the pattern
        return self.specialize(matrix, bindings)
    
    def specialize(self, matrix: PatternMatrix, bindings: List[PatternBinding]) -> 'DecisionTree':
        """Specialize the matrix on the first column's patterns."""
        first_col_patterns = [row[0] for row in matrix.rows]
        
        # Group by pattern constructor
        groups: Dict[str, List[Tuple[List[Pattern], Any]]] = {}
        
        for i, pattern in enumerate(first_col_patterns):
            key = self.pattern_key(pattern)
            if key not in groups:
                groups[key] = []
            groups[key].append((matrix.rows[i][1:], matrix.actions[i]))
        
        # Build branches
        branches = []
        for key, rows in groups.items():
            new_matrix = PatternMatrix()
            for row, action in rows:
                new_matrix.add_row(row, action)
            
            pattern = first_col_patterns[list(groups.keys()).index(key)]
            subtree = self.build_tree(new_matrix, bindings)
            branches.append((pattern, subtree))
        
        return DecisionTree(kind='switch', branches=branches)
    
    def pattern_key(self, pattern: Pattern) -> str:
        """Get a string key for a pattern."""
        if pattern.kind == 'wildcard':
            return '_'
        elif pattern.kind == 'bind':
            return f'bind:{pattern.binding}'
        elif pattern.kind == 'literal':
            return f'lit:{pattern.value}'
        elif pattern.kind == 'tuple':
            return 'tuple'
        elif pattern.kind == 'array':
            return 'array'
        elif pattern.kind == 'struct':
            return f'struct:{pattern.value}'
        elif pattern.kind == 'variant':
            return f'variant:{pattern.value}'
        return 'unknown'
    
    def emit_tree(self, tree: 'DecisionTree'):
        """Emit IR for a decision tree."""
        if tree.kind == 'fail':
            raise PatternError("Match failure - non-exhaustive patterns")
        
        elif tree.kind == 'leaf':
            return self.emit_action(tree.action)
        
        elif tree.kind == 'switch':
            return self.emit_switch(tree)
        
        elif tree.kind == 'guard':
            return self.emit_guard(tree)
    
    def emit_switch(self, tree: 'DecisionTree'):
        """Emit IR for a switch node."""
        # This would generate if-else chains or switch statements
        pass
    
    def emit_action(self, action: MatchArm) -> Value:
        """Emit IR for a match arm action."""
        return self.codegen.generate_expr(action.body)
    
    def emit_guard(self, tree: 'DecisionTree') -> Value:
        """Emit IR for a guard node."""
        pass


@dataclass
class DecisionTree:
    """
    Decision tree for pattern matching.
    
    Types of nodes:
    - leaf: A pattern matched, execute the action
    - fail: No patterns matched (error)
    - switch: Switch on a constructor
    - guard: Check a guard condition
    """
    kind: str
    pattern: Optional[Pattern] = None
    action: Optional[Any] = None
    branches: List[Tuple[Pattern, 'DecisionTree']] = field(default_factory=list)
    guard: Optional[Expr] = None
    
    def is_leaf(self) -> bool:
        return self.kind == 'leaf'
    
    def is_fail(self) -> bool:
        return self.kind == 'fail'
    
    def is_switch(self) -> bool:
        return self.kind == 'switch'


class ExhaustiveChecker:
    """
    Checks pattern matching exhaustiveness.
    
    Uses the algorithm from:
    "Warnings for Pattern Matching" by Maranget
    """
    
    def __init__(self, compiler: PatternCompiler):
        self.compiler = compiler
        self.structs = compiler.structs
        self.enums = compiler.enums
    
    def check(self, match: MatchExpr) -> List[Pattern]:
        """Check exhaustiveness and return missing patterns."""
        matrix = self.build_matrix(match)
        
        # Use recursion to find uncovered patterns
        missing = self.find_missing(matrix, [])
        
        return missing
    
    def build_matrix(self, match: MatchExpr) -> PatternMatrix:
        """Build a pattern matrix from a match expression."""
        matrix = PatternMatrix()
        
        for arm in match.arms:
            patterns = self.expand_pattern(arm.pattern)
            matrix.add_row(patterns, arm)
        
        return matrix
    
    def expand_pattern(self, pattern: Pattern) -> List[Pattern]:
        """Expand a pattern for the matrix."""
        return self.compiler.expand_pattern(pattern)
    
    def find_missing(self, matrix: PatternMatrix, context: List[Pattern]) -> List[Pattern]:
        """Find patterns not covered by the matrix."""
        if matrix.is_empty():
            return [self.make_wildcard_pattern(context)]
        
        num_cols = len(matrix.rows[0]) if matrix.rows else 0
        
        if num_cols == 0:
            return []  # All rows matched
        
        # Get first column
        first_col = [row[0] for row in matrix.rows]
        
        # Find missing patterns for the first column
        missing_first = self.find_missing_first(first_col, context)
        
        # For each missing first pattern, check if it's covered by remaining rows
        result = []
        for missing in missing_first:
            remaining = self.specialize_matrix(matrix, missing)
            rest_missing = self.find_missing(remaining, context + [missing])
            
            if rest_missing:
                result.extend(rest_missing)
            else:
                result.append(missing)
        
        return result
    
    def find_missing_first(self, patterns: List[Pattern], context: List[Pattern]) -> List[Pattern]:
        """Find patterns not covered in the first column."""
        # This is a simplified version
        has_wildcard = any(p.kind == 'wildcard' for p in patterns)
        
        if has_wildcard:
            return []
        
        # Check if all enum variants are covered
        return []  # Simplified
    
    def specialize_matrix(self, matrix: PatternMatrix, pattern: Pattern) -> PatternMatrix:
        """Specialize the matrix for a given pattern."""
        new_matrix = PatternMatrix()
        
        for row, action in zip(matrix.rows, matrix.actions):
            if self.pattern_matches(row[0], pattern):
                new_matrix.add_row(row[1:], action)
        
        return new_matrix
    
    def pattern_matches(self, pattern: Pattern, against: Pattern) -> bool:
        """Check if a pattern matches another pattern."""
        if against.kind == 'wildcard':
            return True
        if pattern.kind == 'wildcard':
            return True
        if pattern.kind == 'bind':
            return True
        if pattern.kind == 'literal' and against.kind == 'literal':
            return pattern.value == against.value
        if pattern.kind == 'variant' and against.kind == 'variant':
            return pattern.value == against.value
        return False
    
    def make_wildcard_pattern(self, context: List[Pattern]) -> Pattern:
        """Make a wildcard pattern matching the context."""
        if context:
            return context[-1]
        return Pattern(kind='wildcard')
