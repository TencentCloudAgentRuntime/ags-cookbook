.DEFAULT_GOAL := help

ROOT_DIR := ../..
REPO_COMMIT := $(shell git -C "$(ROOT_DIR)" rev-parse HEAD)

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
export ENVD_VOLUME_IMAGE
export ENVD_VOLUME_IMAGE_DIGEST
export FIXTURE_A_IMAGE
export FIXTURE_B_IMAGE
export ENVD_VOLUME_MOUNT_PATH
export AGS_INSTANCE_TIMEOUT
export AGS_ENVD_VERSION_METADATA
export AGS_API_KEY
export E2B_API_KEY
export E2B_DOMAIN
export ENVD_EXPECTED_COMMIT

# `?=` alone is not enough here: the `export ENVD_VERSION` above defines the
# variable as empty when it is absent from the environment and from .env, so the
# version check below would reject "". Treat empty as unset.
ifeq ($(strip $(ENVD_VERSION)),)
ENVD_VERSION := 0.5.14
endif

ifeq ($(ENVD_VERSION),0.5.14)
GO_VERSION := 1.25.9
ENVD_BUILD_REVISION := a3fb26e-execenv
else ifeq ($(ENVD_VERSION),0.5.14-modified)
GO_VERSION := 1.25.9
ENVD_BUILD_REVISION := a3fb26e-modified
else ifeq ($(ENVD_VERSION),0.5.14-oci)
GO_VERSION := 1.25.9
# The OCI User/Workdir defaults keep reporting 0.5.14, so the full commit is what
# makes a built artifact traceable back to its source.
ENVD_BUILD_REVISION := $(REPO_COMMIT)
else ifeq ($(ENVD_VERSION),0.2.11)
GO_VERSION := 1.24.3
ENVD_BUILD_REVISION := 1af78dd3-execenv
else
$(error unsupported ENVD_VERSION "$(ENVD_VERSION)"; choose 0.5.14, 0.5.14-modified, 0.5.14-oci, or 0.2.11)
endif

ifeq ($(strip $(ENVD_VOLUME_MOUNT_PATH)),)
ENVD_VOLUME_MOUNT_PATH := /opt/envd
endif
ifeq ($(strip $(AGS_INSTANCE_TIMEOUT)),)
AGS_INSTANCE_TIMEOUT := 20m
endif
ifeq ($(strip $(AGS_ENVD_VERSION_METADATA)),)
AGS_ENVD_VERSION_METADATA := 0.4.0
endif
ENVD_EXPECTED_COMMIT := $(ENVD_BUILD_REVISION)

.PHONY: help setup verify build push pre-cache run all \
        assert-clean-source \
        envd-volume-build envd-volume-verify envd-volume-push \
        fixtures-build fixtures-push user-workdir-build user-workdir-push \
        run-user-workdir

help:
	@echo "Available targets:"
	@echo "  make setup      # Create .env from .env.example"
	@echo "  make verify     # Test ENVD_VERSION ($(ENVD_VERSION))"
	@echo "  make build      # Build the $(ENVD_VERSION) demo image"
	@echo "  make push       # Push the demo image"
	@echo "  make pre-cache  # Pre-cache the image in AGS"
	@echo "  make run        # Reproduce the problem and validate the solution"
	@echo "  make all        # Verify, build, push, and run"
	@echo ""
	@echo "OCI User/Workdir defaults (requires ENVD_VERSION=0.5.14-oci):"
	@echo "  make envd-volume-build   # Build the setuid envd Image Volume (0:0, 4755)"
	@echo "  make envd-volume-verify  # Check 0:0/4755 in the exported image layer"
	@echo "  make envd-volume-push    # Push the Image Volume artifact"
	@echo "  make fixtures-build      # Build business fixtures A and B"
	@echo "  make fixtures-push       # Push business fixtures A and B"
	@echo "  make user-workdir-build  # Build the volume and both fixtures"
	@echo "  make user-workdir-push   # Push the volume and both fixtures"
	@echo "  make run-user-workdir    # Pre-cache, create AGS resources, run the"
	@echo "                           # E2B SDK matrix, then clean up"

setup:
	@test -e .env || cp .env.example .env
	@command -v uv >/dev/null 2>&1 || { echo "uv is required"; exit 1; }
	@uv sync --frozen
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
		--build-arg ENVD_BUILD_REVISION="$(ENVD_BUILD_REVISION)" \
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

all: verify build push run

# --- OCI User/Workdir defaults ------------------------------------------------
#
# The Image Volume artifact carries one file, /usr/bin/envd, as 0:0 mode 4755.
# The two fixtures stand in for a customer's business image: A uses a named OCI
# user with supplementary groups, B uses a bare numeric UID with no passwd entry.
#
# ENVD_VERSION must be 0.5.14-oci for these targets: the OCI User/Workdir
# defaults only exist in that distribution.

assert-clean-source:
	@status="$$(git -C "$(ROOT_DIR)" status --porcelain --untracked-files=normal)"; \
		test -z "$$status" || { \
			echo "the repository must be clean before building a traceable Image Volume"; \
			printf '%s\n' "$$status"; exit 1; \
		}
	@test "$$(git -C "$(ROOT_DIR)" rev-parse HEAD)" = "$(ENVD_BUILD_REVISION)" || { \
		echo "ENVD_BUILD_REVISION must equal the repository HEAD"; exit 1; }

envd-volume-build: assert-clean-source
	@test -n "$(ENVD_VOLUME_IMAGE)" || { echo "ENVD_VOLUME_IMAGE is required"; exit 1; }
	@test "$(ENVD_VERSION)" = 0.5.14-oci || { \
		echo "ENVD_VERSION must be 0.5.14-oci for the Image Volume artifact"; exit 1; }
	@$(MAKE) -C "$(ROOT_DIR)/utils/envd" test VERSION="$(ENVD_VERSION)"
	@$(MAKE) -C "$(ROOT_DIR)/utils/envd" test-privileged VERSION="$(ENVD_VERSION)"
	docker build \
		--platform linux/amd64 \
		--build-arg ENVD_VERSION="$(ENVD_VERSION)" \
		--build-arg GO_VERSION="$(GO_VERSION)" \
		--build-arg ENVD_BUILD_REVISION="$(ENVD_BUILD_REVISION)" \
		--build-arg TARGET_ARCH=amd64 \
		-f Dockerfile.envd-volume \
		-t "$(ENVD_VOLUME_IMAGE)" \
		"$(ROOT_DIR)"
	@$(MAKE) envd-volume-verify

# Reads the metadata out of the exported layer, because the mount is read-only
# and a runtime chmod is not an option.
envd-volume-verify:
	@test -n "$(ENVD_VOLUME_IMAGE)" || { echo "ENVD_VOLUME_IMAGE is required"; exit 1; }
	@test -n "$(ENVD_BUILD_REVISION)" || { echo "ENVD_BUILD_REVISION is required"; exit 1; }
	@./verify-envd-volume.sh "$(ENVD_VOLUME_IMAGE)" "$(ENVD_BUILD_REVISION)"

envd-volume-push: envd-volume-verify
	docker push "$(ENVD_VOLUME_IMAGE)"

fixtures-build:
	@test -n "$(FIXTURE_A_IMAGE)" || { echo "FIXTURE_A_IMAGE is required"; exit 1; }
	@test -n "$(FIXTURE_B_IMAGE)" || { echo "FIXTURE_B_IMAGE is required"; exit 1; }
	docker build \
		--platform linux/amd64 \
		--build-arg BASE_IMAGE="$(or $(BASE_IMAGE),ubuntu:22.04)" \
		-f Dockerfile.fixture-a \
		-t "$(FIXTURE_A_IMAGE)" \
		.
	docker build \
		--platform linux/amd64 \
		--build-arg BASE_IMAGE="$(or $(BASE_IMAGE),ubuntu:22.04)" \
		-f Dockerfile.fixture-b \
		-t "$(FIXTURE_B_IMAGE)" \
		.

fixtures-push:
	@test -n "$(FIXTURE_A_IMAGE)" || { echo "FIXTURE_A_IMAGE is required"; exit 1; }
	@test -n "$(FIXTURE_B_IMAGE)" || { echo "FIXTURE_B_IMAGE is required"; exit 1; }
	docker push "$(FIXTURE_A_IMAGE)"
	docker push "$(FIXTURE_B_IMAGE)"

user-workdir-build: envd-volume-build fixtures-build

user-workdir-push: envd-volume-push fixtures-push

run-user-workdir:
	@./validate_user_workdir.sh
