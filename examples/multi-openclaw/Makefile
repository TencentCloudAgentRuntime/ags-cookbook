.PHONY: setup dev start

setup:
	@test -f .env || (cp .env.example .env && echo "📝 Created .env from .env.example — please edit it with your credentials")
	pnpm install

dev: setup
	pnpm dev

start: setup
	pnpm start
