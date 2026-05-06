# Load variables from localproxy/.env if it exists
ifneq (,$(wildcard localproxy/.env))
  include localproxy/.env
  export
endif

APP_NAME ?= sandbox-hermes
VERSION ?= latest
IMAGE_LATEST = $(DOCKER_REGISTRY)/$(APP_NAME):$(VERSION)

CONTAINER_ENGINE ?= podman

.PHONY: setup build push run run-local stop create_sandbox_tool

setup:
	@test -f localproxy/.env || (cp .env.example localproxy/.env && echo "Created localproxy/.env from .env.example -- please edit it with your credentials")
	cd localproxy && pnpm install

build:
	@test -n "$(DOCKER_REGISTRY)" || { echo "Error: DOCKER_REGISTRY is not set. Please set it in localproxy/.env"; exit 1; }
	$(CONTAINER_ENGINE) build --platform linux/amd64 -t $(IMAGE_LATEST) .

push: build
	@echo "Getting image hash from $(IMAGE_LATEST)..."
	@IMAGE_HASH=$$($(CONTAINER_ENGINE) inspect --format='{{.Id}}' $(IMAGE_LATEST) | cut -d: -f2 | cut -c1-12); \
	IMAGE_HASH_TAG=$(DOCKER_REGISTRY)/$(APP_NAME):$$IMAGE_HASH; \
	echo "Tagging and pushing with hash: $$IMAGE_HASH"; \
	$(CONTAINER_ENGINE) tag $(IMAGE_LATEST) $$IMAGE_HASH_TAG; \
	$(CONTAINER_ENGINE) push $(IMAGE_LATEST); \
	$(CONTAINER_ENGINE) push $$IMAGE_HASH_TAG; \
	echo "Pushed: $(IMAGE_LATEST)"; \
	echo "Pushed: $$IMAGE_HASH_TAG"

run:
	cd localproxy && pnpm start

# NOTE: run-local does NOT include the auto-restart loop used in AGS production.
# If Hermes crashes, the container exits. This is intentional for local debugging
# so crashes are immediately visible. See README for the AGS startup parameters.
run-local:
	$(CONTAINER_ENGINE) run --rm -it --platform linux/amd64 -p 9119:9119 -p 8642:8642 -p 49983:49983 \
		-e GATEWAY_ALLOW_ALL_USERS=true \
		--name $(APP_NAME) $(IMAGE_LATEST)

stop:
	$(CONTAINER_ENGINE) stop $(APP_NAME)

create_sandbox_tool:
	cd localproxy && pnpm run create-tool
