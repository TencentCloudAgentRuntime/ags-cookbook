.DEFAULT_GOAL := run

.PHONY: run check build

DSH_SESSION_IMAGE ?= ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session.11

run:
	@echo "Use the tutorial in the parent session directory."

check:
	sh -n dockerfiles/entrypoint.sh
	node --check plugin/index.js
	node --check plugin/index.test.js
	docker run --rm --platform linux/amd64 --entrypoint node \
		-e PLUGIN_MODULE=file:///usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.js \
		-v "$(CURDIR)/plugin/index.js:/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.js:ro" \
		-v "$(CURDIR)/plugin/index.test.js:/tmp/index.test.js:ro" \
		$(DSH_SESSION_IMAGE) --test /tmp/index.test.js

# A bare `make build` writes a local name so it never shadows the published image;
# an image named on the command line or in the environment is used as given.
build: BUILD_IMAGE = $(if $(filter command line environment,$(origin DSH_SESSION_IMAGE)),$(DSH_SESSION_IMAGE),dsh-brain-session:local)
build:
	docker build --platform linux/amd64 --file dockerfiles/Dockerfile --tag "$(BUILD_IMAGE)" .
