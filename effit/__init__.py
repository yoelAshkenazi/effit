"""
effit — Custom augmented-assignment syntax for Python.
======================================================

Write ``x scale= 2`` and have it transpile to ``x = scale(x, 2)``.

Quick-start
-----------
::

    import effit

    # Activate the import hook so .eff files (and optionally .py files)
    # are transparently transpiled on import.
    effit.activate()

    # Or transpile and execute a string directly:
    ns = effit.run_string('x = 10\\nx scale= 2')
    print(ns['x'])  # 20  (assuming `scale` is defined)

API
---
"""

from __future__ import annotations

__version__ = '0.1.0'

from .parser import transpile_source, transpile_line
from .hook import install, uninstall, run_string

__all__ = [
    'activate',
    'deactivate',
    'run_string',
    'transpile_source',
    'transpile_line',
]


def activate(*, transpile_py: bool = False):
    """Install the effit import hook.

    Parameters
    ----------
    transpile_py : bool
        Also intercept ``.py`` imports (default: only ``.eff`` files).
    """
    install(transpile_py=transpile_py)


def deactivate():
    """Remove the effit import hook."""
    uninstall()
