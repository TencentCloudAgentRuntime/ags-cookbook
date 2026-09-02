.DEFAULT_GOAL := help

CONTAINER_ENGINE ?= podman
BRAIN_IMAGE ?= ags-cookbook/dsh-brain:local
HANDS_UBUNTU_IMAGE ?= ags-cookbook/dsh-hands:ubuntu-local
HANDS_ALPINE_IMAGE ?= ags-cookbook/dsh-hands:alpine-local

.PHONY: help install typecheck test test-mysql build build-brain build-hands build-hands-ubuntu build-hands-alpine

help:
	@echo "Targets: install typecheck test test-mysql build-brain build-hands build"

install:
	pnpm --dir brain install --frozen-lockfile

typecheck:
	pnpm --dir brain typecheck

test:
	pnpm --dir brain test

test-mysql:
	RUN_MYSQL_INTEGRATION=1 pnpm --dir brain test:mysql

build-brain:
	$(CONTAINER_ENGINE) build --platform linux/amd64 --tag $(BRAIN_IMAGE) --file brain/Dockerfile brain

build-hands-ubuntu:
	$(CONTAINER_ENGINE) build --platform linux/amd64 --build-arg HANDS_OS=ubuntu --tag $(HANDS_UBUNTU_IMAGE) --file hands/Dockerfile hands

build-hands-alpine:
	$(CONTAINER_ENGINE) build --platform linux/amd64 --build-arg HANDS_OS=alpine --tag $(HANDS_ALPINE_IMAGE) --file hands/Dockerfile hands

build-hands: build-hands-ubuntu build-hands-alpine

build: build-brain build-hands
