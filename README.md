# effit

> **Custom augmented-assignment syntax for Python.**
> Write `x scale= 2` instead of `x = scale(x, 2)`.


[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What is effit?

**effit** introduces a custom syntax extension to Python: the **function-assignment operator**.

Instead of writing:

```python
x = scale(x, 2)
my_list = append_items(my_list, [4, 5])
data = merge(data, {"b": 2})
```

You can write:

```python
x scale= 2
my_list append_items= [4, 5]
data merge= {"b": 2}
```

The general pattern is:

```
<target> <function_name>= <arguments>
```

which transpiles to:

```python
<target> = <function_name>(<target>, <arguments>)
```

---

## Installation

```bash
pip install effit
```

For development:

```bash
git clone https://github.com/yoelAshkenazi/effit.git
cd effit
pip install -e ".[dev]"
```

---

## Quick Start

### Option 1: Using `.eff` files (recommended)

1. **Activate the hook** in your entry point (e.g., `main.py`):

```python
import effit
effit.activate()

# Now you can import .eff files as regular modules
import my_module  # will find and transpile my_module.eff
```

2. **Write your `.eff` file** (`my_module.eff`):

```python
def scale(x, factor):
    return x * factor

def add(x, y):
    return x + y

x = 10
x scale= 2    # x is now 20
x add= 5      # x is now 25
print(x)       # prints 25
```

### Option 2: Intercept `.py` files too

```python
import effit
effit.activate(transpile_py=True)

# Now ALL .py imports are transpiled (adds slight overhead)
```

### Option 3: Transpile and execute a string directly

```python
import effit

source = """
def scale(x, factor):
    return x * factor

x = 10
x scale= 2
"""

ns = effit.run_string(source)
print(ns['x'])  # 20
```

### Option 4: Just transpile (no execution)

```python
import effit

code = "x scale= 2"
print(effit.transpile_line(code))
# Output: x = scale(x, 2)

source = """
x = 10
x scale= 2
y = [1, 2]
y extend_list= [3, 4]
"""
print(effit.transpile_source(source))
# Output:
# x = 10
# x = scale(x, 2)
# y = [1, 2]
# y = extend_list(y, [3, 4])
```

---

## How It Works

### The Syntax Pattern

```
<target> <function_name>= <arguments>
```

| Component         | Description                                              |
|-------------------|----------------------------------------------------------|
| `<target>`        | Any valid Python identifier, dotted name, or subscript   |
| `<function_name>` | A valid Python identifier (not a keyword)                |
| `=`               | The assignment character (not `==`)                      |
| `<arguments>`     | Everything remaining on the line — passed as 2nd+ args   |

### Examples

| Before (effit syntax)              | After (standard Python)                         |
|------------------------------------|-------------------------------------------------|
| `x scale= 2`                      | `x = scale(x, 2)`                              |
| `my_list append_items= [4, 5]`    | `my_list = append_items(my_list, [4, 5])`       |
| `data merge= {"b": 2}`            | `data = merge(data, {"b": 2})`                 |
| `obj.attr transform= True`        | `obj.attr = transform(obj.attr, True)`          |
| `arr[0] scale= 3`                 | `arr[0] = scale(arr[0], 3)`                    |

### What is NOT matched (safety)

- Standard assignments: `x = 10`
- Augmented assignments: `x += 1`, `x *= 2`
- Comparisons: `if x == 2:`
- Patterns inside string literals: `"x scale= 2"`
- Patterns inside comments: `# x scale= 2`
- Python keywords as the function name: `x return= 5`

---

## Architecture

```
effit/
├── __init__.py   — Public API (activate, deactivate, run_string, transpile_*)
├── parser.py     — Regex-based transpiler (transpile_line, transpile_source)
└── hook.py       — PEP 302 import hook (EffitFinder, EffitLoader)
```

The transpiler works in three stages:

1. **Mask** — String literals and comments are replaced with opaque placeholders.
2. **Match** — A regex identifies the `target func= args` pattern.
3. **Rewrite** — The matched line is rewritten as `target = func(target, args)`.
4. **Unmask** — Original strings and comments are restored.

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

With coverage:

```bash
pytest --cov=effit --cov-report=term-missing
```

---

