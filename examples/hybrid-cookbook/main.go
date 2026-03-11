package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	sandboxcode "github.com/TencentCloudAgentRuntime/ags-go-sdk/sandbox/code"
	"github.com/joho/godotenv"
	tcags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
)

func main() {
	_ = godotenv.Load(".env")

	secretID := os.Getenv("TENCENTCLOUD_SECRET_ID")
	secretKey := os.Getenv("TENCENTCLOUD_SECRET_KEY")
	if secretID == "" || secretKey == "" {
		log.Fatal("missing env: TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY")
	}

	region := os.Getenv("TENCENTCLOUD_REGION")
	if region == "" {
		region = "ap-guangzhou"
	}
	toolName := os.Getenv("AGS_TOOL_NAME")
	if toolName == "" {
		toolName = "code-interpreter-v1"
	}
	timeoutMin := 10
	if os.Getenv("AGS_TIMEOUT_MINUTES") != "" {
		_, _ = fmt.Sscanf(os.Getenv("AGS_TIMEOUT_MINUTES"), "%d", &timeoutMin)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	cred := common.NewCredential(secretID, secretKey)
	cpf := profile.NewClientProfile()
	cpf.HttpProfile.Endpoint = "ags.tencentcloudapi.com"
	controlClient, err := tcags.NewClient(cred, region, cpf)
	if err != nil {
		log.Fatalf("init control-plane client failed: %v", err)
	}

	timeoutString := (time.Duration(timeoutMin) * time.Minute).String()
	startResp, err := controlClient.StartSandboxInstanceWithContext(ctx, &tcags.StartSandboxInstanceRequest{
		ToolName: &toolName,
		Timeout:  &timeoutString,
	})
	if err != nil {
		log.Fatalf("control-plane start sbx failed: %v", err)
	}
	if startResp == nil || startResp.Response == nil || startResp.Response.Instance == nil || startResp.Response.Instance.InstanceId == nil {
		log.Fatal("invalid StartSandboxInstance response")
	}
	instanceID := *startResp.Response.Instance.InstanceId
	log.Printf("control-plane created sbx: %s", instanceID)

	defer func() {
		_, stopErr := controlClient.StopSandboxInstanceWithContext(context.Background(), &tcags.StopSandboxInstanceRequest{
			InstanceId: &instanceID,
		})
		if stopErr != nil {
			log.Printf("cleanup stop sbx failed: %v", stopErr)
		}
	}()

	sbx, err := sandboxcode.Connect(ctx, instanceID, sandboxcode.WithClient(controlClient))
	if err != nil {
		log.Fatalf("data-plane connect sbx failed: %v", err)
	}

	execResp, err := sbx.Code.RunCode(ctx, "print('hello from hybrid cookbook')", nil, nil)
	if err != nil {
		log.Fatalf("data-plane run code failed: %v", err)
	}
	fmt.Println("=== Data Plane Result ===")
	for _, line := range execResp.Logs.Stdout {
		fmt.Println(line)
	}

	listResp, err := controlClient.DescribeSandboxInstanceListWithContext(ctx, &tcags.DescribeSandboxInstanceListRequest{})
	if err != nil {
		log.Printf("control-plane describe list failed: %v", err)
		return
	}
	if listResp == nil || listResp.Response == nil {
		log.Printf("invalid DescribeSandboxInstanceList response")
		return
	}
	log.Printf("control-plane visible sbx count: %d", len(listResp.Response.InstanceSet))
}
