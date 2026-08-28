// 沙箱监控查询示例 - 使用腾讯云 Go SDK 查询 AGS 沙箱监控指标
//
// 使用前请设置环境变量：
//   export TENCENTCLOUD_SECRET_ID="<你的 SecretId>"
//   export TENCENTCLOUD_SECRET_KEY="<你的 SecretKey>"
//
// 运行：
//   go run main.go --region ap-guangzhou --instance-id xxx

package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	sdkErrors "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/errors"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	monitor "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/monitor/v20180724"
)

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

func createClient(region string) (*monitor.Client, error) {
	cred := common.NewCredential(
		os.Getenv("TENCENTCLOUD_SECRET_ID"),
		os.Getenv("TENCENTCLOUD_SECRET_KEY"),
	)

	cpf := profile.NewClientProfile()
	cpf.SignMethod = "TC3-HMAC-SHA256"
	cpf.HttpProfile.Endpoint = "monitor.tencentcloudapi.com"
	cpf.HttpProfile.ReqMethod = "POST"

	return monitor.NewClient(cred, region, cpf)
}

func querySandboxMetric(client *monitor.Client, instanceID, metricName, startTime, endTime string) (string, error) {
	req := monitor.NewGetMonitorDataRequest()
	req.Namespace = common.StringPtr("QCE/AGS")
	req.MetricName = common.StringPtr(metricName)
	req.Period = common.Uint64Ptr(60)
	req.StartTime = common.StringPtr(startTime)
	req.EndTime = common.StringPtr(endTime)
	req.Instances = []*monitor.Instance{
		{
			Dimensions: []*monitor.Dimension{
				{
					Name:  common.StringPtr("instance_id"),
					Value: common.StringPtr(instanceID),
				},
			},
		},
	}

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
	region := flag.String("region", "ap-guangzhou", "地域")
	instanceID := flag.String("instance-id", "", "沙箱实例 ID (必填)")
	metric := flag.String("metric", "SandboxCpuUsagePercent", "指标名，传 all 查询全部")
	flag.Parse()

	if *instanceID == "" {
		fmt.Fprintf(os.Stderr, "错误: --instance-id 为必填参数\n")
		flag.Usage()
		os.Exit(1)
	}

	now := time.Now()
	start := now.Add(-1 * time.Hour)
	startTime := start.Format("2006-01-02T15:04:05-07:00")
	endTime := now.Format("2006-01-02T15:04:05-07:00")

	fmt.Printf("查询参数:\n")
	fmt.Printf("  Region:      %s\n", *region)
	fmt.Printf("  Instance ID: %s\n", *instanceID)
	fmt.Printf("  Metric:      %s\n", *metric)
	fmt.Printf("  时间范围:    %s ~ %s\n", startTime, endTime)
	fmt.Println("======================================================================")

	client, err := createClient(*region)
	if err != nil {
		fmt.Fprintf(os.Stderr, "创建客户端失败: %v\n", err)
		os.Exit(1)
	}

	var metrics []string
	if strings.ToLower(*metric) == "all" {
		metrics = allMetrics
	} else {
		metrics = []string{*metric}
	}

	for _, m := range metrics {
		result, err := querySandboxMetric(client, *instanceID, m, startTime, endTime)
		if err != nil {
			fmt.Printf("[%s] 查询失败: %v\n", m, err)
		} else {
			var resp map[string]interface{}
			if jsonErr := json.Unmarshal([]byte(result), &resp); jsonErr != nil {
				fmt.Printf("[%s] JSON 解析失败: %v\n", m, jsonErr)
				continue
			}
			output, _ := json.MarshalIndent(resp, "", "  ")
			fmt.Printf("[%s] %s\n", m, string(output))
		}
		time.Sleep(100 * time.Millisecond)
	}
}
