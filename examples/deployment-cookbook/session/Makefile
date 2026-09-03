.DEFAULT_GOAL := run

.PHONY: run check build

run:
	@echo "Follow README.md (English) or README_zh.md (Chinese) to connect a deployed DSH agent loop to Agent Runtime Session."

check:
	python3 -m py_compile session_demo.py
	sh -n dockerfiles/entrypoint.sh
	node --check plugin/index.js
	node --check plugin/index.test.js

build:
	docker build --platform linux/amd64 --file dockerfiles/Dockerfile --tag "$${DSH_SESSION_IMAGE:?DSH_SESSION_IMAGE is required}" .
