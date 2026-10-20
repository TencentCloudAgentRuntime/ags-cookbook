.DEFAULT_GOAL := check

.PHONY: check build

check:
	python3 -m py_compile workspace_server.py

build:
	docker build --platform linux/amd64 --file dockerfiles/Dockerfile --tag "$${HANDS_SESSION_IMAGE:?HANDS_SESSION_IMAGE is required}" .
