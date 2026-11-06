.DEFAULT_GOAL := run
PI_HANDOFF_IMAGE ?= pi-session-handoff:local
PLATFORM ?= linux/amd64
PORT ?= 18081

.PHONY: run setup build check
setup:
	cd extension && npm ci
build:
	docker build --platform "$(PLATFORM)" -f dockerfiles/Dockerfile -t "$(PI_HANDOFF_IMAGE)" .
run:
	docker run --rm --env-file .env -p "127.0.0.1:$(PORT):3080" "$(PI_HANDOFF_IMAGE)"
check:
	sh -n dockerfiles/entrypoint.sh
	node --check extension/prepare.mjs
	node --check stateless/server.mjs
	cd extension && node --test *.test.js
	node --test stateless/*.test.js
