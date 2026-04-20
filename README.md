# EonLang

**EonLang** is a modern, compiled programming language with a focus on safety,
performance, and expressive power. It features a powerful type system with
Hindley-Milner type inference, algebraic data types, traits/interfaces,
pattern matching, and a robust borrow checker for memory safety.

## Table of Contents

1. [Overview](#overview)
2. [Language Design](#language-design)
3. [Building from Source](#building-from-source)
4. [Compiler Architecture](#compiler-architecture)
5. [Intermediate Representation (IR)](#intermediate-representation-ir)
6. [Backend and Code Generation](#backend-and-code-generation)
7. [Type System](#type-system)
8. [Memory Safety](#memory-safety)
9. [Pattern Matching](#pattern-matching)
10. [Traits and Generics](#traits-and-generics)
11. [Examples](#examples)
12. [Roadmap](#roadmap)
13. [Contributing](#contributing)
14. [License](#license)

---

## Overview

EonLang is a systems programming language that combines the best features from
modern languages like Rust, Haskell, and OCaml. It is designed to be:

- **Safe**: Memory safety through ownership and borrowing
- **Expressive**: Pattern matching, algebraic data types, and powerful generics
- **Performant**: Compiles to native code via LLVM
- **Pragmatic**: Type inference reduces verbosity while maintaining clarity

### Key Features

- **Hindley-Milner Type Inference**: Write less code without sacrificing type safety
- **Algebraic Data Types**: Sum types, product types, and tuples
- **Pattern Matching**: Exhaustive pattern matching with guards
- **Traits/Interfaces**: Ad-hoc polymorphism with trait bounds
- **Borrow Checker**: Compile-time memory safety without garbage collection
- **LLVM Backend**: State-of-the-art optimization and code generation
- **Generics**: Parametric polymorphism with const generics
- **Lifetime Analysis**: Compile-time tracking of reference validity

---

## Language Design

### Syntax Overview

EonLang's syntax is clean and expressive, drawing from the best practices
established by languages like Rust, Swift, and Kotlin.

```eon
// Functions
fn add(a: i32, b: i32) -> i32 {
    return a + b;
}

// Type inference
fn inferred(x: i32) {
    let y = x + 1;  // Type of y is inferred as i32
    let name = "EonLang";  // Type of name is inferred as str
}

// Mutability
fn mutability() {
    let mut counter = 0;
    counter = counter + 1;  // OK - counter is mutable
}

// Control flow
fn control_flow(x: i32) -> str {
    if x > 0 {
        return "positive";
    } else if x < 0 {
        return "negative";
    } else {
        return "zero";
    }
}

// Loops
fn loops() {
    // Infinite loop
    loop {
        if should_exit() {
            break;
        }
    }
    
    // While loop
    while condition {
        do_work();
    }
    
    // For loop with range
    for i in 0..10 {
        process(i);
    }
}
```

### Data Types

```eon
// Primitive types
let int_val: i32 = 42;
let float_val: f64 = 3.14;
let bool_val: bool = true;
let char_val: char = 'A';
let str_val: str = "Hello, World!";

// Arrays
let arr: [i32; 5] = [1, 2, 3, 4, 5];

// Tuples
let tuple: (i32, str, bool) = (42, "hello", true);
let (a, b, c) = tuple;  // Destructuring

// Structs
struct Point {
    x: f64,
    y: f64
}

let point = Point { x: 1.0, y: 2.0 };

// Enums
enum Shape {
    Circle(f64),           // With radius
    Rectangle(f64, f64),   // Width, height
    Square(f64)             // Side
}

let circle = Shape.Circle(5.0);
```

### Functions

```eon
// Basic function
fn greet(name: str) -> str {
    return "Hello, " + name + "!";
}

// Generic function
fn identity<T>(x: T) -> T {
    return x;
}

// Multiple return values
fn divide(a: f64, b: f64) -> (f64, f64) {
    let quotient = a / b;
    let remainder = a % b;
    return (quotient, remainder);
}

// Closures
fn use_closure() {
    let add = |x: i32, y: i32| -> i32 { x + y };
    let result = add(3, 4);  // result = 7
    
    // Closure with captured environment
    let factor = 10;
    let multiply = |x: i32| -> i32 { x * factor };
}
```

### Pattern Matching

```eon
fn describe(shape: Shape) -> str {
    match shape {
        Shape.Circle(r) => "Circle with radius " + r.to_string(),
        Shape.Rectangle(w, h) => "Rectangle " + w + "x" + h,
        Shape.Square(s) => "Square with side " + s
    }
}

// Pattern matching with guards
fn classify(n: i32) -> str {
    match n {
        x if x < 0 => "negative",
        0 => "zero",
        x if x % 2 == 0 => "even positive",
        _ => "odd positive"
    }
}

// Destructuring
fn process_tuple(t: (i32, str, bool)) {
    let (num, text, flag) = t;
    match text {
        "hello" if flag => println("Greeting!"),
        _ => println("Other")
    }
}
```

---

## Building from Source

### Prerequisites

- Python 3.10 or later
- LLVM/Clang (optional, for native code generation)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/moggan1337/EonLang.git
cd EonLang

# Install dependencies (if using pip)
pip install -e .

# Or run directly
python -m src.compiler --help
```

### Running the Compiler

```bash
# Compile a file
python -m src.compiler examples/hello_world.eon -o hello

# Emit LLVM IR
python -m src.compiler examples/fibonacci.eon --emit-llvm

# Print AST
python -m src.compiler examples/fibonacci.eon --print-ast

# Print tokens
python -m src.compiler examples/fibonacci.eon --print-tokens

# Run after compilation
python -m src.compiler examples/hello_world.eon -r
```

### Command Line Options

```
usage: compiler.py [-h] [-o OUTPUT] [-O OPTIMIZE] [-g] [-S] [--ir] [-r]
                   [--print-ast] [--print-tokens] [--print-types] [-Werror]

EonLang Compiler

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output file
  -O OPTIMIZE, --optimize OPTIMIZE
                        Optimization level (0-3)
  -g, --debug           Generate debug info
  -S, --emit-llvm       Emit LLVM IR
  --ir                  Emit internal IR
  -r, --run             Run after compilation
  --print-ast           Print AST
  --print-tokens        Print tokens
  --print-types         Print inferred types
  -Werror               Treat warnings as errors
```

---

## Compiler Architecture

The EonLang compiler follows a traditional multi-phase design:

```
Source Code
    │
    ▼
┌─────────────────┐
│     Lexer       │  Tokenize source into tokens
└─────────────────┘
    │
    ▼
┌─────────────────┐
│     Parser      │  Build AST from tokens
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Type Inference  │  Hindley-Milner type checking
│  (Algorithm W)  │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Borrow Checker  │  Memory safety verification
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Pattern Match  │  Compile patterns to decision trees
│   Compiler      │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│     IR Gen      │  Generate SSA IR
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   LLVM Gen      │  Generate LLVM IR
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ LLVM/Backend    │  Compile to machine code
└─────────────────┘
    │
    ▼
Machine Code
```

### Phase 1: Lexical Analysis

The lexer tokenizes the source code, handling:
- Keywords and identifiers
- Integer, float, and string literals
- Operators and punctuation
- Comments (single-line and multi-line)
- Unicode support

```python
# Example: Token sequence for "let x = 42;"
[
    Token(LET, 'let', 1, 1),
    Token(IDENTIFIER, 'x', 1, 5),
    Token(ASSIGN, '=', 1, 7),
    Token(INTEGER, '42', 1, 9),
    Token(SEMICOLON, ';', 1, 11),
    Token(EOF, '', 1, 12)
]
```

### Phase 2: Parsing

The recursive-descent parser builds an Abstract Syntax Tree (AST) from the
token stream. It handles:
- Function definitions
- Struct and enum declarations
- Trait and impl blocks
- Expressions (binary, unary, call, etc.)
- Control flow structures

The parser uses operator precedence parsing for expressions and builds
the tree in a way that preserves source location information for
error reporting.

### Phase 3: Type Inference

EonLang uses Algorithm W, the classic Hindley-Milner type inference algorithm,
augmented with support for:
- Subtyping
- Lifetime annotations
- Trait constraints
- Record types

```python
# Example type inference
fn infer_expr(expr: Expr, env: Dict[str, Type]) -> Type:
    if isinstance(expr, BinaryExpr):
        left_type = infer_expr(expr.left, env)
        right_type = infer_expr(expr.right, env)
        unify(left_type, right_type)
        return left_type
```

### Phase 4: Borrow Checking

The borrow checker implements Rust-style ownership and borrowing:
- Each value has exactly one owner
- Values can be borrowed (shared or mutable)
- Mutable borrows are exclusive
- Borrows cannot outlive the borrowed value

### Phase 5: Pattern Compilation

Patterns are compiled to efficient decision trees using the algorithm
from Maranget's "Compiling Patterns" paper:
- Build pattern matrix from match expression
- Check exhaustiveness
- Generate decision tree
- Emit IR for efficient matching

### Phase 6-8: IR and Code Generation

The compiler generates LLVM IR in SSA form, leveraging LLVM's optimization
pipeline for efficient native code generation.

---

## Intermediate Representation (IR)

EonLang uses a custom SSA-based IR before generating LLVM IR. This IR is
designed to be:
- Simple to generate from the AST
- Easy to optimize
- Straightforward to translate to LLVM IR

### IR Instructions

```python
# Core IR instructions
class OpCode(Enum):
    # Memory operations
    ALLOCA = auto()      # Allocate on stack
    LOAD = auto()        # Load from memory
    STORE = auto()       # Store to memory
    GEP = auto()         # Get element pointer
    
    # Arithmetic
    ADD = auto()         # Integer addition
    SUB = auto()         # Integer subtraction
    MUL = auto()         # Integer multiplication
    SDIV = auto()        # Signed division
    FADD = auto()        # Float addition
    
    # Control flow
    BR = auto()          # Unconditional branch
    CBR = auto()         # Conditional branch
    RET = auto()         # Return
    
    # Function calls
    CALL = auto()        # Call function
    
    # PHI node for SSA
    PHI = auto()          # Phi function
```

### SSA Form

The IR uses Static Single Assignment form, where each variable is assigned
exactly once. This simplifies optimization and code generation.

```llvm
; Example IR in text form
define i32 @add(i32 %a, i32 %b) {
entry:
  %0 = alloca i32
  store i32 %a, i32* %0
  %1 = load i32, i32* %0
  %2 = add i32 %1, %b
  ret i32 %2
}
```

### Control Flow Graph

Functions are represented as control flow graphs (CFGs) with basic blocks:

```
        ┌─────────┐
        │  entry  │
        └────┬────┘
             │
        ┌────▼────┐
        │cond br  │
        └────┬────┘
       ┌────┴────┐
       │         │
   ┌───▼───┐ ┌───▼───┐
   │true br│ │false br│
   └───┬───┘ └───┬───┘
       │         │
   ┌───▼───┐ ┌───▼───┐
   │then blk│ │else blk│
   └───┬───┘ └───┬───┘
       │         │
       └────┬────┘
            │
       ┌────▼────┐
       │merge blk│
       └─────────┘
```

---

## Backend and Code Generation

### LLVM Integration

EonLang generates LLVM IR and leverages LLVM for:
- Target-independent optimizations
- Instruction selection
- Register allocation
- Code emission

### Type Mapping

EonLang types are mapped to LLVM types:

| EonLang Type | LLVM Type |
|--------------|-----------|
| i8           | i8        |
| i32          | i32       |
| i64          | i64       |
| f32          | float     |
| f64          | double    |
| bool         | i1        |
| char         | i32       |
| str          | i8*       |
| T*           | T*        |
| &T           | T*        |
| [N x T]      | [N x T]   |
| {A, B}       | {A, B}    |

### Code Generation Pipeline

```python
# Simplified code generation
def generate_function(func: FuncStmt) -> Function:
    ir_func = Function(name=func.name)
    
    # Create entry block
    entry = ir_func.add_block('entry')
    set_block(entry)
    
    # Allocate parameters
    for name, type_ in func.params:
        alloca = alloca(type_, name)
        store(param, alloca)
        locals[name] = alloca
    
    # Generate body
    generate_block(func.body)
    
    return ir_func
```

### Optimization Levels

The compiler supports multiple optimization levels:

- **O0**: No optimization (fastest compile)
- **O1**: Basic optimizations
- **O2**: Standard optimizations
- **O3**: Aggressive optimizations

---

## Type System

### Primitive Types

| Type    | Description                     | Size    |
|---------|---------------------------------|---------|
| i8      | 8-bit signed integer            | 1 byte  |
| i16     | 16-bit signed integer           | 2 bytes |
| i32     | 32-bit signed integer           | 4 bytes |
| i64     | 64-bit signed integer           | 8 bytes |
| f32     | 32-bit IEEE 754 float           | 4 bytes |
| f64     | 64-bit IEEE 754 float           | 8 bytes |
| bool    | Boolean                          | 1 byte  |
| char    | Unicode character                | 4 bytes |
| str     | String (UTF-8)                   | varies  |
| unit    | Unit type (void)                 | 0 bytes |

### Algebraic Data Types

EonLang supports sum types (enums) and product types (structs, tuples):

```eon
// Sum type
enum Result<T, E> {
    Ok(T),
    Err(E)
}

// Product types
struct Point3D {
    x: f64,
    y: f64,
    z: f64
}

// Tuple (anonymous product)
let point = (1.0, 2.0, 3.0);
```

### Type Inference

Hindley-Milner type inference allows:

```eon
// Type of x is inferred as i32
let x = 42;

// Type of f is inferred as fn(i32) -> i32
fn f(a) { a + 1 }

// Type of map is inferred
let map = [1, 2, 3].map(|x| x * 2);
```

---

## Memory Safety

EonLang ensures memory safety through:

### Ownership

Every value has a single owner. When ownership is transferred (moved),
the original binding becomes invalid:

```eon
fn ownership() {
    let v = vec![1, 2, 3];  // v owns the vector
    let w = v;               // Ownership moved to w
    // println(v);           // ERROR: v is no longer valid
}
```

### Borrowing

References allow temporary access without transferring ownership:

```eon
fn borrowing() {
    let v = vec![1, 2, 3];
    
    // Immutable borrow
    let r = &v;
    println(r);  // OK
    
    // Multiple immutable borrows allowed
    let r2 = &v;
    
    // Mutable borrow (exclusive)
    let r_mut = &mut v;
    r_mut.push(4);  // OK - mutable and exclusive
}
```

### Lifetime Analysis

Lifetimes track how long references are valid:

```eon
// Lifetime 'a must live at least as long as both inputs
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}
```

### Safety Rules

The borrow checker enforces:
1. No data races (mutable access is exclusive)
2. No dangling references
3. No use-after-free
4. No double-free

---

## Pattern Matching

### Pattern Types

```eon
// Literal patterns
match x {
    0 => "zero",
    1 => "one",
    _ => "other"
}

// Identifier patterns (bind)
match shape {
    Circle(r) => r * r * PI,
    Rectangle(w, h) => w * h
}

// Wildcard pattern
match opt {
    Some(x) => x,
    None => 0
}

// Range patterns
match c {
    'a'..='z' => "lowercase",
    'A'..='Z' => "uppercase",
    _ => "other"
}

// Guard clauses
match x {
    n if n < 0 => "negative",
    0 => "zero",
    n if n % 2 == 0 => "even positive",
    _ => "odd positive"
}
```

### Exhaustiveness Checking

The compiler ensures all cases are covered:

```eon
// ERROR: Non-exhaustive match
enum Color { Red, Green, Blue }
match color {
    Red => "red",
    Green => "green"
    // Blue not covered!
}
```

---

## Traits and Generics

### Traits

Traits define shared behavior:

```eon
trait Drawable {
    fn draw(self);
    fn area(self) -> f64;
}

struct Circle { radius: f64 }

impl Drawable for Circle {
    fn draw(self) {
        println("Drawing circle");
    }
    
    fn area(self) -> f64 {
        PI * self.radius * self.radius
    }
}
```

### Trait Bounds

Generic functions can require trait implementations:

```eon
// Single bound
fn print_debug<T: Debug>(value: T) {
    println("{:?}", value);
}

// Multiple bounds
fn serialize<T: Serialize + Deserialize>(value: T) {
    // ...
}

// Where clause
fn iterate<T, I>(container: T) -> I
where
    T: IntoIterator,
    T::Item: Clone
{
    // ...
}
```

### Default Implementations

Traits can provide default method implementations:

```eon
trait Greeting {
    fn greet(self) -> str;
    
    fn farewell(self) -> str {
        return "Goodbye!".to_string();
    }
}
```

### Standard Library Traits

- `Clone`: Create a deep copy
- `Copy`: Types that can be duplicated by copying bits
- `Debug`: Formatted debugging output
- `Display`: User-facing formatted output
- `PartialEq`: Equality comparison
- `PartialOrd`: Ordering comparison
- `Iterator`: Loop over sequences
- `From<T>`: Conversion from type
- `Into<T>`: Conversion into type
- `Default`: Default value

---

## Examples

### Hello World

```eon
fn main() -> i32 {
    println("Hello, World!");
    return 0;
}
```

### Fibonacci

```eon
fn fib(n: i32) -> i32 {
    if n <= 1 {
        return n;
    }
    return fib(n - 1) + fib(n - 2);
}

fn main() -> i32 {
    return fib(10);
}
```

### Pattern Matching with ADTs

```eon
enum Shape {
    Circle(f64),
    Rectangle(f64, f64)
}

fn area(shape: Shape) -> f64 {
    match shape {
        Circle(r) => 3.14159 * r * r,
        Rectangle(w, h) => w * h
    }
}
```

---

## Roadmap

### Completed Features
- [x] Lexer and tokenizer
- [x] Recursive-descent parser
- [x] AST representation
- [x] Hindley-Milner type inference
- [x] Borrow checker
- [x] Pattern matching compilation
- [x] LLVM IR generation
- [x] x86-64 code generation via LLVM

### Planned Features
- [ ] More complete stdlib
- [ ] Standard library (collections, I/O)
- [ ] Error handling improvements
- [ ] Async/await support
- [ ] Macros
- [ ] Module system improvements
- [ ] Documentation generator
- [ ] LSP support (language server)
- [ ] REPL/interpreter mode
- [ ] WebAssembly target
- [ ] Embedded systems target

---

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Clone your fork
3. Create a feature branch
4. Make your changes
5. Run tests
6. Submit a pull request

### Development Setup

```bash
# Clone
git clone https://github.com/moggan1337/EonLang.git
cd EonLang

# Install in development mode
pip install -e .

# Run tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_lexer.py -v
```

### Code Style

- Follow PEP 8
- Add type hints where possible
- Include docstrings for public APIs
- Write tests for new features

---

## License

EonLang is released under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

EonLang draws inspiration from many excellent languages and projects:

- **Rust**: Ownership, borrowing, lifetimes
- **Haskell**: Type inference, ADTs, pattern matching
- **OCaml**: Practical functional programming
- **Swift**: Syntax, protocol-oriented programming
- **MLton**: SSA IR design
- **LLVM**: State-of-the-art compiler infrastructure

---

## Contact

- GitHub Issues: https://github.com/moggan1337/EonLang/issues
- Discussions: https://github.com/moggan1337/EonLang/discussions

---

*Built with ❤️ by the EonLang team*
