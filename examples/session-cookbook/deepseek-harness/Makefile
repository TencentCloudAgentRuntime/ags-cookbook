.DEFAULT_GOAL := run
DSH_SESSION_IMAGE ?= ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.2
DSH_IMAGE ?= ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4
CONTAINER_NAME ?= dsh-session-demo
PORT ?= 18080
.PHONY: run setup build start stop check check-image seed resume
run:
	@echo "Follow README.md or README_zh.md: configure .env, make start, make seed, recreate the container, make resume."
setup:
	cd plugin && pnpm install --frozen-lockfile
# Local builds default to a local name so they never shadow the published image.
build: DSH_SESSION_IMAGE = dsh-session:local
build:
	docker build --platform linux/amd64 --build-arg DSH_IMAGE="$(DSH_IMAGE)" -f dockerfiles/Dockerfile -t "$(DSH_SESSION_IMAGE)" .
start:
	docker run -d --platform linux/amd64 --name "$(CONTAINER_NAME)" --env-file .env -p "127.0.0.1:$(PORT):3080" "$(DSH_SESSION_IMAGE)"
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
seed:
	python3 session_demo.py seed
resume:
	python3 session_demo.py resume
