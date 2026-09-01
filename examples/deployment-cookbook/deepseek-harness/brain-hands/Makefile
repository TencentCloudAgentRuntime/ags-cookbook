.DEFAULT_GOAL := help

CONTAINER_ENGINE ?= podman
BRAIN_IMAGE ?= ags-cookbook/dsh-brain:local
HANDS_IMAGE ?= ags-cookbook/dsh-hands:local

.PHONY: help install typecheck test test-mysql build build-brain build-hands

help:
	@echo "Targets: install typecheck test test-mysql build-brain build-hands build"

install:
	pnpm install --frozen-lockfile

typecheck:
	pnpm typecheck

test:
	pnpm test

test-mysql:
	RUN_MYSQL_INTEGRATION=1 pnpm test:mysql

build-brain:
	$(CONTAINER_ENGINE) build --platform linux/amd64 --tag $(BRAIN_IMAGE) --file dockerfiles/brain/Dockerfile .

build-hands:
	$(CONTAINER_ENGINE) build --platform linux/amd64 --tag $(HANDS_IMAGE) --file dockerfiles/hands/Dockerfile dockerfiles/hands

build: build-brain build-hands
