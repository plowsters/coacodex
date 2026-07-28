# Makes `tests` a real package so the cross-module imports several suites rely on
# (`from tests._spell_fixtures import ...`, `from tests.test_client_extract_cli import ...`) resolve
# under BARE `pytest` — which, unlike `python -m pytest`, does not put the CWD on sys.path. CI runs the
# bare form (E0R.1 T6.1); tests/test_e0r1_clean_env_collect.py holds that line.
