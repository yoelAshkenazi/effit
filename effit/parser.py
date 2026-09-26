r"""
effit.parser
~~~~~~~~~~~~

Core transpilation engine that rewrites the custom ``func=`` augmented-
assignment syntax into standard Python function calls.

Pattern
-------
``<target> <func>= <args>``  →  ``<target> = <func>(<target>, <args>)``

The parser works **line-by-line** using a carefully constructed regex that
avoids matching inside string literals or comments.  It is intentionally
*not* a full tokenizer — the goal is a lightweight, predictable transform
that can be composed with Python's own compilation pipeline.

Design decisions
~~~~~~~~~~~~~~~~
* We match only at *statement level* — a line whose non-whitespace content
  starts with ``<identifier> <identifier>=``.  This avoids false positives
  inside expressions, function signatures, and decorator lines.
* We preserve leading indentation so transpiled code stays syntactically
  valid inside ``if``/``for``/``def``/``class`` blocks.
* Multi-line statements joined with ``\`` are collapsed before matching
  and re-expanded afterward.
* String literals and comments are masked before matching, then restored
  afterward, to prevent false positives like ``x = "y scale= 2"``.
"""

from __future__ import annotations

import re
import tokenize
import io
from typing import List

# ---------------------------------------------------------------------------
# Regex components
# ---------------------------------------------------------------------------

# A valid Python identifier (cannot start with a digit).
_IDENT = r'[A-Za-z_]\w*'

# Dotted or subscript target — e.g. ``obj``, ``obj.attr``, ``obj[0].attr``
# We keep it simple: an identifier optionally followed by dot-chains and
# bracket-chains.
_TARGET = (
    rf'(?P<target>{_IDENT}(?:\.\w+|\[[^\]]*\])*)'
)

# The custom operator: an identifier immediately followed by ``=`` but
# *not* ``==``.  We use a negative lookahead to exclude ``==``.
_OPERATOR = rf'(?P<func>{_IDENT})=(?!=)'

# Everything remaining on the line is the argument(s).
_ARGS = r'(?P<args>.+)'

# Full pattern: optional leading whitespace, target, whitespace, operator,
# optional whitespace, args.
_PATTERN = re.compile(
    rf'^(?P<indent>\s*){_TARGET}\s+{_OPERATOR}\s*{_ARGS}$'
)

# ---------------------------------------------------------------------------
# Tokens we must *not* match inside
# ---------------------------------------------------------------------------

# Regex that matches Python string literals (single/double, triple-quoted,
# raw, byte, f-string prefixes) and comments.
_STRING_OR_COMMENT = re.compile(
    r'(?:'
    # Triple-quoted strings (must come before single-quoted)
    r'(?:[bBuUfFrR]{0,2})"""[\s\S]*?"""'
    r'|'
    r"(?:[bBuUfFrR]{0,2})'''[\s\S]*?'''"
    r'|'
    # Single-line strings
    r'(?:[bBuUfFrR]{0,2})"(?:[^"\\]|\\.)*"'
    r'|'
    r"(?:[bBuUfFrR]{0,2})'(?:[^'\\]|\\.)*'"
    r'|'
    # Comments
    r'#.*$'
    r')'
)

# Built-in augmented assignment operators that must NOT be treated as
# our custom syntax.
_BUILTIN_AUGMENTED = frozenset({
    # Standard augmented assignments  (PEP 203 & later additions)
    # The identifier part (before '=') for each:
    # +=  -=  *=  /=  //=  %=  **=  &=  |=  ^=  >>=  <<=  @=
    # These are all *operator* characters, not identifiers, so our regex
    # (_IDENT requiring [A-Za-z_]\w*) will never match them.  This set is
    # here purely as a safety net for future-proofing.
})

# Python keywords — we never treat a keyword followed by ``=`` as our
# custom operator.
_PYTHON_KEYWORDS = frozenset({
    'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
    'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
    'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
    'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
    'while', 'with', 'yield',
})


# ---------------------------------------------------------------------------
# String masking helpers
# ---------------------------------------------------------------------------

class _Masker:
    """Replace string literals and comments with opaque placeholders so the
    main regex never matches inside them.  After transformation the
    placeholders are restored."""

    _PLACEHOLDER = '\x00EFFIT{}\x00'

    def __init__(self) -> None:
        self._stash: List[str] = []

    def mask(self, source: str) -> str:
        """Replace strings/comments with placeholders."""
        def _replace(m: re.Match) -> str:
            idx = len(self._stash)
            self._stash.append(m.group(0))
            return self._PLACEHOLDER.format(idx)
        return _STRING_OR_COMMENT.sub(_replace, source)

    def unmask(self, source: str) -> str:
        """Restore original strings/comments from placeholders."""
        for idx, original in enumerate(self._stash):
            source = source.replace(self._PLACEHOLDER.format(idx), original)
        return source


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transpile_line(line: str) -> str:
    """Transpile a single logical line.

    Parameters
    ----------
    line : str
        A single line of source code (trailing newline optional).

    Returns
    -------
    str
        The transpiled line, or the original line unchanged if no custom
        syntax was detected.

    Examples
    --------
    >>> transpile_line('x scale= 2')
    'x = scale(x, 2)'
    >>> transpile_line('  my_list append_custom= [4, 5]')
    '  my_list = append_custom(my_list, [4, 5])'
    """
    # Strip trailing newline for matching, remember it for output.
    newline = ''
    if line.endswith('\r\n'):
        newline = '\r\n'
        line = line[:-2]
    elif line.endswith('\n'):
        newline = '\n'
        line = line[:-1]

    masker = _Masker()
    masked = masker.mask(line)
    match = _PATTERN.match(masked)

    if match is None:
        return line + newline

    indent = match.group('indent')
    target = match.group('target')
    func = match.group('func')
    args = match.group('args')

    # Safety: skip Python keywords used as the "function" name.
    if func in _PYTHON_KEYWORDS:
        return line + newline

    # Safety: skip if target is a keyword (e.g., ``return x= 1`` would be
    # a syntax error in standard Python anyway, but let's not mangle it).
    bare_target = target.split('.')[0].split('[')[0]
    if bare_target in _PYTHON_KEYWORDS:
        return line + newline

    # Unmask the args (they may contain strings).
    args = masker.unmask(args).strip()

    # Unmask the target too (unlikely to contain strings but be safe).
    target = masker.unmask(target)
    func = masker.unmask(func)

    result = f'{indent}{target} = {func}({target}, {args})'
    return result + newline


def transpile_source(source: str) -> str:
    """Transpile a complete source string.

    Handles continuation lines (``\\``-joined) by collapsing them before
    matching, then produces single-line output for each matched statement.

    Parameters
    ----------
    source : str
        Complete Python source code (may contain the custom syntax).

    Returns
    -------
    str
        The transpiled source code, valid standard Python.
    """
    # --- 1. Collapse line continuations -----------------------------------
    # Replace `\<newline>` with a sentinel so we can treat multi-line
    # statements as single logical lines.
    _CONTINUATION = '\\\n'
    _SENTINEL = '\x01CONT\x01'

    working = source.replace('\\\r\n', _SENTINEL).replace(_CONTINUATION, _SENTINEL)

    lines = working.split('\n')
    result_lines: List[str] = []

    for line in lines:
        # If this logical line contains continuations, flatten them.
        if _SENTINEL in line:
            flat = line.replace(_SENTINEL, ' ')
            result_lines.append(transpile_line(flat))
        else:
            result_lines.append(transpile_line(line))

    return '\n'.join(result_lines)
