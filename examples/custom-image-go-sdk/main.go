package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"

	sandboxcode "github.com/TencentCloudAgentRuntime/ags-go-sdk/sandbox/code"
	"github.com/joho/godotenv"
	tcags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
)

func main() {
	// 1) 加载本地 .env（如果不存在也不影响，后续从环境变量读取）
	_ = godotenv.Overload(".env")

	// 2) 读取账号密钥（必填）
	secretID := os.Getenv("TENCENTCLOUD_SECRET_ID")
	secretKey := os.Getenv("TENCENTCLOUD_SECRET_KEY")
	if secretID == "" || secretKey == "" {
		log.Fatal("缺少环境变量: TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY")
	}

	// 3) 读取地域与工具名称
	region := os.Getenv("TENCENTCLOUD_REGION")
	if region == "" {
		region = "ap-guangzhou"
	}
	toolName := os.Getenv("AGS_TOOL_NAME")
	if toolName == "" {
		log.Fatal("缺少环境变量: AGS_TOOL_NAME（请填写已创建的自定义工具名称）")
	}

	// 4) 初始化 AGS 控制面客户端
	cred := common.NewCredential(secretID, secretKey)
	cpf := profile.NewClientProfile()
	cpf.HttpProfile.Endpoint = "ags.tencentcloudapi.com"
	client, err := tcags.NewClient(cred, region, cpf)
	if err != nil {
		log.Fatalf("初始化 AGS 客户端失败: %v", err)
	}

	// 5) 构造启动请求
	startReq := &tcags.StartSandboxInstanceRequest{
		ToolName: &toolName,
	}

	// 6) 当 AGS_RUNTIME_IMAGE 非空时，从 .env 读取全部 CustomConfiguration 字段
	//    实现"同一工具，不同镜像/命令/端口/探针配置启动"
	runtimeImage := os.Getenv("AGS_RUNTIME_IMAGE")
	if runtimeImage != "" {
		imageRegistryType := os.Getenv("AGS_RUNTIME_IMAGE_REGISTRY_TYPE")
		if imageRegistryType == "" {
			imageRegistryType = "enterprise"
		}

		customCfg := &tcags.CustomConfiguration{
			Image:             &runtimeImage,
			ImageRegistryType: &imageRegistryType,
		}

		// 启动命令，JSON 字符串数组，如 ["/init"]
		if v := os.Getenv("AGS_CUSTOM_COMMAND"); v != "" {
			customCfg.Command = parseStringSlice(v)
		}

		// 启动参数，JSON 字符串数组，如 ["sleep","infinity"]
		if v := os.Getenv("AGS_CUSTOM_ARGS"); v != "" {
			customCfg.Args = parseStringSlice(v)
		}

		// 端口配置，JSON 数组，如 [{"Name":"http","Protocol":"TCP","Port":80}]
		if v := os.Getenv("AGS_CUSTOM_PORTS"); v != "" {
			customCfg.Ports = parsePorts(v)
		}

		// 探针配置（健康检查）
		if os.Getenv("AGS_PROBE_PATH") != "" {
			customCfg.Probe = parseProbe()
		}

		startReq.CustomConfiguration = customCfg
		log.Printf("启动时覆盖镜像: image=%s, registryType=%s", runtimeImage, imageRegistryType)
	} else {
		log.Printf("未配置 AGS_RUNTIME_IMAGE，使用工具默认镜像")
	}

	// 7) 启动实例
	startResp, err := client.StartSandboxInstanceWithContext(context.Background(), startReq)
	if err != nil {
		log.Fatalf("启动沙箱失败: %v", err)
	}
	if startResp == nil || startResp.Response == nil || startResp.Response.Instance == nil || startResp.Response.Instance.InstanceId == nil {
		log.Fatal("StartSandboxInstance 返回无效")
	}

	instanceID := *startResp.Response.Instance.InstanceId
	log.Printf("启动成功，沙箱: %s", instanceID)

	// 8) 兜底清理：程序退出时自动停止实例，避免资源泄漏
	defer func() {
		_, stopErr := client.StopSandboxInstanceWithContext(context.Background(), &tcags.StopSandboxInstanceRequest{InstanceId: &instanceID})
		if stopErr != nil {
			log.Printf("停止沙箱失败: %v", stopErr)
		} else {
			log.Printf("已停止沙箱: %s", instanceID)
		}
	}()

	// 9) 数据面：连接实例并执行代码
	sbx, err := sandboxcode.Connect(context.Background(), instanceID, sandboxcode.WithClient(client))
	if err != nil {
		log.Fatalf("数据面链接沙箱失败: %v", err)
	}

	execResp, err := sbx.Code.RunCode(context.Background(), "print('hello from hybrid cookbook')", nil, nil)
	if err != nil {
		log.Fatalf("数据面执行代码失败: %v", err)
	}
	fmt.Println("=== 数据面结果 ===")
	for _, line := range execResp.Logs.Stdout {
		fmt.Println(line)
	}
}

// parseStringSlice 解析 JSON 字符串数组环境变量，如 '["a","b"]'，返回 []*string
func parseStringSlice(raw string) []*string {
	var items []string
	if err := json.Unmarshal([]byte(raw), &items); err != nil {
		log.Printf("解析 JSON 字符串数组失败 (%q): %v", raw, err)
		return nil
	}
	ptrs := make([]*string, len(items))
	for i := range items {
		ptrs[i] = &items[i]
	}
	return ptrs
}

// parsePorts 解析端口配置 JSON，如 '[{"Name":"http","Protocol":"TCP","Port":80}]'
func parsePorts(raw string) []*tcags.PortConfiguration {
	var items []struct {
		Name     string `json:"Name"`
		Protocol string `json:"Protocol"`
		Port     int64  `json:"Port"`
	}
	if err := json.Unmarshal([]byte(raw), &items); err != nil {
		log.Printf("解析端口配置失败 (%q): %v", raw, err)
		return nil
	}
	ports := make([]*tcags.PortConfiguration, len(items))
	for i := range items {
		ports[i] = &tcags.PortConfiguration{
			Name:     &items[i].Name,
			Protocol: &items[i].Protocol,
			Port:     &items[i].Port,
		}
	}
	return ports
}

// parseProbe 从 AGS_PROBE_* 环境变量构建探针配置
func parseProbe() *tcags.ProbeConfiguration {
	path := os.Getenv("AGS_PROBE_PATH")
	port := envInt64("AGS_PROBE_PORT", 80)
	scheme := os.Getenv("AGS_PROBE_SCHEME")
	if scheme == "" {
		scheme = "HTTP"
	}

	return &tcags.ProbeConfiguration{
		HttpGet: &tcags.HttpGetAction{
			Path:   &path,
			Port:   &port,
			Scheme: &scheme,
		},
		ReadyTimeoutMs:   envInt64Ptr("AGS_PROBE_READY_TIMEOUT_MS", 30000),
		ProbeTimeoutMs:   envInt64Ptr("AGS_PROBE_TIMEOUT_MS", 1000),
		ProbePeriodMs:    envInt64Ptr("AGS_PROBE_PERIOD_MS", 1000),
		SuccessThreshold: envInt64Ptr("AGS_PROBE_SUCCESS_THRESHOLD", 1),
		FailureThreshold: envInt64Ptr("AGS_PROBE_FAILURE_THRESHOLD", 100),
	}
}

// envInt64 从环境变量读取 int64，缺省时返回 defaultVal
func envInt64(key string, defaultVal int64) int64 {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return defaultVal
	}
	return n
}

// envInt64Ptr 从环境变量读取 *int64，缺省时返回 &defaultVal
func envInt64Ptr(key string, defaultVal int64) *int64 {
	n := envInt64(key, defaultVal)
	return &n
}
