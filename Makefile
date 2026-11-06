.PHONY: install server examples demo test lint

PYTHON ?= python3
ARGS ?=

install:
	"$(PYTHON)" -m pip install -r requirements.txt
server:
	"$(PYTHON)" -m src.app $(ARGS)
examples:
	"$(PYTHON)" -c "from src.compress import examples; examples()"
demo:
	"$(PYTHON)" -m src.demo
test:
	"$(PYTHON)" -m coverage run -m pytest -q
	"$(PYTHON)" -m coverage report -m
	"$(PYTHON)" -m coverage html
lint:
	"$(PYTHON)" -m ruff check --select E,F,I,C90,N --line-length 79 src tests
	"$(PYTHON)" -m ruff format --check --line-length 79 src tests
