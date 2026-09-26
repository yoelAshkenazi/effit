"""
effit.hook
~~~~~~~~~~

PEP 302-compliant import hook that transparently transpiles source files
containing the ``func=`` custom syntax before Python's compiler sees them.

Two modes of operation
~~~~~~~~~~~~~~~~~~~~~~
1. **Opt-in file extension** (``.eff``):  Only files ending in ``.eff``
   are transpiled.  This is the safest mode and the default.
2. **Global ``.py`` interception**:  When ``install(transpile_py=True)``
   is called, *all* ``.py`` files loaded after that point are transpiled.
   Use with caution — it adds a small overhead to every import.

Usage
-----
::

    # In your project's entry-point or conftest.py:
    import effit
    effit.activate()          # installs the import hook

    # Now you can import .eff files or .py files containing func= syntax.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Optional, Sequence, Union

from .parser import transpile_source

# ---------------------------------------------------------------------------
# Finder + Loader for .eff files
# ---------------------------------------------------------------------------


class EffitFinder(importlib.abc.MetaPathFinder):
    """A meta-path finder that locates ``.eff`` source files (and
    optionally ``.py`` files) and returns an :class:`EffitLoader` for them.
    """

    def __init__(self, *, transpile_py: bool = False) -> None:
        self.transpile_py = transpile_py

    def find_module(
        self,
        fullname: str,
        path: Optional[Sequence[Union[str, bytes]]] = None,
    ):
        """Legacy find_module for broad compatibility."""
        spec = self.find_spec(fullname, path)
        if spec is not None:
            return spec.loader
        return None

    def find_spec(self, fullname, path, target=None):
        """Locate the module and return an appropriate ModuleSpec."""
        # Determine candidate directories.
        parts = fullname.split('.')
        module_name = parts[-1]

        search_dirs = list(path) if path else sys.path

        for entry in search_dirs:
            entry = str(entry)

            # --- .eff extension (always checked) ---
            eff_file = os.path.join(entry, module_name + '.eff')
            if os.path.isfile(eff_file):
                return importlib.util.spec_from_file_location(
                    fullname,
                    eff_file,
                    loader=EffitLoader(eff_file),
                    submodule_search_locations=[],
                )

            # --- .eff package (directory with __init__.eff) ---
            eff_pkg = os.path.join(entry, module_name, '__init__.eff')
            if os.path.isfile(eff_pkg):
                return importlib.util.spec_from_file_location(
                    fullname,
                    eff_pkg,
                    loader=EffitLoader(eff_pkg),
                    submodule_search_locations=[
                        os.path.join(entry, module_name)
                    ],
                )

            # --- .py interception (opt-in) ---
            if self.transpile_py:
                py_file = os.path.join(entry, module_name + '.py')
                if os.path.isfile(py_file):
                    return importlib.util.spec_from_file_location(
                        fullname,
                        py_file,
                        loader=EffitLoader(py_file),
                        submodule_search_locations=[],
                    )

                py_pkg = os.path.join(entry, module_name, '__init__.py')
                if os.path.isfile(py_pkg):
                    return importlib.util.spec_from_file_location(
                        fullname,
                        py_pkg,
                        loader=EffitLoader(py_pkg),
                        submodule_search_locations=[
                            os.path.join(entry, module_name)
                        ],
                    )

        return None


class EffitLoader(importlib.abc.Loader):
    """Loads a source file, runs it through the effit transpiler, then
    compiles and executes the resulting standard Python code."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath

    def create_module(self, spec):
        # Use default module creation semantics.
        return None

    def exec_module(self, module):
        source = Path(self.filepath).read_text(encoding='utf-8')
        transpiled = transpile_source(source)
        code = compile(transpiled, self.filepath, 'exec')
        exec(code, module.__dict__)

    # Legacy API (Python ≤ 3.3 compat, still called by some tools).
    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]

        module = types.ModuleType(fullname)
        module.__file__ = self.filepath
        module.__loader__ = self
        sys.modules[fullname] = module

        try:
            self.exec_module(module)
        except Exception:
            sys.modules.pop(fullname, None)
            raise

        return module


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_installed_finder: Optional[EffitFinder] = None


def install(*, transpile_py: bool = False) -> EffitFinder:
    """Install the effit import hook on ``sys.meta_path``.

    Parameters
    ----------
    transpile_py : bool
        If *True*, intercept ``.py`` files as well (adds overhead).
        Default is *False* (only ``.eff`` files are transpiled).

    Returns
    -------
    EffitFinder
        The installed finder instance.
    """
    global _installed_finder

    if _installed_finder is not None:
        # Already installed — update setting and return.
        _installed_finder.transpile_py = transpile_py
        return _installed_finder

    finder = EffitFinder(transpile_py=transpile_py)
    # Insert at the *beginning* so we get first crack before the default
    # finders.
    sys.meta_path.insert(0, finder)
    _installed_finder = finder
    return finder


def uninstall() -> None:
    """Remove the effit import hook from ``sys.meta_path``."""
    global _installed_finder
    if _installed_finder is not None:
        try:
            sys.meta_path.remove(_installed_finder)
        except ValueError:
            pass
        _installed_finder = None


def run_string(source: str, globs: Optional[dict] = None) -> dict:
    """Transpile and execute a source string.  Useful for REPL-style
    usage and testing.

    Parameters
    ----------
    source : str
        Source code potentially containing ``func=`` syntax.
    globs : dict, optional
        Global namespace to execute in.  If *None* a fresh dict is used.

    Returns
    -------
    dict
        The global namespace after execution.
    """
    transpiled = transpile_source(source)
    if globs is None:
        globs = {}
    exec(compile(transpiled, '<effit>', 'exec'), globs)
    return globs
