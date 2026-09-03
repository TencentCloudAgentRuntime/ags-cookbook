---
name: cookbook-doc-review
description: >-
  Review AGS Cookbook documentation for language, wording, logic, and Markdown
  layout from an external AGS user's perspective. Use before handing off
  changes to public READMEs, tutorials, reference guides, or example
  documentation anywhere in this repository. Do not use for source-code review
  or explicit contributor/governance documents.
---

# Review AGS Cookbook Documentation

Review only. Do not edit files during the review pass.

## Review Independence

For a final review, use a fresh reviewer context when delegation is available.
Provide the documentation paths, diff boundary, and user's documentation goal,
but not the implementer's intended verdict, suspected findings, proposed
rewrite, or implementation evidence. If a fresh reviewer is unavailable, state
that limitation.

## Core Question

Can a user who has only the public documentation understand the goal, prepare
the prerequisites, run the steps, recognize success or failure, recover from
common problems, and clean up without asking a repository maintainer or
inspecting any other repository file?

Every review decision should help answer this question.

## Audience

Review every public cookbook document as material for people who want to use
AGS. Readers are not expected to maintain this repository, publish its official
artifacts, know its review history, or understand internal implementation
decisions.

This applies to CLI and SDK walkthroughs, Sandbox workflows, storage and
networking guides, browser and mobile examples, custom-image instructions,
Deployment tutorials, API references, and user-facing files under
`dockerfiles/` or `skills/`.

Explicit contributor and agent-governance files such as `CONTRIBUTING.md`,
`AGENTS.md`, and `docs/agents/` are outside this skill.

## Review Scope

Treat the documentation as a black box. Read the changed document in full and
follow only the public documentation links that the reader must follow to
complete the task. Review both the English and translated versions when both
exist.

Do not inspect source code, tests, scripts, Dockerfiles, lockfiles, CI, issues,
pull requests, commits, internal notes, implementation logs, or unrelated
repository files. Do not fill a documentation gap from prior product knowledge.
If the reader needs information that the reviewed documentation does not
provide, report the gap instead of researching the answer elsewhere.

Use four primary review axes.

### 1. Language

- English reads as natural technical English, not a literal translation or an
  internal engineering report.
- Chinese reads as natural technical Chinese, not word-for-word English with
  unnecessary mixed-language filler.
- Grammar, punctuation, tense, person, capitalization, and singular/plural use
  are consistent.
- Terms are introduced before use and remain consistent across headings,
  prose, commands, and translations.
- Proper nouns, commands, flags, API fields, headers, versions, and protocol
  names stay exact.
- English is canonical, while Chinese preserves meaning rather than sentence
  structure.

### 2. Wording

- Sentences are direct, concise, and specific about what the reader should do
  or expect.
- Remove filler, repetition, inflated claims, stacked caveats, and details that
  do not change a user decision.
- Avoid AI- or review-report phrasing such as "this proves", "authoritative
  path", "supported assertion", "comprehensive", or ritual conclusions.
- Distinguish requirements, recommendations, optional diagnostics, examples,
  and observed results without legalistic or contract-heavy prose.
- Do not address readers as repository maintainers. Build or publishing guides
  target resources the reader owns rather than the repository's official
  namespaces and release workflow.
- Preserve necessary warnings, security boundaries, and compatibility limits;
  simplify their expression instead of deleting them for style.

### 3. Logic

- The document moves in the order a reader acts: purpose, prerequisites,
  setup, execution, expected result, recovery, and cleanup where applicable.
- A step does not depend on an undefined term, missing value, hidden command,
  or later explanation.
- The document itself supplies every instruction and decision needed after the
  stated prerequisites; it does not rely on repository knowledge the reader
  cannot see.
- Paragraphs have one clear job. Headings and transitions make the relationship
  between sections obvious.
- Required and optional paths do not interrupt or contradict each other.
- Causes and consequences are stated accurately; observed behavior is not
  promoted into a platform guarantee.
- Repeated explanations are consolidated, and cross-references replace
  unnecessary duplication.
- English and Chinese describe the same sequence, conditions, and outcome.

### 4. Layout

- Heading levels reflect the actual hierarchy and make the main path easy to
  scan.
- Paragraphs are short enough to read comfortably; lists are used for genuine
  sets or sequences, not to fragment ordinary prose.
- Tables are used for comparisons or repeated fields, not as decoration.
- Commands, configuration, expected output, and explanations stay adjacent.
- Code fences, list indentation, blank lines, links, and inline code follow
  valid Markdown and render cleanly.
- Long commands remain copyable. Placeholders are visually clear and explained
  before execution.
- English and translated documents keep matching code, configuration, resource
  names, image references, and machine output.

## Documentation-Only Guardrail

This skill reviews documentation quality and sufficiency, not implementation
correctness. Check internal consistency, command continuity, security guidance,
and whether the documented result follows from the documented steps. Do not use
implementation evidence to rescue unclear or incomplete prose.

Preserve necessary secret-handling, permission, lifecycle, compatibility, and
cleanup guidance. If a factual claim cannot be assessed from the documentation
alone, record it as an unverified residual risk rather than researching other
files.

## Findings

Report only concrete reader-facing problems. For each finding include:

- axis: `Language`, `Wording`, `Logic`, or `Layout`;
- severity and confidence;
- file and line;
- the problematic text or structure;
- how it confuses, slows, misleads, or blocks the reader;
- the missing or conflicting information visible from the documentation;
- the smallest useful correction direction.

One finding may name a secondary axis, but choose one primary axis. Do not
report vague preferences, generic style advice, or differences that are merely
personal taste.

## Output

Return:

1. `Verdict: PASS` or `Verdict: FAIL`.
2. A one-line assessment for each axis: Language, Wording, Logic, and Layout.
3. Findings ordered by severity. Write `No findings` when applicable.
4. Claims that remain unverifiable from the documentation alone, if any.

Use `FAIL` when a material issue remains in any primary axis or when an edit
would make the documentation factually unsafe. Use `PASS` only when the
reviewed path is natural, concise, logically ordered, scannable, and usable
from the documentation alone.
