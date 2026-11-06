# Session Cookbook

[中文](./README_zh.md)

This directory demonstrates how to integrate an agent application's conversation persistence with Agent Runtime Session, so the application can load saved conversation history after its running instance is replaced.

Each example stands on its own and walks through configuration, build, verification and cleanup. None of them needs a separate workspace service.

| Integration target | What the example shows |
| --- | --- |
| DeepSeek Harness (DSH) | Connect DSH's conversation persistence to cloud Session, delete the container, then reload the same conversation in a fresh one and keep talking — [deepseek-harness](./deepseek-harness/README.md) |
| pi | Add a pi extension that copies every conversation entry to cloud Session, delete the container, then reopen the same conversation in a fresh one with the official `pi` binary, including `/fork` and `switch_session`; also shows a minimal in-memory variant — [pi](./pi/README.md) |

`make run` prints navigation.


One thing worth saying up front: Session stores your history, but it does not decide who gets to write it. If several instances may take turns on one conversation, pick a handoff reference from the table below; the base examples assume a single writer per conversation.

For scaling, affinity and workspace association, see the [Deployment Cookbook](../deployment-cookbook/README.md). For a split Brain/Hands example that stores conversations and Hands workspace routing in cloud Session, see [brain-hands-session](../deployment-cookbook/brain-hands-session/README.md).

## Choose by framework version and implementation

| Implementation | Use case | Framework changes | Guide |
| --- | --- | --- | --- |
| DSH 0.2.1-rc.2 base persistence | One writer; restore cloud history in a fresh process | No framework source patch | [Setup and runtime](./deepseek-harness/dsh-0.2.1-rc.2/README.md) |
| DSH 0.2.1-rc.2 handoff reference | Completed-turn A → B → A across persistent replicas; rebuild stale memory generations | Independent directory, source patch and image | [Lifecycle, changes and implementation comparison](./deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/README.md) |
| pi 1.4.0 file/RPC | Official pi RPC, local JSONL, fresh-process restoration; one writer | No framework source modification | [Setup and runtime](./pi/README.md) |
| pi 1.4.0 SDK/HTTP reference | Fresh in-memory sessions per request; completed-turn replica handoff | Independent directory/image; SDK HTTP wrapper without framework source changes | [Lifecycle, changes and implementation comparison](./pi/reference/pi-1.4.0-stateless-handoff/README.md) |

Neither reference lets another replica continue a turn that is half-way through, replays tools, or copies workspace files. A turn left unfinished by a crashed replica is closed off automatically once it has shown no activity for a timeout (default 10 minutes). The Session service is unchanged. Build the selected reference directory's image; it does not replace a base example's entry point.
