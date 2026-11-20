.DEFAULT_GOAL := run

.PHONY: setup run

setup:
	uv sync --locked

run:
	@uv run --locked python mcp_client.py
