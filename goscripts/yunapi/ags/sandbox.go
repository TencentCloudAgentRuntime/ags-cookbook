package ags

import (
	"context"
	"fmt"
	"time"

	ags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
)

// ============== 重新导出 SDK 类型（方便使用） ==============

type (
	// 配置类型
	CustomConfiguration   = ags.CustomConfiguration
	NetworkConfiguration  = ags.NetworkConfiguration
	ResourceConfiguration = ags.ResourceConfiguration
	ProbeConfiguration    = ags.ProbeConfiguration
	HttpGetAction         = ags.HttpGetAction

	// 沙箱工具
	CreateSandboxToolRequest        = ags.CreateSandboxToolRequest
	CreateSandboxToolResponse       = ags.CreateSandboxToolResponse
	DeleteSandboxToolRequest        = ags.DeleteSandboxToolRequest
	DeleteSandboxToolResponse       = ags.DeleteSandboxToolResponse
	DescribeSandboxToolListRequest  = ags.DescribeSandboxToolListRequest
	DescribeSandboxToolListResponse = ags.DescribeSandboxToolListResponse
)

// ============== 辅助函数：创建指针 ==============

// String 返回字符串指针
func String(v string) *string {
	return common.StringPtr(v)
}

// Int64 返回 int64 指针
func Int64(v int64) *int64 {
	return common.Int64Ptr(v)
}

// ============== Client 封装 ==============

// Client AGS 客户端封装
type Client struct {
	*ags.Client
	commonClient *common.Client // 用于调用 SDK 未封装的接口
}

// CreateSandboxTool 创建沙箱工具
func (c *Client) CreateSandboxTool(req *CreateSandboxToolRequest) (*CreateSandboxToolResponse, error) {
	return c.Client.CreateSandboxTool(req)
}

// DeleteSandboxTool 删除沙箱工具
func (c *Client) DeleteSandboxTool(req *DeleteSandboxToolRequest) (*DeleteSandboxToolResponse, error) {
	return c.Client.DeleteSandboxTool(req)
}

// DescribeSandboxToolList 查询沙箱工具列表
func (c *Client) DescribeSandboxToolList(req *DescribeSandboxToolListRequest) (*DescribeSandboxToolListResponse, error) {
	return c.Client.DescribeSandboxToolList(req)
}

// ============== 辅助方法 ==============

// SandboxToolStatus 沙箱工具状态常量
const (
	SandboxToolStatusCreating = "CREATING"
	SandboxToolStatusActive   = "ACTIVE"
	SandboxToolStatusDeleting = "DELETING"
	SandboxToolStatusFailed   = "FAILED"
)

// GetToolStatus 查询 Tool 状态
func (c *Client) GetToolStatus(toolID string) (string, error) {
	req := ags.NewDescribeSandboxToolListRequest()
	req.ToolIds = []*string{&toolID}
	req.Limit = Int64(1)

	resp, err := c.DescribeSandboxToolList(req)
	if err != nil {
		return "", err
	}

	if len(resp.Response.SandboxToolSet) == 0 {
		return "", fmt.Errorf("Tool 不存在: %s", toolID)
	}

	return *resp.Response.SandboxToolSet[0].Status, nil
}

// WaitToolActiveOptions 等待 Tool Active 的选项
type WaitToolActiveOptions struct {
	PollInterval time.Duration // 轮询间隔，默认 2s
}

// WaitToolActive 等待 Tool 状态变为 ACTIVE
func (c *Client) WaitToolActive(ctx context.Context, toolID string, opts *WaitToolActiveOptions) error {
	pollInterval := 2 * time.Second
	if opts != nil && opts.PollInterval > 0 {
		pollInterval = opts.PollInterval
	}

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("等待 Tool 就绪被取消: %w", ctx.Err())
		case <-ticker.C:
			status, err := c.GetToolStatus(toolID)
			if err != nil {
				return fmt.Errorf("查询 Tool 状态失败: %w", err)
			}

			switch status {
			case SandboxToolStatusActive:
				return nil
			case SandboxToolStatusCreating:
				continue
			case SandboxToolStatusFailed:
				return fmt.Errorf("Tool 创建失败")
			default:
				return fmt.Errorf("Tool 状态异常: %s", status)
			}
		}
	}
}
