.DEFAULT_GOAL := help

GO_IMAGE ?= golang:1.25.9-bookworm
TARGET_ARCH ?= amd64
BUILD_REVISION ?= a3fb26e-execenv

.PHONY: help build test test-race clean

help:
	@echo "Available targets:"
	@echo "  make build      # Build bin/envd for Linux/$(TARGET_ARCH)"
	@echo "  make test       # Run environment inheritance and process tests"
	@echo "  make test-race  # Run the same tests with the Go race detector"
	@echo "  make clean      # Remove the local build output"

build:
	@mkdir -p bin
	docker run --rm \
		--platform "linux/$(TARGET_ARCH)" \
		--user "$$(id -u):$$(id -g)" \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w /workspace/src \
		"$(GO_IMAGE)" \
		sh -c "CGO_ENABLED=0 GOOS=linux GOARCH=$(TARGET_ARCH) go build -trimpath -buildvcs=false -a -o /workspace/bin/envd -ldflags '-X=main.commitSHA=$(BUILD_REVISION) -s -w -buildid=' ."

test:
	docker run --rm \
		--platform linux/amd64 \
		--user "$$(id -u):$$(id -g)" \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w /workspace/src \
		"$(GO_IMAGE)" \
		go test -count=1 ./internal/services/process/handler ./internal/services/process ./internal/utils

test-race:
	docker run --rm \
		--platform linux/amd64 \
		--user "$$(id -u):$$(id -g)" \
		-e GOCACHE=/tmp/go-build \
		-e GOMODCACHE=/tmp/go-mod \
		-v "$(CURDIR):/workspace" \
		-w /workspace/src \
		"$(GO_IMAGE)" \
		go test -race -count=1 ./internal/services/process/handler ./internal/services/process ./internal/utils

clean:
	rm -f bin/envd
