.DEFAULT_GOAL := help

WORKSPACE ?= .
COMMAND ?= python workload/ci_task.py
ARTIFACT_PATH ?= workload/output
OUTPUT_DIR ?= ags-results

.PHONY: help setup run test clean

help:
	@echo "Available targets:"
	@echo "  make setup  # install the Python dependency"
	@echo "  make run    # run COMMAND in a fresh AGS sandbox"
	@echo "  make test   # run local unit tests without AGS credentials"

setup:
	uv sync

run:
	uv run python main.py \
		--workspace "$(WORKSPACE)" \
		--command "$(COMMAND)" \
		--artifact-path "$(ARTIFACT_PATH)" \
		--output-dir "$(OUTPUT_DIR)"

test:
	uv run python -m unittest -v test_runner.py

clean:
	rm -rf "$(OUTPUT_DIR)" workload/output
