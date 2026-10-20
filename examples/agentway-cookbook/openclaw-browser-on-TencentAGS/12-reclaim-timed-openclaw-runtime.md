# 12. 限时运行与自动回收（规划，当前版本不支持）

## 版本边界

第 00 章固定使用 Operator 镜像 `v1.0.15-d5afc116` 和源码 `d5afc116883d3ffbf9041b09adda39d640e29eb1` 对应的 CRD。该版本不支持 `Agent.spec.expireAfter`，本章不提供可执行的限时创建或 Timeout 热更新步骤。

不要把未生效的到期字段当作费用或资源回收保障；关闭严格校验也不能让旧 Operator 实现自动回收。

## 当前版本的清理方式

任务完成后，由使用者或自己的调度系统显式删除对应 Agent，并核对 AGS SandboxInstance 和专属 SandboxTool 的清理结果：

```bash
kubectl delete agent <实际的Agent名称> -n <实际的namespace>
```

COS/CFS 中的业务数据按自己的保留策略单独处理。

## 规划示例与恢复条件

[12-timed-openclaw-agent.yaml.txt](./planned-examples/12-timed-openclaw-agent.yaml.txt) 仅供设计参考，请勿 apply。

将本章恢复为操作步骤前，必须：

1. 给出已发布的 Operator 镜像、完整源码 SHA 和配套 CRD，确认 CRD 包含 `expireAfter` 与到期状态字段。
2. 在真实 AGS 环境创建短时 Agent，确认运行态返回的到期时间。
3. 等待到期，确认 SandboxInstance 已停止、Agent CR 和专属 SandboxTool 已回收，且未被 Operator 重新创建。
4. 验证时长变更和异常路径，并确认 COS/CFS 数据保留边界。

本仓库尚未完成这些端到端验证，当前固定版本不承诺自动回收。
