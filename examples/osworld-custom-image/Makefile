SHELL := /bin/bash
.PHONY: setup run quickstart copy build push custom claude snapshot smoke clean check

setup:
	uv sync --frozen
	@test -f .env || cp .env.example .env

run: quickstart
quickstart:
	uv run python scripts/demo.py quickstart
copy:
	uv run python scripts/demo.py copy
build:
	uv run python scripts/demo.py build
push:
	uv run python scripts/demo.py push
custom:
	uv run python scripts/demo.py custom
claude:
	uv run python scripts/demo.py claude
snapshot:
	uv run python scripts/demo.py snapshot
smoke:
	uv run python scripts/demo.py smoke
clean:
	uv run python scripts/demo.py clean
check:
	uv run pytest -q tests
