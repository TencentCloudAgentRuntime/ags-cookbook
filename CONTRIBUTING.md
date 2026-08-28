# Contributing Guide

Thanks for contributing to Agent Sandbox Cookbook.

## Before you start

### Recommended local setup

- `uv`
- `python3`
- `go` for Go examples
- `git`

Run the smallest relevant example locally from its own directory, or use the repository root to dispatch a single example:

```bash
make examples-list
make example-setup EXAMPLE=<name>
make example-run EXAMPLE=<name>
```


## Repository guidance map

Use the following public documents by role:

- Example users: `README.md` -> `examples/README.md` -> target example `README.md`
- Contributors: `CONTRIBUTING.md` -> relevant example README / Makefile; use GitHub Issues for larger collaborative work

## Repository boundary

This repository is user-centered first.

- Prefer committing content that directly improves how AGS users discover, run, and understand examples
- Keep project-governance and maintenance-only content to the minimum needed for public collaboration
- Keep execution notes, temporary drafts, and other non-customer-facing working materials in `.local/`
- Keep development and maintenance plumbing in dot-directories when practical (for example `.github/`, `.pre-commit-config.yaml`, `.repo/`) so customer-facing paths stay focused on examples

## Development workflow

1. Fork the repository
2. Clone your fork
3. Add upstream remote
4. Create a feature branch from `main`
5. Make changes
6. Run the smallest relevant example locally
7. Open a Pull Request

Example:

```bash
git clone https://github.com/YOUR_USERNAME/ags-cookbook.git
cd ags-cookbook
git remote add upstream https://github.com/TencentCloudAgentRuntime/ags-cookbook.git
git checkout -b fix/your-change
```

## Example conventions

Each example should aim to provide:

- `README.md`
- `Makefile` with at least `make run`
- `.env.example` when environment variables are required
- isolated dependency management
  - Python: prefer `pyproject.toml` + `uv.lock`
  - Go: `go.mod` / `go.sum`
  - Node.js / TypeScript: `package.json` + `pnpm-lock.yaml`

### README expectations

`README.md` **must be written in English**. A Chinese translation may be provided as `README_zh.md` (or other language variants such as `README_ja.md`), but the primary `README.md` is always English.

Each example README should include:

1. What the example demonstrates
2. Prerequisites
3. Required environment variables
4. Install steps
5. Run command
6. Expected output or artifacts
7. Common failure modes if the example depends on external tools/templates

## Python examples

- Prefer `uv sync` and `uv run ...`
- Keep `requires-python` accurate in `pyproject.toml`
- Use environment variables for secrets
- Add clear logging for long-running or multi-step flows

## Go examples

- Read credentials from `TENCENTCLOUD_*` only
- Keep startup / cleanup behavior explicit

## Node.js / TypeScript examples

- Use `pnpm` as the package manager; commit `pnpm-lock.yaml`
- Use `tsx` to run TypeScript directly — no build step required
- Read credentials from environment variables (`TENCENTCLOUD_*`); use `dotenv` to load `.env`
- Provide `.env.example` with placeholder values only — never commit real secrets

## Commit messages

Commit messages **must be written in English**.

Use semantic prefixes such as:

- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `test:`
- `chore:`

## Pull request quality bar

A good PR should:

- update docs when behavior changes
- keep English and Chinese docs reasonably aligned where relevant
- avoid introducing hidden environment assumptions
- improve, not reduce, local reproducibility
