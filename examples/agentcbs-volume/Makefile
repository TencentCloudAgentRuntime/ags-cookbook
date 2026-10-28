.DEFAULT_GOAL := help

.PHONY: help setup run cleanup check

help:
	@echo "Targets:"
	@echo "  make setup    Install Python dependencies with uv"
	@echo "  make run      Create the VolumeTemplate + Tool (first run) and start a sandbox with the Volume"
	@echo "  make cleanup  Delete the Tool, all derived Volumes (and their data), and the template"
	@echo "  make check    Local syntax checks"

setup:
	uv sync

run:
	uv run scripts/run.py

cleanup:
	uv run scripts/cleanup.py

check:
	python3 -m py_compile scripts/common.py scripts/run.py scripts/cleanup.py
