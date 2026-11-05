SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help setup preflight build install run access status verify test check check-config e2e clean

help:
	@printf '%s\n' 'make setup     Install pinned local dependencies' 'make build     Build and push amd64 images' 'make run       Deploy Harness and AWV workspace' 'make access    Show login logs and forward the Web port' 'make test      Run Provider tests without a cluster' 'make check     Typecheck, validate shell/YAML/Helm' 'make e2e       Run the two-round cluster test (overwrites demo files)' 'make clean     Remove compute; retain PVC and Secrets'

setup:
	@command -v pnpm >/dev/null || { echo 'pnpm 11.19.0 is required'; exit 1; }
	pnpm install --frozen-lockfile
	pnpm --dir plugin/dsh-agc install --frozen-lockfile
	pnpm --dir images/worker install --frozen-lockfile --ignore-scripts

preflight:
	node scripts/with-env.mjs ./scripts/preflight.sh

build:
	node scripts/with-env.mjs ./scripts/build-images.sh

install: preflight
	node scripts/with-env.mjs ./scripts/install.sh

run: install
	@printf '%s\n' 'Deployment ready. Run make access in another terminal, keep the login token, and submit examples/prompts/create-pelican.md in Harness.'

access:
	node scripts/with-env.mjs ./scripts/access.sh

status:
	node scripts/with-env.mjs bash -c 'kubectl --kubeconfig "$${KUBECONFIG:?}" -n "$${NAMESPACE:-dsh-awv}" get pod,job,svc,pvc'

verify:
	node scripts/with-env.mjs ./scripts/verify.sh

test:
	pnpm --dir plugin/dsh-agc test

check-config:
	node scripts/check-config.mjs

check: check-config
	pnpm --dir plugin/dsh-agc check
	@for script in scripts/*.sh tests/e2e/*.sh; do bash -n "$$script" || exit; done

e2e:
	node scripts/with-env.mjs ./tests/e2e/run.sh

clean:
	node scripts/with-env.mjs ./scripts/cleanup.sh
