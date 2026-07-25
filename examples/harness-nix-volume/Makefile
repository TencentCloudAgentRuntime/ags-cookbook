SHELL := /bin/bash
PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help setup build-images build-claude-volume build-main-image push-images run cleanup check

help:
	@echo "Targets:"
	@echo "  make setup                 Install Python SDK dependencies"
	@echo "  make build-images          Build main image and Nix Claude Code image volume"
	@echo "  make build-claude-volume   Build only the Nix Claude Code image volume"
	@echo "  make build-main-image      Build only the main image"
	@echo "  make push-images           Push both images so AGS can pull them"
	@echo "  make run                   Create a Tool, or reuse TOOL_ID, then print the result URL"
	@echo "  make cleanup               Stop sandbox; set DELETE_TOOL=1 to delete tool"
	@echo "  make check                 Local syntax checks"

setup:
	uv sync

build-images: build-main-image build-claude-volume

build-main-image:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	: "$${MAIN_IMAGE_REF:?set MAIN_IMAGE_REF in .env}"; \
	ENGINE="$${CONTAINER_ENGINE:-docker}"; \
	PLATFORM="$${IMAGE_PLATFORM:-linux/amd64}"; \
	"$$ENGINE" build --platform "$$PLATFORM" -t "$$MAIN_IMAGE_REF" -f images/main/Dockerfile .

build-claude-volume:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	: "$${CLAUDE_CODE_VOLUME_IMAGE_REF:?set CLAUDE_CODE_VOLUME_IMAGE_REF in .env}"; \
	$(PYTHON) scripts/build_volume.py

push-images:
	@set -e; \
	if [ -f .env ]; then set -a; source .env; set +a; fi; \
	: "$${MAIN_IMAGE_REF:?set MAIN_IMAGE_REF in .env}"; \
	: "$${CLAUDE_CODE_VOLUME_IMAGE_REF:?set CLAUDE_CODE_VOLUME_IMAGE_REF in .env}"; \
	ENGINE="$${CONTAINER_ENGINE:-docker}"; \
	"$$ENGINE" push "$$MAIN_IMAGE_REF"; \
	"$$ENGINE" push "$$CLAUDE_CODE_VOLUME_IMAGE_REF"

run:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	uv run $(PYTHON) scripts/run.py

cleanup:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	uv run $(PYTHON) scripts/cleanup.py

check:
	bash -n .env.example
	$(PYTHON) -m py_compile \
		images/main/demo_server.py \
		images/main/start_demo.py \
		scripts/build_volume.py \
		scripts/run.py \
		scripts/cleanup.py
