.DEFAULT_GOAL := run

.PHONY: run check build

DSH_SESSION_IMAGE ?= ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session.9

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

build:
	docker build --platform linux/amd64 --file dockerfiles/Dockerfile --tag "$(DSH_SESSION_IMAGE)" .
