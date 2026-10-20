# 11. 显式多存储来源（规划，当前版本不支持）

## 版本边界

第 00 章固定使用 Operator 镜像 `v1.0.15-d5afc116` 和源码 `d5afc116883d3ffbf9041b09adda39d640e29eb1` 对应的 CRD。该版本不支持：

- `AgentProfile.spec.storageSources`
- `volumeMounts[].storageSource`、`subPath`、`subPathExpr`
- `AgentProfile.spec.env[].valueFrom` 的 downward API 注入

本章不是可执行部署步骤，不要向当前版本提交这些字段。关闭严格校验会导致字段被剪裁，不能实现预期存储行为。

## 当前版本的做法

使用 Provider 默认 CFS/COS 存储，以及 `volumeMounts[].name/mountPath/subpath`。注意字段为小写 `subpath`：

- 省略时，按 namespace、Agent name、UID 和 mount name 自动隔离。
- 显式填写时，固定到文件系统内指定路径，不再拼接 Provider root；相同路径表示共享目录。

参见[第 01 章](./01-prepare-tencent-agent-runtime.md)、[第 02 章](./02-create-openclaw-browser-agent.md)及 [Hermes 固定路径与删除重建验收](../hermes-dashboard-on-TencentAGS/README.md#验证删除重建后保留数据)。

## 规划示例

未来的显式存储方案拟通过 `storageSources[]` 声明多个 backend，再用挂载项引用来源；静态 `subPath` 表达共享目录，`subPathExpr` 表达按元数据生成的隔离目录。

以下文件仅供设计参考，使用 `.yaml.txt` 扩展名，与可应用清单隔离：

- [多存储来源](./planned-examples/11-01-storage-source-agent-storage.yaml.txt)
- [存储变更 rollout](./planned-examples/11-02-rolling-upgrade-storage-source-rollout.yaml.txt)

恢复为操作指南前，必须绑定实际发布的 Operator 镜像、完整源码 SHA 和配套 CRD，并在真实 AGS/CFS/COS 环境验证挂载来源、共享/隔离目录以及存储变更后的数据可读性。
