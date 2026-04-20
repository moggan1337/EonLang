# EonLang Examples

This directory contains example EonLang programs.

## Running Examples

```bash
# Compile and run hello world
python -m src.compiler examples/hello_world.eon -r

# Compile and run fibonacci
python -m src.compiler examples/fibonacci.eon -r

# Emit LLVM IR for ADT example
python -m src.compiler examples/adt_example.eon --emit-llvm
```

## Example Files

- `hello_world.eon` - Simple hello world program
- `fibonacci.eon` - Recursive fibonacci implementation
- `adt_example.eon` - Algebraic data types and pattern matching
- `traits_eon.eon` - Traits and interfaces
- `generics.eon` - Generic functions and data structures
- `lifetimes.eon` - Lifetime annotations and borrow checking
