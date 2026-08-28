#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询单个沙箱监控指标示例。

使用前请设置环境变量：
    export TENCENTCLOUD_SECRET_ID="<你的 SecretId>"
    export TENCENTCLOUD_SECRET_KEY="<你的 SecretKey>"

使用方式：
    python query_single_metric.py --region ap-guangzhou --instance-id xxx --metric SandboxCpuUsagePercent
"""
import argparse
import json
import os
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


def query_sandbox_metric(
    region: str,
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
        instance_id: 沙箱实例 ID
        metric_name: 指标名，如 "SandboxCpuUsagePercent"
        start_time: 开始时间 (ISO 8601)，默认 1 小时前
        end_time: 结束时间 (ISO 8601)，默认当前时间
        period: 统计周期，单位秒，默认 60

    Returns:
        GetMonitorData 响应字典
    """
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

    # 默认时间范围：最近 1 小时
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


def main():
    parser = argparse.ArgumentParser(description="查询沙箱监控指标")
    parser.add_argument("--region", required=True, help="地域，如 ap-guangzhou")
    parser.add_argument("--instance-id", required=True, help="沙箱实例 ID")
    parser.add_argument(
        "--metric",
        default="SandboxCpuUsagePercent",
        help="指标名，传 all 查询全部 10 个指标",
    )
    parser.add_argument("--period", type=int, default=60, help="统计周期（秒），默认 60")
    parser.add_argument("--start", default=None, help="开始时间 (ISO 8601)，默认 1 小时前")
    parser.add_argument("--end", default=None, help="结束时间 (ISO 8601)，默认当前时间")
    args = parser.parse_args()

    metrics = ALL_METRICS if args.metric.lower() == "all" else [args.metric]

    try:
        for metric_name in metrics:
            result = query_sandbox_metric(
                region=args.region,
                instance_id=args.instance_id,
                metric_name=metric_name,
                start_time=args.start,
                end_time=args.end,
                period=args.period,
            )

            # 解析数据点
            data_points = result.get("DataPoints", [])
            if data_points and data_points[0].get("Values"):
                values = data_points[0]["Values"]
                print(
                    f"[{metric_name}] count={len(values)}, "
                    f"avg={sum(values)/len(values):.4f}, max={max(values):.4f}"
                )
            else:
                print(f"[{metric_name}] 当前时间范围内无数据")

    except TencentCloudSDKException as e:
        print(f"查询失败: {e}")


if __name__ == "__main__":
    main()
