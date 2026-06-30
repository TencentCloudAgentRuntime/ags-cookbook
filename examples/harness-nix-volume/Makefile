SHELL := /bin/bash
PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help setup build-images build-harness-volume build-main-image run cleanup check

help:
	@echo "Targets:"
	@echo "  make setup                 Install Python SDK dependencies"
	@echo "  make build-images          Build main image and Nix Harness image volume"
	@echo "  make build-harness-volume  Build only the Nix Harness image volume"
	@echo "  make build-main-image      Build only the main image"
	@echo "  make run                   Create AGS tool, start sandbox, verify Harness"
	@echo "  make cleanup               Stop sandbox; set DELETE_TOOL=1 to delete tool"
	@echo "  make check                 Local syntax checks"

setup:
	uv sync

build-images: build-main-image build-harness-volume

build-main-image:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	: "$${MAIN_IMAGE_REF:?set MAIN_IMAGE_REF in .env}"; \
	ENGINE="$${CONTAINER_ENGINE:-docker}"; \
	PLATFORM="$${IMAGE_PLATFORM:-linux/amd64}"; \
	"$$ENGINE" build --platform "$$PLATFORM" -t "$$MAIN_IMAGE_REF" -f images/main/Dockerfile .

build-harness-volume:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	: "$${HARNESS_VOLUME_IMAGE_REF:?set HARNESS_VOLUME_IMAGE_REF in .env}"; \
	./scripts/build-harness-volume.sh

run:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	uv run $(PYTHON) scripts/run.py

cleanup:
	@if [ -f .env ]; then set -a; source .env; set +a; fi; \
	uv run $(PYTHON) scripts/cleanup.py

check:
	bash -n .env.example
	bash -n scripts/build-harness-volume.sh
	$(PYTHON) -m py_compile scripts/run.py scripts/cleanup.py
