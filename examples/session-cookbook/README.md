# Session Cookbook

[中文](./README_zh.md)

This directory demonstrates how to integrate an agent application's conversation persistence with Agent Runtime Session, so the application can load saved conversation history after its running instance is replaced.

Each example stands on its own and walks through configuration, build, verification and cleanup. None of them needs a separate workspace service.

| Integration target | What the example shows |
| --- | --- |
| DeepSeek Harness (DSH) | Connect DSH's conversation persistence to cloud Session, delete the container, then reload the same conversation in a fresh one and keep talking — [deepseek-harness](./deepseek-harness/README.md) |
| pi | Add a pi extension that copies every conversation entry to cloud Session, delete the container, then reopen the same conversation in a fresh one with the official `pi` binary, including `/fork` and `switch_session`; also shows a minimal in-memory variant — [pi](./pi/README.md) |

`make run` prints navigation.

One thing worth saying up front: Session stores your history, but it does not decide who gets to write it. Several instances writing to one conversation, or an in-progress turn that another instance has to carry on, need extra coordination — see [Limits](./deepseek-harness/dsh-0.2.1-rc.2/README.md#8-limits).

For scaling, affinity and workspace association, see the [Deployment Cookbook](../deployment-cookbook/README.md). For a split Brain/Hands example that stores conversations and Hands workspace routing in cloud Session, see [brain-hands-session](../deployment-cookbook/brain-hands-session/README.md).
