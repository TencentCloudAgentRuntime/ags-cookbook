---
name: cookbook-doc-review
description: >-
  Review AGS Cookbook documentation from an external AGS user's perspective.
  Use before handing off changes to public READMEs, tutorials, reference
  guides, or example documentation anywhere in this repository. Do not use
  for source-code review or explicit contributor/governance documents.
---

# Review AGS Cookbook Documentation

Review only. Do not edit files during the review pass.

## Review Independence

For a final handoff review, use a fresh reviewer context when delegation is
available. Give the reviewer the repository path, diff boundary, and user's
documentation requirement, but not the implementer's intended verdict,
suspected findings, or proposed rewrite. If a fresh reviewer is unavailable,
state that limitation with the result.

## Audience Contract

Treat the repository's public cookbook surface as documentation for people who
want to use AGS. The reader is not expected to maintain this repository,
publish its official artifacts, know its review history, or understand why a
maintainer chose a particular implementation.

This applies to every public example document: CLI and SDK walkthroughs,
Sandbox workflows, storage and networking guides, browser or mobile examples,
custom-image instructions, Deployment tutorials, API references, and files
under `dockerfiles/` or `skills/`. Specialized guides may contain technical
detail, but they must not turn into instructions for maintaining the
repository's namespaces, official artifacts, release process, lockfiles,
labels, or READMEs.

Explicit contributor and agent-governance files such as `CONTRIBUTING.md`,
`AGENTS.md`, and `docs/agents/` are outside this skill.

## Review Boundary

Review the changed documentation and the shortest linked path a reader needs
to complete the task. Use the repository files, commands, configuration, and
observed behavior as evidence. Do not accept implementation notes or prior
review conclusions as proof that a reader-facing claim is useful or correct.

Identify the subject before applying domain rules. Check CLI behavior against
the relevant CLI contract, SDK behavior against the SDK boundary, and cloud
resource behavior against the corresponding API and lifecycle. Do not carry a
constraint from one cookbook into an unrelated example.

If the requested base or diff boundary is not given, inspect the current
documentation changes without widening the review to unrelated files.

## Reader Test

Read the documentation in order as a new AGS user and check:

1. **Purpose and entry point**
   - The opening says what the example does and when to use it.
   - Required work is separated from optional inspection, rebuilding, and
     troubleshooting.

2. **Runnable path**
   - Prerequisites, credentials, permissions, variables, commands, expected
     results, failure recovery, and cleanup are present where needed.
   - Placeholders tell the reader what to replace.
   - Commands target accounts, resources, paths, and artifact destinations the
     reader controls. For example, image publishing uses the reader's registry
     namespace, never the repository's official namespace.

3. **User-relevant detail**
   - Keep implementation detail only when it changes a user action, expected
     behavior, security boundary, compatibility limit, or troubleshooting
     decision.
   - Remove repository-maintenance chores, investigation narratives, internal
     acceptance language, release bookkeeping, and legal or architectural
     reasoning that the evidence does not support.
   - Do not make readers understand repository revisions, internal validation
     history, artifact provenance, or implementation structure unless they
     must act on that detail.

4. **Plain language**
   - Prefer direct instructions and concrete expected results.
   - Avoid report-like phrases such as "this proves", "authoritative path",
     "supported assertion", or repeated contract disclaimers.
   - Introduce necessary domain terms in context. Preserve exact command, API,
     header, resource, SDK, and protocol names.

5. **Truth and safety**
   - Separate required behavior from optional diagnostics and observed results
     from platform guarantees.
   - Check claims about identity, lifecycle, persistence, concurrency,
     recovery, compatibility, networking, permissions, and billing against the
     contract for the feature being documented. Do not generalize from one
     successful run.
   - Do not expose secrets or encourage tokens in files, command arguments, or
     logs. Cleanup must cover chargeable or long-lived resources created by the
     walkthrough.

6. **Bilingual consistency**
   - English is canonical; Chinese preserves the same behavior and scope.
   - Shell, JSON, configuration, resource names, versions, image references,
     and expected machine output match across languages.
   - Relative links resolve from each document.

## Findings Standard

Report a finding only when it has a concrete reader impact. For each finding,
include:

- severity and confidence;
- file and line;
- the reader action or moment that triggers the problem;
- the likely misunderstanding, failure, or unsafe action;
- repository evidence;
- the smallest useful fix.

Do not report vague preferences, generic style advice, or maintenance concerns
that do not affect an AGS user.

## Output

Return:

1. `Verdict: PASS` or `Verdict: FAIL`.
2. Findings ordered by severity. Write `No findings` when applicable.
3. A short reader-journey assessment covering discovery, execution,
   verification, recovery, and cleanup.
4. Residual risks or unverified external behavior, if any.

Use `FAIL` when a material user-facing problem remains or the documented claim
cannot be supported by available evidence. Use `PASS` only when the reviewed
reader path is usable without repository-maintainer knowledge.
