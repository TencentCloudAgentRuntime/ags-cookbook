# Session Cookbook

[中文](./README_zh.md)

How to move a framework's conversation history off local disk and into Agent Runtime Session, so a conversation outlives the process that started it.

Each example stands on its own and walks through configuration, build, verification and cleanup. None of them needs a separate workspace service.

| Framework | What the example shows |
| --- | --- |
| DeepSeek Harness | Connect DSH's conversation persistence to cloud Session, delete the container, then reload the same conversation in a fresh one and keep talking — [deepseek-harness](./deepseek-harness/README.md) |

`make run` prints navigation.

One thing worth saying up front: Session stores your history, but it does not decide who gets to write it. Several instances writing to one conversation, or an in-progress turn that another instance has to carry on, need extra coordination — see [limits of this adapter](./deepseek-harness/README.md#limits-of-this-adapter).

For scaling, affinity and workspace association, see the [Deployment Cookbook](../deployment-cookbook/README.md). The combined Session + workspace scenario lives in [session-workspace](../deployment-cookbook/session-workspace/README.md).
