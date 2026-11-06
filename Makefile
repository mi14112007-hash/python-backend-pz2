PYTHON ?= python3
ARGS ?=

install:
	$(PYTHON) -m pip install -r requirements.txt
server:
	$(PYTHON) -m src.server $(ARGS)
examples:
	$(PYTHON) -m src.examples
demo:
	$(PYTHON) -m src.demo
test:
	$(PYTHON) -m coverage run -m pytest -q
	$(PYTHON) -m coverage report -m
	$(PYTHON) -m coverage html
lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
