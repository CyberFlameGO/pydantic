import importlib
import os
import re
import sys
from pathlib import Path

import pytest

try:
    from mypy import api as mypy_api
    from mypy.version import __version__ as mypy_version

    from pydantic.mypy import parse_mypy_version

except ImportError:
    mypy_api = None
    mypy_version = None
    parse_mypy_version = lambda _: (0,)  # noqa: E731

MYPY_VERSION_TUPLE = parse_mypy_version(mypy_version)

pytestmark = pytest.mark.skipif(
    '--test-mypy' not in sys.argv
    and os.environ.get('PYCHARM_HOSTED') != '1',  # never skip when running via the PyCharm runner
    reason='Test only with "--test-mypy" flag',
)

# This ensures mypy can find the test files, no matter where tests are run from:
os.chdir(Path(__file__).parent.parent.parent)

cases = [
    ('mypy-plugin.ini', 'plugin_success.py', None),
    ('mypy-plugin.ini', 'plugin_fail.py', 'plugin-fail.txt'),
    ('mypy-plugin.ini', 'custom_constructor.py', 'custom_constructor.txt'),
    ('mypy-plugin-strict.ini', 'plugin_success.py', 'plugin-success-strict.txt'),
    ('mypy-plugin-strict.ini', 'plugin_fail.py', 'plugin-fail-strict.txt'),
    ('mypy-plugin-strict.ini', 'fail_defaults.py', 'fail_defaults.txt'),
    pytest.param(
        'mypy-default.ini',
        'success.py',
        None,
        marks=pytest.mark.skipif(
            MYPY_VERSION_TUPLE > (1, 0, 1), reason='Need to handle some more things for mypy >=1.1.1'
        ),
    ),
    ('mypy-default.ini', 'fail1.py', 'fail1.txt'),
    ('mypy-default.ini', 'fail2.py', 'fail2.txt'),
    ('mypy-default.ini', 'fail3.py', 'fail3.txt'),
    ('mypy-default.ini', 'fail4.py', 'fail4.txt'),
    ('mypy-default.ini', 'plugin_success.py', 'plugin_success.txt'),
    pytest.param('mypy-plugin-strict-no-any.ini', 'dataclass_no_any.py', None),
    pytest.param(
        'pyproject-default.toml',
        'success.py',
        None,
        marks=pytest.mark.skipif(
            MYPY_VERSION_TUPLE > (1, 0, 1), reason='Need to handle some more things for mypy >=1.1.1'
        ),
    ),
    ('pyproject-default.toml', 'fail1.py', 'fail1.txt'),
    ('pyproject-default.toml', 'fail2.py', 'fail2.txt'),
    ('pyproject-default.toml', 'fail3.py', 'fail3.txt'),
    ('pyproject-default.toml', 'fail4.py', 'fail4.txt'),
    ('pyproject-plugin.toml', 'plugin_success.py', None),
    ('pyproject-plugin.toml', 'plugin_fail.py', 'plugin-fail.txt'),
    ('pyproject-plugin-strict.toml', 'plugin_success.py', 'plugin-success-strict.txt'),
    ('pyproject-plugin-strict.toml', 'plugin_fail.py', 'plugin-fail-strict.txt'),
    ('pyproject-plugin-strict.toml', 'fail_defaults.py', 'fail_defaults.txt'),
    ('mypy-plugin-strict.ini', 'plugin_default_factory.py', 'plugin_default_factory.txt'),
    # with Config-Class
    ('mypy-plugin.ini', 'plugin_success_baseConfig.py', None),
    ('mypy-plugin.ini', 'plugin_fail_baseConfig.py', 'plugin-fail-baseConfig.txt'),
    ('mypy-plugin-strict.ini', 'plugin_success_baseConfig.py', 'plugin-success-strict-baseConfig.txt'),
    ('mypy-plugin-strict.ini', 'plugin_fail_baseConfig.py', 'plugin-fail-strict-baseConfig.txt'),
    ('mypy-default.ini', 'plugin_success_baseConfig.py', 'plugin_success_baseConfig.txt'),
    ('pyproject-plugin.toml', 'plugin_success_baseConfig.py', None),
    ('pyproject-plugin.toml', 'plugin_fail_baseConfig.py', 'plugin-fail-baseConfig.txt'),
    ('pyproject-plugin-strict.toml', 'plugin_success_baseConfig.py', 'plugin-success-strict-baseConfig.txt'),
    ('pyproject-plugin-strict.toml', 'plugin_fail_baseConfig.py', 'plugin-fail-strict-baseConfig.txt'),
    pytest.param(
        'pyproject-default.toml',
        'computed_fields.py',
        'computed_fields.txt',
        marks=pytest.mark.skipif(
            sys.version_info < (3, 8) or MYPY_VERSION_TUPLE < (0, 982),
            reason='cached_property is only available in Python 3.8+, errors are different with mypy 0.971',
        ),
    ),
]


def build_executable_modules():
    """
    Iterates over the test cases and returns a list of modules that should be executable.
    Specifically, we include any modules that are not expected to produce any typechecking errors.
    Currently, we do not skip/xfail executable modules, but I have included code below that could
    do so if uncommented.
    """
    modules = set()
    for case in cases:
        if type(case) != tuple:
            # this means it is a pytest.param
            skip_this_case = False
            for mark in case.marks:
                # Uncomment the lines below to respect skipif:
                # if mark.markname == 'skipif' and mark.args[0]:
                #     skip_this_case = True
                #     break

                # Uncomment the lines below to respect xfail:
                # if mark.markname == 'xfail':
                #     skip_this_case = True  # don't attempt to execute xfail modules
                #     break
                pass
            if skip_this_case:
                continue
            case = case.values
        _, fname, out_fname = case
        if out_fname is None:
            # no output file is present, so no errors should be produced; the module should be executable
            modules.add(fname[:-3])
    return sorted(modules)


executable_modules = build_executable_modules()


@pytest.mark.parametrize('config_filename,python_filename,output_filename', cases)
def test_mypy_results(config_filename: str, python_filename: str, output_filename: str) -> None:
    full_config_filename = f'tests/mypy/configs/{config_filename}'
    full_filename = f'tests/mypy/modules/{python_filename}'

    # Idea: tests/mypy/outputs/latest should have the latest version of the output files
    #   Older mypy versions can have their own versions of expected output files in tests/mypy/outputs/v1.0.1, etc.
    #   Only folders corresponding to mypy versions equal to or newer than the installed mypy version will be searched
    all_output_roots = [((1, 0, 1), Path('tests/mypy/outputs/v1.0.1')), ((9999,), Path('tests/mypy/outputs/latest'))]
    output_roots = [(v, p) for (v, p) in all_output_roots if v >= MYPY_VERSION_TUPLE]

    if output_filename is None:
        output_path = None
    else:
        for max_version, output_root in output_roots:
            maybe_output_path = output_root / output_filename
            if maybe_output_path.exists():
                output_path = maybe_output_path
                break
        else:
            raise FileNotFoundError(f'Could not find expected output file {output_filename} in any of {output_roots}')

    # Specifying a different cache dir for each configuration dramatically speeds up subsequent execution
    # It also prevents cache-invalidation-related bugs in the tests
    cache_dir = f'.mypy_cache/test-{os.path.splitext(config_filename)[0]}'
    command = [
        full_filename,
        '--config-file',
        full_config_filename,
        '--cache-dir',
        cache_dir,
        '--show-error-codes',
        '--show-traceback',
    ]
    if MYPY_VERSION_TUPLE >= (0, 990):
        command.append('--disable-recursive-aliases')
    print(f"\nExecuting: mypy {' '.join(command)}")  # makes it easier to debug as necessary
    actual_result = mypy_api.run(command)
    actual_out, actual_err, actual_returncode = actual_result
    # Need to strip filenames due to differences in formatting by OS
    actual_out = '\n'.join(['.py:'.join(line.split('.py:')[1:]) for line in actual_out.split('\n') if line]).strip()
    actual_out = re.sub(r'\n\s*\n', r'\n', actual_out)

    if actual_out:
        print('{0}\n{1:^100}\n{0}\n{2}\n{0}'.format('=' * 100, 'mypy output', actual_out))

    assert actual_err == ''
    expected_returncode = 0 if output_filename is None else 1
    assert actual_returncode == expected_returncode

    if output_path and not output_path.exists():
        output_path.write_text(actual_out)
        raise RuntimeError(f'wrote actual output to {output_path} since file did not exist')

    expected_out = Path(output_path).read_text().rstrip('\n') if output_path else ''

    # fix for compatibility between mypy versions: (this can be dropped once we drop support for mypy<0.930)
    if actual_out and MYPY_VERSION_TUPLE < (0, 930):
        actual_out = actual_out.lower()
        expected_out = expected_out.lower()
        actual_out = actual_out.replace('variant:', 'variants:')
        actual_out = re.sub(r'^(\d+: note: {4}).*', r'\1...', actual_out, flags=re.M)
        expected_out = re.sub(r'^(\d+: note: {4}).*', r'\1...', expected_out, flags=re.M)

    assert actual_out == expected_out, actual_out


def test_bad_toml_config() -> None:
    full_config_filename = 'tests/mypy/configs/pyproject-plugin-bad-param.toml'
    full_filename = 'tests/mypy/modules/success.py'

    # Specifying a different cache dir for each configuration dramatically speeds up subsequent execution
    # It also prevents cache-invalidation-related bugs in the tests
    cache_dir = '.mypy_cache/test-pyproject-plugin-bad-param'
    command = [full_filename, '--config-file', full_config_filename, '--cache-dir', cache_dir, '--show-error-codes']
    if MYPY_VERSION_TUPLE >= (0, 990):
        command.append('--disable-recursive-aliases')
    print(f"\nExecuting: mypy {' '.join(command)}")  # makes it easier to debug as necessary
    with pytest.raises(ValueError) as e:
        mypy_api.run(command)

    assert str(e.value) == 'Configuration value must be a boolean for key: init_forbid_extra'


@pytest.mark.parametrize('module', sorted(executable_modules))
@pytest.mark.filterwarnings('ignore:.*is deprecated.*:DeprecationWarning')
def test_success_cases_run(module: str) -> None:
    """
    Ensure the "success" files can actually be executed
    """
    importlib.import_module(f'tests.mypy.modules.{module}')


def test_explicit_reexports():
    from pydantic import __all__ as root_all
    from pydantic.deprecated.tools import __all__ as tools
    from pydantic.main import __all__ as main
    from pydantic.networks import __all__ as networks
    from pydantic.types import __all__ as types

    for name, export_all in [('main', main), ('network', networks), ('tools', tools), ('types', types)]:
        for export in export_all:
            assert export in root_all, f'{export} is in {name}.__all__ but missing from re-export in __init__.py'


def test_explicit_reexports_exist():
    import pydantic

    for name in pydantic.__all__:
        assert hasattr(pydantic, name), f'{name} is in pydantic.__all__ but missing from pydantic'


@pytest.mark.parametrize(
    'v_str,v_tuple',
    [
        ('0', (0,)),
        ('0.930', (0, 930)),
        ('0.940+dev.04cac4b5d911c4f9529e6ce86a27b44f28846f5d.dirty', (0, 940)),
    ],
)
def test_parse_mypy_version(v_str, v_tuple):
    assert parse_mypy_version(v_str) == v_tuple
