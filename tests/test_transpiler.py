"""
Comprehensive test suite for the effit transpiler.

Covers:
- Basic single-variable transpilation
- Dotted / subscripted targets
- Multiple statements in a single source
- String literal and comment safety (no false positives)
- Indentation preservation (inside if/for/def/class)
- Line continuation (backslash-joined lines)
- Python keyword safety
- Standard augmented assignments (+=, -= etc.) must NOT be mangled
- The run_string() execution helper
- Import hook installation / uninstallation
"""

from __future__ import annotations

import sys
import textwrap
import pytest

from effit.parser import transpile_line, transpile_source
from effit.hook import run_string, install, uninstall


# =========================================================================
# transpile_line — basic cases
# =========================================================================

class TestTranspileLineBasic:
    """Simple, single-line transpilation."""

    def test_basic_transform(self):
        assert transpile_line('x scale= 2') == 'x = scale(x, 2)'

    def test_basic_transform_with_newline(self):
        assert transpile_line('x scale= 2\n') == 'x = scale(x, 2)\n'

    def test_crlf_newline(self):
        assert transpile_line('x scale= 2\r\n') == 'x = scale(x, 2)\r\n'

    def test_multiple_args(self):
        assert transpile_line('my_list extend= [4, 5]') == \
               'my_list = extend(my_list, [4, 5])'

    def test_string_arg(self):
        assert transpile_line('msg greet= "hello"') == \
               'msg = greet(msg, "hello")'

    def test_no_spaces_around_equals(self):
        """``func=`` with no space before args should still match."""
        assert transpile_line('x scale=2') == 'x = scale(x, 2)'

    def test_extra_spaces(self):
        """Extra whitespace between target and operator."""
        assert transpile_line('x   scale=   2') == 'x = scale(x, 2)'

    def test_underscored_func_name(self):
        assert transpile_line('my_list append_custom= [4, 5]') == \
               'my_list = append_custom(my_list, [4, 5])'

    def test_numeric_in_func_name(self):
        assert transpile_line('data transform2= True') == \
               'data = transform2(data, True)'


# =========================================================================
# transpile_line — complex targets
# =========================================================================

class TestTranspileLineComplexTargets:
    """Dotted attributes and subscripts."""

    def test_dotted_target(self):
        assert transpile_line('obj.attr scale= 2') == \
               'obj.attr = scale(obj.attr, 2)'

    def test_subscript_target(self):
        assert transpile_line('arr[0] scale= 2') == \
               'arr[0] = scale(arr[0], 2)'

    def test_deep_dotted_target(self):
        assert transpile_line('a.b.c transform= x') == \
               'a.b.c = transform(a.b.c, x)'

    def test_subscript_and_dot(self):
        assert transpile_line('obj[0].attr scale= 3') == \
               'obj[0].attr = scale(obj[0].attr, 3)'


# =========================================================================
# transpile_line — must NOT match (safety)
# =========================================================================

class TestTranspileLineNoMatch:
    """Lines that must pass through unchanged."""

    def test_standard_assignment(self):
        line = 'x = 10'
        assert transpile_line(line) == line

    def test_augmented_add(self):
        line = 'x += 1'
        assert transpile_line(line) == line

    def test_augmented_sub(self):
        line = 'x -= 1'
        assert transpile_line(line) == line

    def test_augmented_mul(self):
        line = 'x *= 2'
        assert transpile_line(line) == line

    def test_comparison(self):
        line = 'if x == 2:'
        assert transpile_line(line) == line

    def test_function_def(self):
        line = 'def foo(x=1):'
        assert transpile_line(line) == line

    def test_class_def(self):
        line = 'class Foo(Bar):'
        assert transpile_line(line) == line

    def test_decorator(self):
        line = '@decorator'
        assert transpile_line(line) == line

    def test_import_statement(self):
        line = 'import os'
        assert transpile_line(line) == line

    def test_keyword_as_func(self):
        """Python keywords must never be treated as the custom operator."""
        line = 'x return= 5'
        assert transpile_line(line) == line

    def test_keyword_as_target(self):
        line = 'if something= 5'
        assert transpile_line(line) == line

    def test_empty_line(self):
        assert transpile_line('') == ''

    def test_comment_line(self):
        line = '# x scale= 2'
        assert transpile_line(line) == line

    def test_string_containing_pattern(self):
        """Pattern inside a string literal must NOT be rewritten."""
        line = 'x = "y scale= 2"'
        assert transpile_line(line) == line

    def test_inline_comment_with_pattern(self):
        """Pattern inside an inline comment must NOT be rewritten."""
        line = 'x = 10  # x scale= 2'
        assert transpile_line(line) == line


# =========================================================================
# transpile_line — indentation
# =========================================================================

class TestTranspileLineIndentation:
    """Indented lines (inside blocks) must keep their indentation."""

    def test_single_indent(self):
        assert transpile_line('    x scale= 2') == '    x = scale(x, 2)'

    def test_double_indent(self):
        assert transpile_line('        x scale= 2') == '        x = scale(x, 2)'

    def test_tab_indent(self):
        assert transpile_line('\tx scale= 2') == '\tx = scale(x, 2)'


# =========================================================================
# transpile_source — multi-line
# =========================================================================

class TestTranspileSource:
    """Full source strings with multiple lines."""

    def test_multiple_lines(self):
        source = textwrap.dedent("""\
            x = 10
            x scale= 2
            y = 20
            y double= 3
        """)
        expected = textwrap.dedent("""\
            x = 10
            x = scale(x, 2)
            y = 20
            y = double(y, 3)
        """)
        assert transpile_source(source) == expected

    def test_inside_function(self):
        source = textwrap.dedent("""\
            def transform(x):
                x scale= 2
                return x
        """)
        expected = textwrap.dedent("""\
            def transform(x):
                x = scale(x, 2)
                return x
        """)
        assert transpile_source(source) == expected

    def test_inside_if_block(self):
        source = textwrap.dedent("""\
            if True:
                x scale= 2
            else:
                x scale= 3
        """)
        expected = textwrap.dedent("""\
            if True:
                x = scale(x, 2)
            else:
                x = scale(x, 3)
        """)
        assert transpile_source(source) == expected

    def test_mixed_normal_and_custom(self):
        source = textwrap.dedent("""\
            x = 10
            x += 5
            x scale= 2
            print(x)
        """)
        expected = textwrap.dedent("""\
            x = 10
            x += 5
            x = scale(x, 2)
            print(x)
        """)
        assert transpile_source(source) == expected

    def test_continuation_line(self):
        """Backslash continuation should be collapsed and transpiled."""
        source = 'x scale= \\\n    2\n'
        result = transpile_source(source)
        # After collapsing, should produce: 'x = scale(x, 2)\n'
        assert 'x = scale(x,' in result
        assert '2)' in result

    def test_preserves_strings(self):
        source = textwrap.dedent("""\
            msg = "x scale= 2"
            x scale= 2
        """)
        expected = textwrap.dedent("""\
            msg = "x scale= 2"
            x = scale(x, 2)
        """)
        assert transpile_source(source) == expected


# =========================================================================
# run_string — execution
# =========================================================================

class TestRunString:
    """End-to-end execution through run_string()."""

    def test_basic_execution(self):
        source = textwrap.dedent("""\
            def scale(x, factor):
                return x * factor

            x = 10
            x scale= 2
        """)
        ns = run_string(source)
        assert ns['x'] == 20

    def test_list_operation(self):
        source = textwrap.dedent("""\
            def append_items(lst, items):
                return lst + items

            my_list = [1, 2, 3]
            my_list append_items= [4, 5]
        """)
        ns = run_string(source)
        assert ns['my_list'] == [1, 2, 3, 4, 5]

    def test_chained_operations(self):
        source = textwrap.dedent("""\
            def add(x, y):
                return x + y

            def mul(x, y):
                return x * y

            x = 5
            x add= 3
            x mul= 2
        """)
        ns = run_string(source)
        assert ns['x'] == 16  # (5 + 3) * 2

    def test_string_operation(self):
        source = textwrap.dedent("""\
            def append_str(s, suffix):
                return s + suffix

            msg = "hello"
            msg append_str= " world"
        """)
        ns = run_string(source)
        assert ns['msg'] == 'hello world'

    def test_dict_operation(self):
        source = textwrap.dedent("""\
            def merge(d, other):
                result = dict(d)
                result.update(other)
                return result

            data = {"a": 1}
            data merge= {"b": 2}
        """)
        ns = run_string(source)
        assert ns['data'] == {'a': 1, 'b': 2}

    def test_with_existing_globals(self):
        """run_string should respect a pre-populated namespace."""
        def double(x, _unused):
            return x * 2

        ns = {'double': double}
        run_string('x = 5\nx double= None', globs=ns)
        assert ns['x'] == 10

    def test_inside_loop(self):
        source = textwrap.dedent("""\
            def add(x, y):
                return x + y

            total = 0
            for i in range(5):
                total add= i
        """)
        ns = run_string(source)
        assert ns['total'] == 10  # 0+0+1+2+3+4

    def test_inside_nested_function(self):
        source = textwrap.dedent("""\
            def add(x, y):
                return x + y

            def compute():
                x = 1
                x add= 2
                return x

            result = compute()
        """)
        ns = run_string(source)
        assert ns['result'] == 3


# =========================================================================
# Import hook
# =========================================================================

class TestImportHook:
    """Test install/uninstall of the meta-path finder."""

    def test_install_and_uninstall(self):
        from effit.hook import EffitFinder
        finder = install()
        assert isinstance(finder, EffitFinder)
        assert finder in sys.meta_path

        uninstall()
        assert finder not in sys.meta_path

    def test_double_install_is_idempotent(self):
        f1 = install()
        f2 = install()
        assert f1 is f2
        # Clean up
        uninstall()

    def test_uninstall_when_not_installed(self):
        """Should not raise."""
        uninstall()
        uninstall()  # second call should be a no-op
