# Contributing to Bill Diff

Thanks for your interest in contributing! This project compares versions of U.S. appropriations bills to make the legislative process more transparent. Contributions of all kinds are welcome: bug fixes, new features, documentation improvements, and bug reports.

## Getting started

### Prerequisites

- **Python 3.12+** -- check with `python3 --version`
- **uv** (Python package manager) -- install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Git** -- for version control

### Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/civic_tech_appropriations_bills.git
cd civic_tech_appropriations_bills

# Install dependencies (including dev tools)
uv sync

# Install pre-commit hooks (runs linting/formatting automatically on commit)
uv run pre-commit install

# Run the fast test suite to verify everything works
uv run pytest -m "not slow"
```

### Optional: download bill XML for full test suite

The fast tests use inline XML and mocked data. Integration tests need real bill XML files:

```bash
# Get a free API key at https://api.congress.gov/sign-up/
echo "CONGRESS_API_KEY=your_key_here" > .env
source .env

# Download the primary test bill
uv run python fetch_bills.py download 118 hr 4366

# Run all tests (including integration tests against real XML)
uv run pytest
```

See the README for the full list of bills used by the test suite.

## Making changes

### Branch workflow

1. Create a branch from `main` for your work
2. Make your changes in small, focused commits
3. Push your branch and open a pull request

### Code style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting. If you installed the pre-commit hooks, this runs automatically on each commit. You can also run it manually:

```bash
uv run ruff check .          # Lint
uv run ruff check --fix .    # Lint and auto-fix
uv run ruff format .         # Format
```

### Testing

Tests are split into two groups:

- **Fast tests** (`pytest -m "not slow"`) -- unit tests using inline XML and mocked data. These run in under a second and don't need any bill files. CI runs these on every PR.
- **Slow tests** (`pytest`) -- integration tests against real bill XML files. These need downloaded bills in `bills/` and take a couple of minutes.

When adding new code, write tests for it. If your tests need real XML files, mark them with `@pytest.mark.slow`. Shared test helpers are in `conftest.py`.

```bash
uv run pytest -m "not slow"              # Fast tests only
uv run pytest test_diff_bill.py -v       # One test file
uv run pytest -k "test_my_function"      # Tests matching a name
```

## Submitting a pull request

1. Make sure the fast tests pass: `uv run pytest -m "not slow"`
2. Make sure linting passes: `uv run ruff check .`
3. Open a pull request against `main`
4. Describe what you changed and why
5. CI will run tests and linting automatically

## Reporting bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce (bill number, versions compared, command you ran)
- Any error output

## Questions?

Open an issue or start a discussion. There are no dumb questions.
