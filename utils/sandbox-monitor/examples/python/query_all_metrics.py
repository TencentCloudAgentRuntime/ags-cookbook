#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量查询沙箱全部 10 个监控指标示例。

使用前请设置环境变量：
    export TENCENTCLOUD_SECRET_ID="<你的 SecretId>"
    export TENCENTCLOUD_SECRET_KEY="<你的 SecretKey>"

使用方式：
    python query_all_metrics.py --region ap-guangzhou --tool-id sdt-xxx --instance-id xxx
"""
import argparse
import json
import os
import time
from datetime import datetime, timedelta

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.monitor.v20180724 import monitor_client, models


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


def create_monitor_client(region: str) -> monitor_client.MonitorClient:
    """创建云监控客户端。"""
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

    return monitor_client.MonitorClient(cred, region, client_profile)


def query_metric(
    client: monitor_client.MonitorClient,
    tool_id: str,
    instance_id: str,
    metric_name: str,
    start_time: str,
    end_time: str,
    period: int = 60,
) -> dict:
    """查询单个指标。"""
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


def format_iso_time(dt: datetime) -> str:
    """格式化为带时区的 ISO 8601 字符串。"""
    s = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    return s[:-2] + ":" + s[-2:]


def main():
    parser = argparse.ArgumentParser(description="批量查询沙箱全部监控指标")
    parser.add_argument("--region", required=True, help="地域，如 ap-guangzhou")
    parser.add_argument("--tool-id", required=True, help="沙箱工具 ID，如 sdt-0h5n0fil")
    parser.add_argument("--instance-id", required=True, help="沙箱实例 ID")
    args = parser.parse_args()

    REGION = args.region
    TOOL_ID = args.tool_id
    INSTANCE_ID = args.instance_id

    now = datetime.now().astimezone()
    start = now - timedelta(hours=1)
    start_time = format_iso_time(start)
    end_time = format_iso_time(now)

    print(f"查询参数:")
    print(f"  Region:      {REGION}")
    print(f"  Tool ID:     {TOOL_ID}")
    print(f"  Instance ID: {INSTANCE_ID}")
    print(f"  时间范围:    {start_time} ~ {end_time}")
    print(f"  统计周期:    60s")
    print("=" * 70)

    client = create_monitor_client(REGION)

    for metric in ALL_METRICS:
        try:
            result = query_metric(
                client=client,
                tool_id=TOOL_ID,
                instance_id=INSTANCE_ID,
                metric_name=metric,
                start_time=start_time,
                end_time=end_time,
            )

            data_points = result.get("DataPoints", [])
            if data_points and data_points[0].get("Values"):
                values = data_points[0]["Values"]
                avg = sum(values) / len(values)
                mx = max(values)
                print(f"[{metric}] count={len(values)}, avg={avg:.4f}, max={mx:.4f}")
            else:
                print(f"[{metric}] 无数据")

        except TencentCloudSDKException as e:
            print(f"[{metric}] 查询失败: {e}")

        time.sleep(0.1)  # 避免触发频率限制


if __name__ == "__main__":
    main()
