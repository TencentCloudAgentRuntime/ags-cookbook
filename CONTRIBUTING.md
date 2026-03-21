# Contributing Guide

Thanks for contributing to Agent Sandbox Cookbook.

## Before you start

### Recommended local setup

- `uv`
- `python3`
- `go` for Go examples
- `git`

Run:

```bash
make bootstrap
make examples-list
make check
```


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

### README expectations

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

## Commit messages

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
