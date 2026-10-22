.DEFAULT_GOAL := run
DSH_SESSION_IMAGE ?= ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.2.1-rc.2-session-persistence.2
CONTAINER_NAME ?= dsh-session-demo
PORT ?= 18080
# The sign-in URL DSH prints once ready; the token changes on every container start.
LAUNCH_URL = $$(docker logs "$(CONTAINER_NAME)" 2>&1 | grep -o 'http[^ ]*?token=[^ ]*' | tail -n 1)

.PHONY: run setup build start url stop check check-image check-dsh-image seed resume
run:
	@echo "Follow README.md or README_zh.md: configure .env, make start, make seed, make stop, make start, make resume."
setup:
	cd plugin && pnpm install --frozen-lockfile
# A bare `make build` writes a local name so it never shadows the published image;
# an image named on the command line or in the environment is used as given.
build: BUILD_IMAGE = $(if $(filter command line environment,$(origin DSH_SESSION_IMAGE)),$(DSH_SESSION_IMAGE),dsh-session:local)
build:
	docker build --platform linux/amd64 $(if $(DSH_IMAGE),--build-arg DSH_IMAGE="$(DSH_IMAGE)") -f dockerfiles/Dockerfile -t "$(BUILD_IMAGE)" .
# Starts DSH, waits until it prints its sign-in URL, and prints that URL.
start:
	docker run -d --platform linux/amd64 --name "$(CONTAINER_NAME)" --env-file .env \
	  -e DSH_PUBLIC_URL="http://127.0.0.1:$(PORT)/" -p "127.0.0.1:$(PORT):3080" "$(DSH_SESSION_IMAGE)"
	@for i in $$(seq 60); do \
	  url="$(LAUNCH_URL)"; [ -n "$$url" ] && { echo "DSH is ready. Sign in at: $$url"; exit 0; }; \
	  [ "$$(docker inspect -f '{{.State.Running}}' "$(CONTAINER_NAME)" 2>/dev/null)" = true ] || break; \
	  sleep 2; \
	done; \
	echo "DSH did not become ready; last log lines:" >&2; docker logs --tail 20 "$(CONTAINER_NAME)" >&2; exit 1
url:
	@echo "$(LAUNCH_URL)"
stop:
	docker stop --time 30 "$(CONTAINER_NAME)"
	docker rm "$(CONTAINER_NAME)"
check:
	sh -n dockerfiles/entrypoint.sh
	node --check plugin/index.js
	node --test plugin/index.test.js
	python3 -m unittest -v test_session_demo.py
check-image:
	docker run --rm --platform linux/amd64 --entrypoint node "$(DSH_SESSION_IMAGE)" --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
# Checks a DSH image you want to build on: make check-dsh-image DSH_IMAGE=your-registry/your-dsh:version
check-dsh-image:
	@[ -n "$(DSH_IMAGE)" ] || { echo "Set DSH_IMAGE to the DSH image to check" >&2; exit 2; }
	docker run --rm --platform linux/amd64 --entrypoint sh \
	  -v "$(CURDIR)/dockerfiles/check-dsh-image.sh:/check-dsh-image.sh:ro" "$(DSH_IMAGE)" /check-dsh-image.sh
seed:
	DSH_LAUNCH_URL="$${DSH_LAUNCH_URL:-$(LAUNCH_URL)}" python3 session_demo.py seed
resume:
	DSH_LAUNCH_URL="$${DSH_LAUNCH_URL:-$(LAUNCH_URL)}" python3 session_demo.py resume
