# 沙箱监控查询指南

本文档说明客户如何通过腾讯云云监控标准接口查询 AGS 沙箱实例的运行监控指标。

## 概述

### 职责边界

| 角色 | 职责 |
|---|---|
| 平台侧 | 负责沙箱指标的采集、上报、存储和接入云监控 |
| 客户侧 | 使用腾讯云云监控 `GetMonitorData` 接口查询指标 |

### 基本信息

| 项 | 值 |
|---|---|
| 云 API | `GetMonitorData` |
| API 版本 | `2018-07-24` |
| API 域名 | `monitor.tencentcloudapi.com` |
| Namespace | `QCE/AGS` |
| 推荐 SDK | 腾讯云官方 Python / Go SDK |
| 认证方式 | 腾讯云 SecretId / SecretKey (TC3-HMAC-SHA256 签名) |
| 官方文档 | [GetMonitorData API](https://cloud.tencent.com/document/api/248/31014) |

---

## 查询参数

### 地域 (Region)

监控数据按地域存储，查询时必须指定沙箱实际运行地域。

| 地域 | Region 值 |
|---|---|
| 北京 | `ap-beijing` |
| 上海 | `ap-shanghai` |
| 广州 | `ap-guangzhou` |
| 新加坡 | `ap-singapore` |
| 美东（弗吉尼亚） | `na-ashburn` |

### 查询维度 (Dimensions)

| 维度名 | 必填 | 示例 | 说明 |
|---|:---:|---|---|
| `tool_id` | 是 | `sdt-ggdjgpcl` | 沙箱工具 ID |
| `instance_id` | 是 | `3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs` | 沙箱实例 ID |

`Dimensions` 标准 JSON 格式：

```json
[
  {"Name": "tool_id", "Value": "sdt-ggdjgpcl"},
  {"Name": "instance_id", "Value": "3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs"}
]
```

---

## 监控指标列表

`GetMonitorData` 单次请求只支持一个 `MetricName`。如需查询全部指标，需逐个调用。

| MetricName | 单位 | 说明 |
|---|---|---|
| `SandboxCpuUsagePercent` | `%` | CPU 使用率（多核场景可超 100%，如 2 核满载约 200%） |
| `SandboxCpuUsedCores` | `cores` | CPU 已使用核数 |
| `SandboxMemoryUsagePercent` | `%` | 内存使用率 |
| `SandboxMemoryUsedBytes` | `Bytes` | 内存已使用字节数 |
| `SandboxDiskReadBytesPerSecond` | `Bytes/s` | 磁盘读速率 |
| `SandboxDiskWriteBytesPerSecond` | `Bytes/s` | 磁盘写速率 |
| `SandboxFsUsagePercent` | `%` | 文件系统使用率 |
| `SandboxFsUsedBytes` | `Bytes` | 文件系统已使用字节数 |
| `SandboxNetworkRxBytesPerSecond` | `Bytes/s` | 网络入方向速率 |
| `SandboxNetworkTxBytesPerSecond` | `Bytes/s` | 网络出方向速率 |

---

## 接口说明

### 请求方式

- **协议**：HTTPS
- **方法**：POST
- **域名**：`monitor.tencentcloudapi.com`
- **认证**：TC3-HMAC-SHA256 签名（由 SDK 自动处理）

### 请求体 (Request Body)

```json
{
  "Namespace": "QCE/AGS",
  "MetricName": "SandboxCpuUsagePercent",
  "Instances": [
    {
      "Dimensions": [
        {"Name": "tool_id", "Value": "sdt-ggdjgpcl"},
        {"Name": "instance_id", "Value": "3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs"}
      ]
    }
  ],
  "Period": 60,
  "StartTime": "2026-05-19T14:00:00+08:00",
  "EndTime": "2026-05-19T15:00:00+08:00"
}
```

### 请求字段说明

| 字段 | 必填 | 类型 | 说明 |
|---|:---:|---|---|
| `Namespace` | 是 | String | 固定为 `QCE/AGS` |
| `MetricName` | 是 | String | 指标名，见上方指标列表 |
| `Instances` | 是 | Array | 查询对象数组，单次最多 50 个实例 |
| `Instances[].Dimensions` | 是 | Array | 只传 `tool_id` 和 `instance_id` |
| `Period` | 否 | Integer | 统计周期，单位秒，建议 `60` |
| `StartTime` | 否 | String | ISO 8601 时间，必须带时区（如 `+08:00`） |
| `EndTime` | 否 | String | ISO 8601 时间，必须带时区 |

### 响应体 - 成功且有数据

```json
{
  "Response": {
    "Period": 60,
    "MetricName": "SandboxCpuUsagePercent",
    "DataPoints": [
      {
        "Dimensions": [
          {"Name": "instance_id", "Value": "3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs"},
          {"Name": "tool_id", "Value": "sdt-ggdjgpcl"}
        ],
        "Timestamps": [1747634400, 1747634460, 1747634520],
        "Values": [0.12, 0.08, 0.15]
      }
    ],
    "StartTime": "2026-05-19T14:00:00+08:00",
    "EndTime": "2026-05-19T15:00:00+08:00",
    "Msg": "Success",
    "RequestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

### 响应体 - 成功但无数据

```json
{
  "Response": {
    "Period": 60,
    "MetricName": "SandboxCpuUsagePercent",
    "DataPoints": [
      {
        "Dimensions": [
          {"Name": "instance_id", "Value": "3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs"},
          {"Name": "tool_id", "Value": "sdt-ggdjgpcl"}
        ],
        "Timestamps": [],
        "Values": []
      }
    ],
    "Msg": "Success",
    "RequestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

> 无数据常见原因：沙箱未运行、地域不匹配、时间窗口不对、数据刚产生尚未完成索引（建议等待 1-3 分钟）。

### 响应体 - 错误

```json
{
  "Response": {
    "Error": {
      "Code": "InvalidParameterValue",
      "Message": "invalid MetricName: InvalidMetric"
    },
    "RequestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

常见错误码：

| 错误码 | 说明 | 排查建议 |
|---|---|---|
| `InvalidParameterValue` | 参数取值错误 | 检查 Namespace、MetricName、Dimensions、Region |
| `LimitExceeded.LimitedAccess` | 请求受限/限频 | 降低并发，拆分时间窗口 |
| `FailedOperation.ErrNotOpen` | 服务未开通 | 检查账号服务状态 |
| `FailedOperation.ErrOwed` | 欠费 | 检查账号费用状态 |
| `InternalError` | 内部错误 | 稍后重试，保留 RequestId |

---

## Python SDK 使用

> **环境要求**：Python >= 3.10

### 安装依赖

```bash
pip install tencentcloud-sdk-python-common tencentcloud-sdk-python-monitor
```

### 设置环境变量

```bash
export TENCENTCLOUD_SECRET_ID="<你的 SecretId>"
export TENCENTCLOUD_SECRET_KEY="<你的 SecretKey>"
```

### 完整示例

```python
import json
import os
from datetime import datetime, timedelta

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.monitor.v20180724 import monitor_client, models


def query_sandbox_metric(
    region: str,
    tool_id: str,
    instance_id: str,
    metric_name: str,
    start_time: str = None,
    end_time: str = None,
    period: int = 60,
) -> dict:
    """
    查询沙箱监控指标。

    Args:
        region: 地域，如 "ap-guangzhou"
        tool_id: 沙箱工具 ID，如 "sdt-ggdjgpcl"
        instance_id: 沙箱实例 ID
        metric_name: 指标名，如 "SandboxCpuUsagePercent"
        start_time: 开始时间 (ISO 8601)，默认 1 小时前
        end_time: 结束时间 (ISO 8601)，默认当前时间
        period: 统计周期，单位秒，默认 60

    Returns:
        GetMonitorData 响应字典
    """
    # 构造凭证
    cred = credential.Credential(
        os.environ["TENCENTCLOUD_SECRET_ID"],
        os.environ["TENCENTCLOUD_SECRET_KEY"],
    )

    # 配置客户端
    http_profile = HttpProfile()
    http_profile.endpoint = "monitor.tencentcloudapi.com"
    http_profile.reqMethod = "POST"

    client_profile = ClientProfile()
    client_profile.signMethod = "TC3-HMAC-SHA256"
    client_profile.httpProfile = http_profile

    client = monitor_client.MonitorClient(cred, region, client_profile)

    # 默认时间范围：最近 1 小时
    now = datetime.now().astimezone()
    if not end_time:
        end_time = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        end_time = end_time[:-2] + ":" + end_time[-2:]
    if not start_time:
        start = now - timedelta(hours=1)
        start_time = start.strftime("%Y-%m-%dT%H:%M:%S%z")
        start_time = start_time[:-2] + ":" + start_time[-2:]

    # 构造请求
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


# 使用示例
if __name__ == "__main__":
    try:
        result = query_sandbox_metric(
            region="ap-guangzhou",
            tool_id="sdt-ggdjgpcl",
            instance_id="3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs",
            metric_name="SandboxCpuUsagePercent",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except TencentCloudSDKException as e:
        print(f"查询失败: {e}")
```

### 批量查询所有指标

```python
ALL_METRICS = [
    "SandboxCpuUsagePercent",
    "SandboxCpuUsedCores",
    "SandboxMemoryUsagePercent",
    "SandboxMemoryUsedBytes",
    "SandboxDiskReadBytesPerSecond",
    "SandboxDiskWriteBytesPerSecond",
    "SandboxFsUsagePercent",
    "SandboxFsUsedBytes",
    "SandboxNetworkRxBytesPerSecond",
    "SandboxNetworkTxBytesPerSecond",
]

import time

for metric in ALL_METRICS:
    result = query_sandbox_metric(
        region="ap-guangzhou",
        tool_id="sdt-ggdjgpcl",
        instance_id="3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs",
        metric_name=metric,
    )
    data_points = result.get("DataPoints", [])
    if data_points and data_points[0].get("Values"):
        values = data_points[0]["Values"]
        print(f"{metric}: avg={sum(values)/len(values):.4f}, max={max(values):.4f}, count={len(values)}")
    else:
        print(f"{metric}: no data")
    time.sleep(0.1)  # 避免触发频率限制
```

---

## Golang SDK 使用

### 安装依赖

```bash
go get -u github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common
go get -u github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/monitor
```

### 设置环境变量

```bash
export TENCENTCLOUD_SECRET_ID="<你的 SecretId>"
export TENCENTCLOUD_SECRET_KEY="<你的 SecretKey>"
```

### 完整示例

```go
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	sdkErrors "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/errors"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	monitor "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/monitor/v20180724"
)

func querySandboxMetric(region, toolID, instanceID, metricName string) (string, error) {
	// 构造凭证
	cred := common.NewCredential(
		os.Getenv("TENCENTCLOUD_SECRET_ID"),
		os.Getenv("TENCENTCLOUD_SECRET_KEY"),
	)

	// 配置客户端
	cpf := profile.NewClientProfile()
	cpf.SignMethod = "TC3-HMAC-SHA256"
	cpf.HttpProfile.Endpoint = "monitor.tencentcloudapi.com"
	cpf.HttpProfile.ReqMethod = "POST"

	client, err := monitor.NewClient(cred, region, cpf)
	if err != nil {
		return "", fmt.Errorf("创建客户端失败: %w", err)
	}

	// 构造请求
	now := time.Now()
	start := now.Add(-1 * time.Hour)

	req := monitor.NewGetMonitorDataRequest()
	req.Namespace = common.StringPtr("QCE/AGS")
	req.MetricName = common.StringPtr(metricName)
	req.Period = common.Uint64Ptr(60)
	req.StartTime = common.StringPtr(start.Format("2006-01-02T15:04:05-07:00"))
	req.EndTime = common.StringPtr(now.Format("2006-01-02T15:04:05-07:00"))
	req.Instances = []*monitor.Instance{
		{
			Dimensions: []*monitor.Dimension{
				{
					Name:  common.StringPtr("tool_id"),
					Value: common.StringPtr(toolID),
				},
				{
					Name:  common.StringPtr("instance_id"),
					Value: common.StringPtr(instanceID),
				},
			},
		},
	}

	// 发送请求
	resp, err := client.GetMonitorData(req)
	if _, ok := err.(*sdkErrors.TencentCloudSDKError); ok {
		return "", fmt.Errorf("API 错误: %w", err)
	}
	if err != nil {
		return "", fmt.Errorf("请求失败: %w", err)
	}

	return resp.ToJsonString(), nil
}

func main() {
	region := "ap-guangzhou"
	toolID := "sdt-ggdjgpcl"
	instanceID := "3vixj4szpniara3tu7wyhg35nbr27w4d7223wexs"
	metricName := "SandboxCpuUsagePercent"

	result, err := querySandboxMetric(region, toolID, instanceID, metricName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "查询失败: %v\n", err)
		os.Exit(1)
	}

	// 格式化输出
	var prettyJSON map[string]interface{}
	json.Unmarshal([]byte(result), &prettyJSON)
	output, _ := json.MarshalIndent(prettyJSON, "", "  ")
	fmt.Println(string(output))
}
```

### 批量查询所有指标

在上述 `main.go` 中添加以下代码即可批量查询：

```go
// 全部沙箱监控指标
var allMetrics = []string{
	"SandboxCpuUsagePercent",
	"SandboxCpuUsedCores",
	"SandboxMemoryUsagePercent",
	"SandboxMemoryUsedBytes",
	"SandboxDiskReadBytesPerSecond",
	"SandboxDiskWriteBytesPerSecond",
	"SandboxFsUsagePercent",
	"SandboxFsUsedBytes",
	"SandboxNetworkRxBytesPerSecond",
	"SandboxNetworkTxBytesPerSecond",
}

func queryAllMetrics(region, toolID, instanceID string) {
	for _, metric := range allMetrics {
		result, err := querySandboxMetric(region, toolID, instanceID, metric)
		if err != nil {
			fmt.Printf("[%s] 查询失败: %v\n", metric, err)
		} else {
			fmt.Printf("[%s] %s\n", metric, result)
		}
		time.Sleep(100 * time.Millisecond) // 避免触发频率限制
	}
}
```

---

## 调用限制与建议

| 限制项 | 说明 |
|---|---|
| MetricName | 单次请求只能查询一个指标 |
| Instances | 单次最多查询 50 个实例 |
| 数据点上限 | 单次请求最多返回 7200 个数据点 |
| QPS | 默认有频率限制，批量查询需控制并发 |
| 数据延迟 | 新产生的数据可能有 1-3 分钟延迟 |

---

## 安全建议

- **不要** 将 `SecretId` / `SecretKey` 写入代码仓库、文档或日志
- **推荐** 使用环境变量或密钥管理服务存储凭证
- **建议** 只授予云监控查询所需的最小权限
- 排查问题时提供 `RequestId`，不要暴露明文密钥

---

## 目录结构

```
sandbox-monitor/
├── README.md                          # 本文档
├── examples/
│   ├── python/
│   │   ├── query_single_metric.py     # Python 查询单个指标示例
│   │   ├── query_all_metrics.py       # Python 查询所有指标示例
│   │   └── requirements.txt           # Python 依赖
│   └── golang/
│       ├── main.go                    # Go 查询示例
│       └── go.mod                     # Go 模块定义
└── skill/
    └── sandbox-monitor.md             # Claude Code skill 文件
```
