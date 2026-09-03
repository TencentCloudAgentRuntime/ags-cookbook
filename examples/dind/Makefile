SHELL := /bin/bash

ifneq (,$(wildcard .env))
include .env
export
endif

REPO_ROOT := $(abspath ../..)
DIND_DOCKERFILE := $(CURDIR)/image/Dockerfile
ENVD_BUILD_REVISION ?= $(shell git -C $(REPO_ROOT) log -1 --format=%H -- utils/envd/versions/0.5.14-oci)

IMAGE_GZ ?= ccr.ccs.tencentyun.com/ags-image/dind:v1.0.0
IMAGE_HK ?= hkccr.ccs.tencentyun.com/ags-image/dind:v1.0.0
AGR_BIN ?= agr

.PHONY: setup build-image push-images create-tool start harbor-oracle run cleanup

setup:
	@command -v "$(AGR_BIN)" >/dev/null || { \
		echo "agr is required; install it from https://github.com/TencentCloudAgentRuntime/ags-cli"; \
		exit 1; \
	}
	@current_version="$$($(AGR_BIN) version -o json --jq '.Data.Version')"; \
	update_available="$$($(AGR_BIN) update --check -o json --jq '.Data.update_available')" || { \
		echo "Unable to check the latest agr version."; \
		exit 1; \
	}; \
	if [[ "$$update_available" == "true" ]]; then \
		latest_version="$$($(AGR_BIN) update --check -o json --jq '.Data.latest')"; \
		echo "agr $$current_version is outdated; latest is v$${latest_version#v}."; \
		echo "Upgrade with: curl -fsSL https://github.com/TencentCloudAgentRuntime/ags-cli/releases/latest/download/install.sh | sh"; \
		exit 1; \
	fi; \
	echo "agr $$current_version is the latest version."
	@test -f .env || cp .env.example .env
	@echo "Ready. Review .env before creating cloud resources."

build-image:
	docker buildx build --platform linux/amd64 --load \
		--build-arg ENVD_BUILD_REVISION=$(ENVD_BUILD_REVISION) \
		-f $(DIND_DOCKERFILE) -t $(IMAGE_HK) $(REPO_ROOT)

push-images:
	docker buildx build --platform linux/amd64 --provenance=true \
		--build-arg ENVD_BUILD_REVISION=$(ENVD_BUILD_REVISION) \
		-f $(DIND_DOCKERFILE) -t $(IMAGE_GZ) -t $(IMAGE_HK) --push $(REPO_ROOT)

create-tool:
	./scripts/create-tool.sh

start:
	./scripts/start-instance.sh

harbor-oracle:
	./scripts/run-harbor-oracle.sh

run:
	./scripts/create-tool.sh
	./scripts/start-instance.sh
	./scripts/run-harbor-oracle.sh

cleanup:
	./scripts/cleanup.sh
