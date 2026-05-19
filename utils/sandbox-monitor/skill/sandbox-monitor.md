# AGS 沙箱监控查询 Skill

当用户需要查询沙箱监控数据时，使用本 skill 帮助完成。

## 能力

本 skill 用于通过腾讯云云监控 `GetMonitorData` 接口查询 AGS 沙箱实例的运行监控指标。

## 前置条件

- 已设置环境变量 `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY`
- 已知沙箱的 `tool_id` 和 `instance_id`
- 已安装 Python 依赖：`pip install tencentcloud-sdk-python-common tencentcloud-sdk-python-monitor`

## 监控指标

共 10 个指标可查询：

| MetricName | 单位 | 说明 |
|---|---|---|
| `SandboxCpuUsagePercent` | % | CPU 使用率 |
| `SandboxCpuUsedCores` | cores | CPU 使用核数 |
| `SandboxMemoryUsagePercent` | % | 内存使用率 |
| `SandboxMemoryUsedBytes` | Bytes | 内存已使用字节数 |
| `SandboxDiskReadBytesPerSecond` | Bytes/s | 磁盘读速率 |
| `SandboxDiskWriteBytesPerSecond` | Bytes/s | 磁盘写速率 |
| `SandboxFsUsagePercent` | % | 文件系统使用率 |
| `SandboxFsUsedBytes` | Bytes | 文件系统已使用字节数 |
| `SandboxNetworkRxBytesPerSecond` | Bytes/s | 网络入速率 |
| `SandboxNetworkTxBytesPerSecond` | Bytes/s | 网络出速率 |

## 查询流程

当用户请求查询沙箱监控指标时，按以下步骤操作：

### 步骤 1：确认参数

向用户确认以下信息（如未提供）：
- **Region**：沙箱运行地域（`ap-beijing` / `ap-shanghai` / `ap-guangzhou` / `ap-singapore` / `na-ashburn`）
- **tool_id**：沙箱工具 ID（如 `sdt-ggdjgpcl`）
- **instance_id**：沙箱实例 ID（如 `3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs`）
- **指标**：要查询的指标名或 `all` 查询全部
- **时间范围**：默认最近 1 小时

### 步骤 2：执行查询

使用以下 Python 脚本查询指标：

```python
import json
import os
from datetime import datetime, timedelta

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.monitor.v20180724 import monitor_client, models


def query_sandbox_metric(region, tool_id, instance_id, metric_name, start_time=None, end_time=None, period=60):
    cred = credential.Credential(
        os.environ["TENCENTCLOUD_SECRET_ID"],
        os.environ["TENCENTCLOUD_SECRET_KEY"],
    )

    http_profile = HttpProfile()
    http_profile.endpoint = "monitor.tencentcloudapi.com"
    http_profile.reqMethod = "POST"

    client_profile = ClientProfile()
    client_profile.signMethod = "TC3-HMAC-SHA256"
    client_profile.httpProfile = http_profile

    client = monitor_client.MonitorClient(cred, region, client_profile)

    now = datetime.now().astimezone()
    if not end_time:
        end_time = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        end_time = end_time[:-2] + ":" + end_time[-2:]
    if not start_time:
        start = now - timedelta(hours=1)
        start_time = start.strftime("%Y-%m-%dT%H:%M:%S%z")
        start_time = start_time[:-2] + ":" + start_time[-2:]

    payload = {
        "Namespace": "QCE/AGS",
        "MetricName": metric_name,
        "Instances": [
            {
                "Dimensions": [
                    {"Name": "tool_id", "Value": tool_id},
                    {"Name": "instance_id", "Value": instance_id},
                ]
            }
        ],
        "Period": period,
        "StartTime": start_time,
        "EndTime": end_time,
    }

    req = models.GetMonitorDataRequest()
    req.from_json_string(json.dumps(payload))
    resp = client.GetMonitorData(req)
    return json.loads(resp.to_json_string())
```

### 步骤 3：解读结果

查询结果中：
- `DataPoints[].Timestamps`：Unix 时间戳数组（秒级）
- `DataPoints[].Values`：对应时间点的指标值数组
- 两者一一对应

向用户展示：
- 数据点数量
- 平均值、最大值、最小值
- 如有异常值（如 CPU 突增），主动指出

### 步骤 4：问题排查

如查询返回空数据，检查：
1. 沙箱是否正在运行
2. Region 是否与沙箱实际运行地域匹配
3. 时间范围是否正确（新数据可能有 1-3 分钟延迟）
4. tool_id 和 instance_id 是否正确

如遇 SDK 异常，参考错误码：
- `InvalidParameterValue`：参数错误，检查 Namespace/MetricName/Dimensions/Region
- `LimitExceeded.LimitedAccess`：限频，降低并发
- `InternalError`：内部错误，稍后重试

## 查询全部指标的快速命令

```bash
export TENCENTCLOUD_SECRET_ID="<SecretId>"
export TENCENTCLOUD_SECRET_KEY="<SecretKey>"

python -c "
import json, os, time
from datetime import datetime, timedelta
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.monitor.v20180724 import monitor_client, models

ALL_METRICS = [
    'SandboxCpuUsagePercent', 'SandboxCpuUsedCores',
    'SandboxMemoryUsagePercent', 'SandboxMemoryUsedBytes',
    'SandboxDiskReadBytesPerSecond', 'SandboxDiskWriteBytesPerSecond',
    'SandboxFsUsagePercent', 'SandboxFsUsedBytes',
    'SandboxNetworkRxBytesPerSecond', 'SandboxNetworkTxBytesPerSecond',
]

cred = credential.Credential(os.environ['TENCENTCLOUD_SECRET_ID'], os.environ['TENCENTCLOUD_SECRET_KEY'])
hp = HttpProfile(); hp.endpoint = 'monitor.tencentcloudapi.com'; hp.reqMethod = 'POST'
cp = ClientProfile(); cp.signMethod = 'TC3-HMAC-SHA256'; cp.httpProfile = hp
client = monitor_client.MonitorClient(cred, 'REGION', cp)

now = datetime.now().astimezone()
start = now - timedelta(hours=1)
fmt = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%S%z')[:-2] + ':' + dt.strftime('%z')[-2:]

for m in ALL_METRICS:
    payload = {'Namespace':'QCE/AGS','MetricName':m,'Instances':[{'Dimensions':[{'Name':'tool_id','Value':'TOOL_ID'},{'Name':'instance_id','Value':'INSTANCE_ID'}]}],'Period':60,'StartTime':fmt(start),'EndTime':fmt(now)}
    req = models.GetMonitorDataRequest(); req.from_json_string(json.dumps(payload))
    resp = json.loads(client.GetMonitorData(req).to_json_string())
    dp = resp.get('DataPoints',[])
    vals = dp[0].get('Values',[]) if dp else []
    if vals: print(f'{m}: avg={sum(vals)/len(vals):.4f}, max={max(vals):.4f}, count={len(vals)}')
    else: print(f'{m}: no data')
    time.sleep(0.1)
"
```

将上面命令中的 `REGION`、`TOOL_ID`、`INSTANCE_ID` 替换为实际值即可。

## 关键参数说明

| 参数 | 说明 | 示例 |
|---|---|---|
| Namespace | 固定值 | `QCE/AGS` |
| Region | 沙箱运行地域 | `ap-guangzhou` |
| Period | 统计周期（秒） | `60` |
| Dimensions | 维度，只传 tool_id 和 instance_id | 见上方示例 |

## 安全注意事项

- 不要将 SecretId/SecretKey 写入代码仓库或日志
- 使用环境变量传递凭证
- 排查问题时只提供 RequestId，不要暴露密钥
