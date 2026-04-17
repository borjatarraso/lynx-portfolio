# Testing Guide

Lynx Portfolio has two test suites: **pytest** for unit tests and
**Robot Framework** for BDD-style functional/integration tests.

---

## Prerequisites

```bash
# Install the project in editable mode
pip install -e .

# Install test dependencies
pip install pytest robotframework robotframework-requests
```

The Robot Framework API tests require the `robotframework-requests` library
for HTTP session handling.

---

## Quick run (all tests)

```bash
# Unit tests
python -m pytest tests/ -v

# Robot Framework tests (all suites)
python -m robot --outputdir results tests/robot/

# Both in sequence
python -m pytest tests/ -v && python -m robot --outputdir results tests/robot/
```

---

## Unit tests (pytest)

Unit tests live in `tests/` and cover the internal Python modules directly.

### Test files

| File                   | Module tested     | Tests | What it covers                        |
|------------------------|-------------------|-------|---------------------------------------|
| `test_vault.py`        | `vault.py`, `backup.py` | 29 | Key derivation, file encryption roundtrip, wrong password, vault session lifecycle, backup create/restore, edge cases |
| `test_default_mode.py` | `cli.py`, `config.py`   | 10 | Default mode selection (production vs first-run), database creation, empty portfolio detection, config state |
| `test_validation.py`   | `validation.py`         | 50 | Ticker/ISIN/exchange/shares/price validation, edge cases (SQL injection, unicode, negative values, overlong strings) |

### Running specific tests

```bash
# All unit tests
python -m pytest tests/ -v

# Single test file
python -m pytest tests/test_vault.py -v

# Single test class
python -m pytest tests/test_validation.py::TestValidateTicker -v

# Single test method
python -m pytest tests/test_validation.py::TestValidateTicker::test_sql_injection -v

# With short output
python -m pytest tests/ -q

# Stop on first failure
python -m pytest tests/ -x
```

---

## Robot Framework tests

Robot Framework tests live in `tests/robot/` and use BDD-style
Given/When/Then keywords. They test the application end-to-end by running
the actual `lynx-portfolio.py` script as a subprocess.

### Test suites

| File                       | Tests | What it covers                              |
|----------------------------|-------|---------------------------------------------|
| `cli_tests.robot`          | 9     | Console mode: version, add, list, show, update, delete, import |
| `vault_tests.robot`        | 9     | Encryption: encrypt, decrypt, wrong password, disable, restore, edge cases |
| `default_mode_tests.robot` | 6     | Production default, devel mode, console subcommands, version flag, vault ops |
| `api_tests.robot`          | 18    | REST API: health, version, CRUD, refresh, cache, forex, input validation (400 errors) |

### Shared resources

All suites use `tests/robot/resources/common.robot` which provides:

- **Setup/teardown**: creates a temporary database via `LYNX_DB_PATH` env var
- **`Run Lynx` keyword**: executes `lynx-portfolio.py -c` with arguments
- **BDD step keywords**: `an instrument "AAPL" with 10 shares at avg price 150`,
  `the user lists the portfolio`, `the output should contain "text"`, etc.

### Running Robot tests

```bash
# All Robot suites
python -m robot --outputdir results tests/robot/

# Single suite
python -m robot --outputdir results tests/robot/cli_tests.robot

# Multiple specific suites
python -m robot --outputdir results \
  tests/robot/cli_tests.robot \
  tests/robot/vault_tests.robot

# Single test case by name
python -m robot --outputdir results \
  --test "Add Instrument With Cost Basis" \
  tests/robot/cli_tests.robot

# Tests matching a pattern
python -m robot --outputdir results \
  --test "*Encrypt*" \
  tests/robot/vault_tests.robot

# With verbose console output
python -m robot --outputdir results --loglevel DEBUG tests/robot/cli_tests.robot
```

### API tests

The API test suite starts a Flask server on port 15123 as a background
process, runs HTTP requests against it, and stops the server on teardown.

```bash
# Run API tests only
python -m robot --outputdir results tests/robot/api_tests.robot
```

The API tests require the `RequestsLibrary` Robot Framework library:

```bash
pip install robotframework-requests
```

If port 15123 is in use, the API tests will fail. Make sure no other instance
is running on that port.

### Test output

Robot Framework generates three output files in the `--outputdir` directory:

| File          | Purpose                                    |
|---------------|--------------------------------------------|
| `output.xml`  | Machine-readable test results              |
| `log.html`    | Detailed execution log (click to expand)   |
| `report.html` | Summary report with pass/fail statistics   |

Open `report.html` in a browser for a visual overview, or `log.html` for
step-by-step execution details.

### How the test isolation works

All tests use the `LYNX_DB_PATH` environment variable to point the
application at a temporary database file. This ensures:

- Tests never touch the production database
- Each suite gets a fresh, empty database
- Tests can run in parallel without interference (different temp files)

The `Setup Temp Database` keyword in `common.robot` creates the temp file,
and `Teardown Temp Database` removes it after the suite completes.

For tests that need to verify `--devel` mode behavior, the `LYNX_DB_PATH`
environment variable is temporarily removed so the CLI falls through to
its normal mode-selection logic.

---

## Test coverage summary

| Category           | Tests | Framework |
|--------------------|-------|-----------|
| Vault & backup     | 29    | pytest    |
| Default mode       | 10    | pytest    |
| Input validation   | 50    | pytest    |
| CLI commands       | 9     | Robot     |
| Vault operations   | 9     | Robot     |
| Default mode (E2E) | 6     | Robot     |
| REST API           | 18    | Robot     |
| **Total**          | **131** |         |

---

## Writing new tests

### Adding a pytest test

Create a new file `tests/test_<module>.py`:

```python
import pytest
from lynx_portfolio.<module> import <function>

class TestMyFeature:
    def test_basic_case(self):
        result = <function>(valid_input)
        assert result == expected

    def test_edge_case(self):
        with pytest.raises(ValueError):
            <function>(bad_input)
```

### Adding a Robot test

Add test cases to an existing `.robot` file or create a new one that
imports `resources/common.robot`:

```robot
*** Settings ***
Resource    resources/common.robot
Suite Setup       Setup Temp Database
Suite Teardown    Teardown Temp Database

*** Test Cases ***
My New Test
    [Documentation]    Describe what this test verifies.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user lists the portfolio
    Then the output should contain "Apple" ignoring case
```

Use `Run Lynx` for direct command execution, or the BDD step keywords
defined in `common.robot` for readable Given/When/Then style.
