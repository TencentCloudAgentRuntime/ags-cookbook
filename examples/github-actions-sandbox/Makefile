.DEFAULT_GOAL := help

WORKSPACE ?= .
COMMAND ?= python workload/ci_task.py
ARTIFACT_PATH ?= workload/output
OUTPUT_DIR ?= ags-results

# Freeze caller-supplied values before Make can expand $ or $(shell ...).
# Export them as data; never interpolate them into the host shell recipe.
override COMMAND := $(value COMMAND)
override WORKSPACE := $(value WORKSPACE)
override ARTIFACT_PATH := $(value ARTIFACT_PATH)
override OUTPUT_DIR := $(value OUTPUT_DIR)
export SANDBOX_COMMAND := $(COMMAND)
export AGS_WORKSPACE := $(WORKSPACE)
export SANDBOX_ARTIFACT_PATH := $(ARTIFACT_PATH)
export AGS_RESULT_DIR := $(OUTPUT_DIR)

.PHONY: help setup run test clean

help:
	@echo "Available targets:"
	@echo "  make setup  # install the Python dependency"
	@echo "  make run    # run COMMAND in a fresh AGS sandbox"
	@echo "  make test   # run local unit tests without AGS credentials"

setup:
	uv sync

run:
	uv run python main.py

test:
	uv run python -m unittest -v test_runner.py

clean:
	rm -rf "$$AGS_RESULT_DIR" workload/output
