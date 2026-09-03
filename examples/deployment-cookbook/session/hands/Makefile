.DEFAULT_GOAL := check

.PHONY: check build

check:
	python3 -m py_compile hands_demo.py workspace_server.py test_hands_demo.py
	python3 -m unittest -v test_hands_demo.py

build:
	docker build --platform linux/amd64 --file dockerfiles/Dockerfile --tag "$${HANDS_SESSION_IMAGE:?HANDS_SESSION_IMAGE is required}" .
