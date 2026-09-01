.PHONY: setup run dev start

setup:
	@test -f .env || (cp .env.example .env && echo "📝 Created .env from .env.example — please edit it with your credentials")
	pnpm install

run: setup
	pnpm start

dev: setup
	pnpm dev

start: setup
	pnpm start
