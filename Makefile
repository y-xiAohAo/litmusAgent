.PHONY: install test check lint clean format

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=src --cov-report=term-missing

check:
	mypy src/

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

precommit:
	pre-commit run --all-files

.PHONY: ci
ci: lint check test
