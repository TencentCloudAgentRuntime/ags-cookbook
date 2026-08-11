.DEFAULT_GOAL := help

VERSION ?= 0.5.14
TARGET_ARCH ?= amd64
REPO_ROOT := $(abspath ../..)

ifeq ($(VERSION),0.5.14)
GO_VERSION := 1.25.9
BUILD_REVISION ?= a3fb26e-execenv
TEST_PACKAGES := ./internal/services/process/handler ./internal/services/process ./internal/utils
CGROUP_COMPAT_TEST_PACKAGE := ./internal/services/cgroups
CGROUP_COMPAT_TEST_NAME := TestNewCgroup2Manager_NonCgroup2FS
else ifeq ($(VERSION),0.5.14-modified)
GO_VERSION := 1.25.9
BUILD_REVISION ?= $(shell git -C "$(REPO_ROOT)" rev-parse HEAD)
TEST_PACKAGES := ./internal/execcontext ./internal/permissions ./internal/services/process/handler ./internal/services/process ./internal/utils
EXTRA_TEST_PACKAGE := ./internal/services/filesystem
EXTRA_TEST_NAME := TestStatUsesStartupIdentityWithoutAuthorization
else ifeq ($(VERSION),0.2.11)
GO_VERSION := 1.24.3
BUILD_REVISION ?= 1af78dd3-execenv
TEST_PACKAGES := ./internal/services/process/handler ./internal/services/process ./internal/utils
else
$(error unsupported VERSION "$(VERSION)"; choose 0.5.14, 0.5.14-modified, or 0.2.11)
endif

GO_IMAGE ?= golang:$(GO_VERSION)-bookworm
VERSION_DIR := /workspace/versions/$(VERSION)
OUTPUT := bin/envd-$(VERSION)

.PHONY: help build build-all test test-privileged test-all test-race test-race-all verify-all clean

help:
	@echo "Available targets:"
	@echo "  make build VERSION=0.5.14      # Build bin/envd-0.5.14"
	@echo "  make build VERSION=0.5.14-modified # Build bin/envd-0.5.14-modified"
	@echo "  make build VERSION=0.2.11      # Build bin/envd-0.2.11"
	@echo "  make build-all                 # Build all versions"
	@echo "  make test VERSION=<version>    # Run focused tests"
	@echo "  make test-privileged VERSION=0.5.14-modified # Require setuid tests to PASS"
	@echo "  make test-all                  # Test all three versions"
	@echo "  make test-race-all             # Race-test all three versions"
	@echo "  make verify-all                # Test, race-test, and build all three"
	@echo "  make clean                     # Remove local build outputs"

build:
	@mkdir -p bin
	docker run --rm \
		--platform "linux/$(TARGET_ARCH)" \
		--user "$$(id -u):$$(id -g)" \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w "$(VERSION_DIR)/src" \
		"$(GO_IMAGE)" \
		sh -c "CGO_ENABLED=0 GOOS=linux GOARCH=$(TARGET_ARCH) go build -trimpath -buildvcs=false -a -o /workspace/$(OUTPUT) -ldflags '-X=main.commitSHA=$(BUILD_REVISION) -s -w -buildid=' ."

build-all:
	@$(MAKE) build VERSION=0.5.14 TARGET_ARCH="$(TARGET_ARCH)"
	@$(MAKE) build VERSION=0.5.14-modified TARGET_ARCH="$(TARGET_ARCH)"
	@$(MAKE) build VERSION=0.2.11 TARGET_ARCH="$(TARGET_ARCH)"

test:
	docker run --rm \
		--platform linux/amd64 \
		--user "$$(id -u):$$(id -g)" \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w "$(VERSION_DIR)/src" \
		"$(GO_IMAGE)" \
		sh -c "go test -count=1 $(TEST_PACKAGES)$(if $(EXTRA_TEST_PACKAGE), && go test -count=1 $(EXTRA_TEST_PACKAGE) -run $(EXTRA_TEST_NAME))$(if $(CGROUP_COMPAT_TEST_PACKAGE), && go test -count=1 $(CGROUP_COMPAT_TEST_PACKAGE) -run $(CGROUP_COMPAT_TEST_NAME))"

test-privileged:
	@test "$(VERSION)" = 0.5.14-modified || { \
		echo "test-privileged is only defined for VERSION=0.5.14-modified"; exit 1; }
	docker run --rm \
		--platform linux/amd64 \
		-e ENVD_REQUIRE_PRIVILEGED_TESTS=1 \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w "$(VERSION_DIR)/src" \
		"$(GO_IMAGE)" \
		sh -c 'set -eu; output=/tmp/envd-privileged-tests.log; \
			if ! go test -v -count=1 ./internal/execcontext ./internal/services/process/handler >"$$output" 2>&1; then cat "$$output"; exit 1; fi; \
			cat "$$output"; \
			if grep -E -- "--- SKIP: (TestSetuid|TestPrivileged)" "$$output"; then \
				echo "privileged envd tests were skipped" >&2; exit 1; \
			fi'

test-all:
	@$(MAKE) test VERSION=0.5.14
	@$(MAKE) test VERSION=0.5.14-modified
	@$(MAKE) test VERSION=0.2.11

test-race:
	docker run --rm \
		--platform linux/amd64 \
		--user "$$(id -u):$$(id -g)" \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w "$(VERSION_DIR)/src" \
		"$(GO_IMAGE)" \
		sh -c "go test -race -count=1 $(TEST_PACKAGES)$(if $(EXTRA_TEST_PACKAGE), && go test -race -count=1 $(EXTRA_TEST_PACKAGE) -run $(EXTRA_TEST_NAME))$(if $(CGROUP_COMPAT_TEST_PACKAGE), && go test -race -count=1 $(CGROUP_COMPAT_TEST_PACKAGE) -run $(CGROUP_COMPAT_TEST_NAME))"

test-race-all:
	@$(MAKE) test-race VERSION=0.5.14
	@$(MAKE) test-race VERSION=0.5.14-modified
	@$(MAKE) test-race VERSION=0.2.11

verify-all: test-all test-race-all build-all

clean:
	rm -f bin/envd-0.5.14 bin/envd-0.5.14-modified bin/envd-0.2.11
