# DX Improvement Draft

Status: Draft
Scope: Repository-level developer experience (DX) improvements for `ags-cookbook`

## Execution Mandate

This task is not limited to documentation cleanup. The end goal is to complete the work as an owner-like maintainer with enough authorization to drive the repository toward a materially better developer experience.

That means the eventual execution phase should:

- act with high autonomy once execution is explicitly authorized
- prefer solving blocking problems instead of working around them
- test examples for real whenever credentials and environment allow
- record findings continuously to local files so progress is not lost
- use repository evidence, not assumptions, to define the fix plan

This draft therefore covers not only documentation and automation design, but also a full validation-and-repair loop across examples.

## Background

This repository contains many valuable examples and tutorials, but the current developer experience is inconsistent and fragmented. The main problem is not lack of content; it is that documentation, repository structure, commands, and automation are not aligned with the current state of the project.

## Primary DX Audience

The primary audience for DX work in this repository is **AGS users and reference readers**, not repository maintainers.

That includes people who want to:

- discover which example matches their scenario
- prepare the minimum required local environment
- run an example successfully with low friction
- understand the intended AGS usage pattern from working code
- copy or adapt an example into their own project

This changes prioritization. Improvements that reduce friction for first-time AGS users should be treated as more important than maintainer-only conveniences. Repository-maintenance ergonomics still matter, but they are secondary unless they directly improve the user-facing example experience.

## Documentation Layering Principle

Documentation should be split by audience instead of mixing all concerns into the root README.

- Root `README.md` / `README_zh.md` should primarily serve AGS users and example readers
- Repository maintenance rules, authoring conventions, and internal design principles should live in separate maintenance-oriented documents
- Contributor-facing guidance can remain in `CONTRIBUTING.md`, but deeper repository design principles should not crowd the user-facing README

This means future documentation work should avoid turning the root README into an internal process manual.

## Maintainability Delivery Principle

Repository maintainability should be enforced primarily through executable quality gates rather than user-facing prose.

The main carriers for maintainability in this repository should be:

- linters and static checks
- pre-commit hooks
- CI workflows

This keeps the user-facing README focused on AGS users while moving long-term repository quality control into automation. Maintenance guidance can still exist in dedicated documents, but the durable source of truth should be machine-enforced wherever practical.

## Local-First Execution Principle

Executable repository contracts should be established locally before they are promoted into hosted CI.

That means the near-term sequence should be:

1. make the local `make`-based workflows clear and stable
2. ensure users can run those workflows directly on their own machines
3. use those local commands as the source of truth for future automation
4. only then consider mirroring the mature subset into GitHub CI

Heavy CI or end-to-end GitHub-hosted validation should remain deferred until the local command surface is reliable enough to serve as the canonical execution path.

## Current Problems

### 1. Root documentation is outdated

Observed issues:

- Root `README.md` / `README_zh.md` still mention `Python 3.8+`
- Multiple actual Python examples require `Python >= 3.12`
- Root docs still describe `requirements.txt` as the primary dependency model
- Most Python examples have already migrated to `pyproject.toml` + `uv.lock` + `uv run`
- Root docs do not fully reflect the current example set

Examples currently missing from root project overview:

- `examples/custom-image-go-sdk`
- `examples/hybrid-cookbook`
- `examples/osworld-ags`

Impact:

- AGS users may choose the wrong Python version
- AGS users may follow obsolete install steps
- The real repository structure is harder to discover

### 2. Missing repository-level user entrypoint

Current repository top-level experience is fragmented:

- No root `Makefile`, `Taskfile`, or similar unified command entrypoint
- No documented `bootstrap`, `check`, `smoke`, or `docs-check` workflow
- No single place explaining how an AGS user should prepare the environment for first use

Impact:

- Each example behaves like an isolated island
- AGS users must infer how the repository is meant to be used
- Repeated onboarding friction for every new reader who tries a different example

### 3. Environment variable and domain conventions are inconsistent

Observed differences include:

- `tencentags.com`
- `ap-guangzhou.tencentags.com`
- `ap-singapore.tencentags.com`
- `e2b.dev` in some overlay code

Related env variables are also scattered across examples:

- `E2B_API_KEY`
- `E2B_DOMAIN`
- `AGS_TEMPLATE`
- `AGS_TOOL_NAME`
- `AGS_TIMEOUT`
- other example-specific `AGS_*` variables

Impact:

- Users cannot easily tell which variables are global, required, optional, or example-specific
- Cross-example troubleshooting becomes expensive
- Default behavior appears inconsistent

### 4. Quality automation is too weak

Current automation is minimal:

- pre-commit only includes `gitleaks`
- GitHub Actions only runs secret scanning
- No lint, formatting, docs consistency, or smoke validation workflow

Impact:

- Docs can drift without detection
- Examples may silently break
- Contributors lack confidence that changes are safe

### 5. Example command interface is only partially unified

Positives:

- Many examples provide `make run`
- `examples/README.md` already communicates the intent of a unified command interface

Gaps:

- No root-level command to enumerate, validate, or smoke-test examples
- No common `setup` / `smoke` contract
- Some examples still have unique runtime assumptions
- `osworld-ags` has special behavior that is not part of a broader repository contract

Impact:

- The current command model is directionally correct but not yet a real DX foundation

### 6. Documentation is not optimized for first-time AGS users

Missing or underdeveloped repository-level guidance:

- 3–5 minute quick start
- “Which example should I start with?” guide
- environment variable matrix
- common troubleshooting guide
- supported scenario matrix
- stable vs advanced/experimental example classification

Impact:

- The repo is content-rich but navigation-poor
- Newcomers pay unnecessary cognitive cost

### 7. Consistency and maintenance signals are uneven

Observed issues:

- Root structure diagrams do not fully match real files
- Some docs are more up to date than others
- Mixed naming conventions such as `Agents.md` vs repository-level `AGENTS.md`
- License filename is unconventional for tooling expectations

Impact:

- Lowers trust in repository freshness
- Makes maintenance harder over time

### 8. Local reproducibility expectations are not clear enough

Observed environment/tooling reality:

- Many Python examples require Python 3.12
- Local systems may only have Python 3.11 or lower
- Repo docs do not clearly define the recommended interpreter/tool bootstrap path

Impact:

- First-run failure is likely
- Developers may blame individual examples instead of the onboarding flow

## Proposed Direction

## Expanded Delivery Expectations

Before active execution begins, the following expectations are part of scope:

1. Check whether machine-local environment variables and credentials are sufficient to perform full validation work
2. If credentials are sufficient, test examples one by one rather than relying only on static inspection
3. For each example, continue until the test truly reaches a meaningful outcome:
   - success, or
   - a real blocking issue with concrete evidence, or
   - a repaired path that allows the test to proceed
4. Do not intentionally bypass hard problems merely to keep momentum
5. Persist findings for every example in separate local records
6. After the validation round, refine the DX plan using both:
   - the repository audit
   - the real execution experience

## Validation Strategy for Examples

The example validation stage should be treated as first-class input into the DX effort, not as an optional follow-up.

### Stage A: Credential and environment sufficiency check

Before broad execution:

- inspect locally available environment variables and credentials
- determine whether they are sufficient for:
  - Agent Sandbox access
  - region/domain-specific access
  - GitHub or external repository operations where needed
  - any example-specific required services
- classify each example as:
  - executable now
  - executable with local fixes
  - blocked by missing external capability

The goal is to know whether the machine already contains enough authority to complete meaningful end-to-end testing.

### Stage B: Example-by-example real testing

Each example should be tested individually.

For each example:

- create a dedicated local log/report file
- record prerequisites
- record exact commands used
- record whether dependencies install successfully
- record runtime behavior
- record failures, warnings, paper cuts, and confusing steps
- if blocked, attempt to repair the issue instead of skipping immediately
- only conclude “blocked” after a genuine effort to restore progress

### Stage C: Repair while validating

Validation should not be a passive audit. If a failure is encountered, attempt to:

- fix documentation problems that caused the failure
- repair bootstrap scripts or command surfaces
- normalize environment loading
- install missing local dependencies when appropriate
- patch code or config if the example is genuinely broken

The principle is:

- do not hide unresolved problems
- do not fake a pass
- do not mark an example as complete unless the actual test reached a meaningful stopping point

### Stage D: Per-example evidence retention

To avoid loss of context, each example should produce a dedicated local artifact, for example under a repository-local report directory.

Each per-example record should include:

- example name
- test date/time
- environment snapshot relevant to execution
- commands run
- observed output summary
- encountered issues
- fixes attempted
- final status
- DX implications

This evidence then becomes direct input to the final repair plan.

### Phase 0: Fork and branch hygiene

- Ensure work is performed on personal fork
- Keep upstream remote for sync
- Use a dedicated DX branch for changes

### Phase 1: Establish a DX baseline audit

Produce a repository-backed baseline covering:

- outdated docs
- command inconsistencies
- env var inconsistencies
- missing automation
- example health expectations
- machine credential sufficiency for real validation
- per-example execution readiness

### Phase 2: Fix first-contact experience

Prioritize root documentation:

- rewrite root quick start
- align Python version requirements with reality
- document `uv` usage clearly
- add example navigation and selection guidance
- add environment variable overview
- update project structure descriptions

### Phase 3: Add repository-level unified entrypoints

Potential additions:

- root `Makefile` or `justfile`
- `make bootstrap`
- `make examples-list`
- `make check`
- `make smoke`
- `make docs-check`

Goal:

- give AGS users a predictable starting surface

### Phase 4: Normalize example contracts

For each example, aim for a clear and repeatable contract:

- consistent `make run`
- optional `make setup`
- optional `make smoke`
- standardized `.env.example`
- consistent README sections
- explicit prerequisites and stability labeling
- easier diagnosis when required credentials or external resources are missing

### Phase 5: Add lightweight but effective automation

Prefer small, high-value CI additions first:

- docs consistency checks
- markdown/link validation where practical
- Python/Go syntax or lint checks
- lightweight example smoke validation
- stronger pre-commit defaults

### Phase 6: Validate from a zero-context perspective

Before finalizing:

- simulate first-time AGS user onboarding
- verify critical commands and docs
- check English/Chinese documentation consistency
- summarize remaining risks and deferred work
- incorporate lessons learned from actual example execution logs

## Prioritization

Recommended top-three priorities:

1. Fix outdated root documentation
2. Add repository-level developer entrypoints
3. Add minimal automation to prevent future drift

## Expected Outcomes

If executed well, the repository should become:

- easier to onboard into
- easier to navigate
- easier to run locally
- easier to keep accurate without documentation drift
- easier for AGS users to adapt into their own projects

## Open Questions

Questions to settle during execution:

- Should the repository standardize on one recommended domain example in docs, while still permitting region-specific overrides?
- Should root automation be `Makefile`-based, `justfile`-based, or both?
- Which examples are “recommended starters” vs “advanced” vs “external dependency heavy”?
- How much CI is appropriate before it becomes too expensive for a cookbook repository?
- What per-example result taxonomy is most useful: pass / fixed-pass / blocked-external / blocked-bug / docs-gap / design-gap?
- Where should local validation records live so they are useful during execution but do not pollute the long-term repository structure?

## Next-Stage Execution Backlog

### Priority 0: User-path fixes with immediate DX impact

1. Review every example README against a minimum user contract:
   - prerequisites
   - required environment variables
   - one primary run path
   - expected success result
   - common failure hints
2. Add or refine example classification so AGS users can quickly choose where to start:
   - starter
   - advanced
   - heavy / external-dependent
3. Continue removing install paths that can accidentally pollute the user machine, especially where examples still assume global `python` or `pip` usage
4. Ensure README and actual example entrypoints remain aligned after the validation round

### Priority 1: Example contract normalization

1. Keep a light but recognizable contract across examples where it improves user comprehension:
   - `make run` where practical
   - `make setup` where dependency bootstrap is non-trivial
   - clear `.env.example` usage when applicable
2. Allow justified exceptions for externally overlaid or unusually heavy examples rather than forcing fake uniformity
3. Audit remaining examples for hidden assumptions on interpreter names, package managers, or undeclared local tools

### Priority 2: Maintainability via automation

1. Expand `pre-commit` beyond secret scanning with low-cost, high-value checks
2. After local commands are stable, add lightweight CI gates for repository health, especially:
   - Python syntax validation
   - Go build validation
   - docs or metadata consistency checks
3. Add a small repository-level contract check to catch drift across examples
4. Keep maintenance rules in automation and dedicated maintenance-oriented documents, not in the user-facing README

### Priority 3: Defer or treat as follow-up

1. Region/domain unification where real network conditions vary by user environment
2. Deep packaging refactors for externally overlaid examples such as `osworld-ags`
3. Heavy end-to-end GitHub CI that is too costly or too flaky for a cookbook repository

## Notes

This draft is intentionally repository-centric. It focuses on improving developer experience without assuming all examples must become fully testable in CI.

## Permission Probe Findings

Probe date: 2026-03-21
Probe scope: local identity, toolchain, repository permissions, credential presence, and immediate execution readiness

### Confirmed Available Access

- local shell access with broad execution capability
- repository access on personal fork (`guangyouyu/ags-cookbook`)
- GitHub CLI authenticated with admin permission on the fork
- Docker CLI available and daemon accessible
- `uv`, `go`, `make`, `node`, `npm`, `pnpm`, `curl`, `jq`, and `python3` available
- Python 3.12 is available through `uv` even though it is not installed as `python3.12` on PATH
- `E2B_API_KEY` is present and does not appear to be a placeholder
- Tencent Cloud credentials are present:
  - `TENCENTCLOUD_SECRET_ID`
  - `TENCENTCLOUD_SECRET_KEY`
  - `TENCENTCLOUD_REGION`
- CNB credentials are present:
  - `CNB_TOKEN`
  - `CNB_API_ENDPOINT`

### Important Gaps / Risks

- `E2B_DOMAIN` is not globally exported in the shell environment
  - many examples set their own defaults, but the defaults are inconsistent
  - this confirms a repository-level DX issue rather than only a local-machine issue
- system `python` is missing from PATH
  - `python3` exists
  - some scripts or tools may assume `python`
- system default interpreter is Python 3.11.6
  - many examples require Python 3.12
  - however `uv` already has a Python 3.12 interpreter available for use
- the quick CNB endpoint probe returned `404`
  - this does not yet prove the token is invalid
  - it suggests the probed path may be incorrect and should not be treated as a credential failure

### Root / sudo capability

Confirmed during probe:

- `sudo -n true` succeeds
- `sudo -n id` returns `uid=0(root)`
- non-interactive root access is available

Implication:

- system packages, interpreters, and low-level dependencies can be installed or repaired during execution without interactive approval
- environment-level blockers should be treated as solvable unless an external service itself is unavailable

### Implications for Example Validation

Initial conclusion:

- the machine appears sufficiently provisioned to begin real example testing
- the most likely blockers are not missing credentials, but:
  - inconsistent domain defaults
  - Python interpreter assumptions
  - example-specific runtime or documentation drift

Therefore, the later execution phase should proceed under the assumption that full example validation is feasible, while carefully recording:

- which examples truly run as-is
- which ones require local environment normalization
- which ones expose repository-level DX defects
