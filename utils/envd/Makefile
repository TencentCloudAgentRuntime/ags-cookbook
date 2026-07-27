.DEFAULT_GOAL := help

VERSION ?= 0.5.14
TARGET_ARCH ?= amd64

ifeq ($(VERSION),0.5.14)
GO_VERSION := 1.25.9
UPSTREAM_REVISION := a3fb26e
TEST_PACKAGES := ./internal/services/process/handler ./internal/services/process ./internal/utils
CGROUP_COMPAT_TEST_PACKAGE := ./internal/services/cgroups
CGROUP_COMPAT_TEST_NAME := TestNewCgroup2Manager_NonCgroup2FS
else ifeq ($(VERSION),0.2.11)
GO_VERSION := 1.24.3
UPSTREAM_REVISION := 1af78dd3
TEST_PACKAGES := ./internal/services/process/handler ./internal/services/process ./internal/utils
else
$(error unsupported VERSION "$(VERSION)"; choose 0.5.14 or 0.2.11)
endif

GO_IMAGE ?= golang:$(GO_VERSION)-bookworm
BUILD_REVISION ?= $(UPSTREAM_REVISION)-execenv
VERSION_DIR := /workspace/versions/$(VERSION)
OUTPUT := bin/envd-$(VERSION)

.PHONY: help build build-all test test-all test-race test-race-all verify-all clean

help:
	@echo "Available targets:"
	@echo "  make build VERSION=0.5.14      # Build bin/envd-0.5.14"
	@echo "  make build VERSION=0.2.11      # Build bin/envd-0.2.11"
	@echo "  make build-all                 # Build both versions"
	@echo "  make test VERSION=<version>    # Run focused tests"
	@echo "  make test-all                  # Test both versions"
	@echo "  make test-race-all             # Race-test both versions"
	@echo "  make verify-all                # Test, race-test, and build both"
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
		sh -c "go test -count=1 $(TEST_PACKAGES)$(if $(CGROUP_COMPAT_TEST_PACKAGE), && go test -count=1 $(CGROUP_COMPAT_TEST_PACKAGE) -run $(CGROUP_COMPAT_TEST_NAME))"

test-all:
	@$(MAKE) test VERSION=0.5.14
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
		sh -c "go test -race -count=1 $(TEST_PACKAGES)$(if $(CGROUP_COMPAT_TEST_PACKAGE), && go test -race -count=1 $(CGROUP_COMPAT_TEST_PACKAGE) -run $(CGROUP_COMPAT_TEST_NAME))"

test-race-all:
	@$(MAKE) test-race VERSION=0.5.14
	@$(MAKE) test-race VERSION=0.2.11

verify-all: test-all test-race-all build-all

clean:
	rm -f bin/envd-0.5.14 bin/envd-0.2.11
