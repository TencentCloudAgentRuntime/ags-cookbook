.DEFAULT_GOAL := run
PI_SESSION_IMAGE ?= pi-session:local

.PHONY: run setup build check seed resume cleanup
run:
	@echo "Follow README.md or README_zh.md: configure .env, make build, make seed, make resume."
setup:
	cd extension && npm ci
build:
	docker build --platform linux/amd64 -f dockerfiles/Dockerfile -t "$(PI_SESSION_IMAGE)" .
check:
	sh -n dockerfiles/entrypoint.sh
	node --check extension/prepare.mjs
	cd extension && node --test *.test.js
	python3 -m unittest -v test_session_demo.py
# seed and resume each start a fresh container with --rm: the container is gone when the command returns.
seed:
	PI_SESSION_IMAGE="$(PI_SESSION_IMAGE)" python3 session_demo.py seed
resume:
	PI_SESSION_IMAGE="$(PI_SESSION_IMAGE)" python3 session_demo.py resume
# Previews this user's Sessions; add DELETE=1 to delete them.
cleanup:
	python3 session_demo.py cleanup $(if $(filter 1,$(DELETE)),--delete)
