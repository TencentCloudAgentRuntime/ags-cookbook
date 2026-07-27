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
export ENVD_VERSION

ENVD_VERSION ?= 0.5.4

ifeq ($(ENVD_VERSION),0.5.4)
GO_VERSION := 1.25.4
ENVD_UPSTREAM_REVISION := 017de201
else ifeq ($(ENVD_VERSION),0.2.11)
GO_VERSION := 1.24.3
ENVD_UPSTREAM_REVISION := 1af78dd3
else
$(error unsupported ENVD_VERSION "$(ENVD_VERSION)"; choose 0.5.4 or 0.2.11)
endif

.PHONY: help setup verify build push pre-cache run all

help:
	@echo "Available targets:"
	@echo "  make setup      # Create .env from .env.example"
	@echo "  make verify     # Test ENVD_VERSION ($(ENVD_VERSION))"
	@echo "  make build      # Build the $(ENVD_VERSION) demo image"
	@echo "  make push       # Push the demo image"
	@echo "  make pre-cache  # Pre-cache the image in AGS"
	@echo "  make run        # Reproduce the problem and validate the solution"
	@echo "  make all        # Verify, build, push, pre-cache, and run"

setup:
	@test -e .env || cp .env.example .env
	@echo "Edit examples/envd-oci-env/.env before continuing."

verify:
	@$(MAKE) -C "$(ROOT_DIR)/utils/envd" test VERSION="$(ENVD_VERSION)"

build: verify
	@test -n "$(ENVD_DEMO_IMAGE)" || { echo "ENVD_DEMO_IMAGE is required"; exit 1; }
	docker build \
		--platform linux/amd64 \
		--build-arg BASE_IMAGE="$(or $(BASE_IMAGE),ubuntu:22.04)" \
		--build-arg ENVD_VERSION="$(ENVD_VERSION)" \
		--build-arg GO_VERSION="$(GO_VERSION)" \
		--build-arg ENVD_BUILD_REVISION="$(ENVD_UPSTREAM_REVISION)-execenv" \
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
