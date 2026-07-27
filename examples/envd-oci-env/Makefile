.DEFAULT_GOAL := help

ROOT_DIR := ../..

-include .env

export TENCENTCLOUD_SECRET_ID
export TENCENTCLOUD_SECRET_KEY
export TENCENTCLOUD_REGION
export ENVD_DEMO_IMAGE
export ENVD_IMAGE_REGISTRY_TYPE
export AGS_ROLE_ARN
export AGS_EXEC_USER
export BASE_IMAGE

.PHONY: help setup verify build push pre-cache run all

help:
	@echo "Available targets:"
	@echo "  make setup      # Create .env from .env.example"
	@echo "  make verify     # Test the bundled envd source"
	@echo "  make build      # Compile envd and build the demo image"
	@echo "  make push       # Push the demo image"
	@echo "  make pre-cache  # Pre-cache the image in AGS"
	@echo "  make run        # Reproduce the problem and validate the solution"
	@echo "  make all        # Verify, build, push, pre-cache, and run"

setup:
	@test -e .env || cp .env.example .env
	@echo "Edit examples/envd-oci-env/.env before continuing."

verify:
	@$(MAKE) -C "$(ROOT_DIR)/utils/envd" test

build: verify
	@test -n "$(ENVD_DEMO_IMAGE)" || { echo "ENVD_DEMO_IMAGE is required"; exit 1; }
	docker build \
		--platform linux/amd64 \
		--build-arg BASE_IMAGE="$(or $(BASE_IMAGE),ubuntu:22.04)" \
		-f Dockerfile \
		-t "$(ENVD_DEMO_IMAGE)" \
		"$(ROOT_DIR)"

push:
	@test -n "$(ENVD_DEMO_IMAGE)" || { echo "ENVD_DEMO_IMAGE is required"; exit 1; }
	docker push "$(ENVD_DEMO_IMAGE)"

pre-cache:
	@./validate.sh --pre-cache-only

run:
	@./validate.sh

all: verify build push pre-cache run
