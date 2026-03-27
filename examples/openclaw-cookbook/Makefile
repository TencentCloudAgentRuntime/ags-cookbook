APP_NAME ?= sandbox-openclaw
VERSION ?= latest
DOCKER_REGISTRY ?= ccr.ccs.tencentyun.com/ags-test-image
IMAGE_LATEST = $(DOCKER_REGISTRY)/$(APP_NAME):$(VERSION)

CONTAINER_ENGINE ?= podman

.PHONY: setup build push run run-local stop

setup:
	@test -f localproxy/.env || (cp .env.example localproxy/.env && echo "📝 Created localproxy/.env from .env.example — please edit it with your credentials")
	cd localproxy && pnpm install

build:
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

run-local:
	$(CONTAINER_ENGINE) run --rm -it --platform linux/amd64 -p 8080:8080 -p 49983:49983 \
		-v $(PWD)/openclaw.json:/home/node/.openclaw/openclaw.json \
		--name $(APP_NAME) $(IMAGE_LATEST) \
		/bin/bash -l -c "/usr/bin/envd > /tmp/envd.log 2>&1 & node /app/openclaw.mjs gateway --port 8080 --bind lan --allow-unconfigured"

stop:
	$(CONTAINER_ENGINE) stop $(APP_NAME)
