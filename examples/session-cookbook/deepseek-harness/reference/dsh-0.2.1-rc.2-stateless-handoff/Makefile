.DEFAULT_GOAL := check

.PHONY: setup check

# The peer dependencies come from the base example's lockfile; this directory is a
# reference plugin, not a separately published package.
setup:
	cd plugin && pnpm install --frozen-lockfile

check:
	node --check plugin/index.js
	node --check plugin/constants.js
	node --check plugin/handoff-controller.js
	node --check plugin/dsh-handoff.js
	node --test plugin/index.test.js plugin/handoff-controller.test.js plugin/dsh-handoff.test.js
