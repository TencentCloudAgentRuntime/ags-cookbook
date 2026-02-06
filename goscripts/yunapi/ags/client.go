package ags

import (
	"context"
	"encoding/json"
	"fmt"

	ags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	tcerrors "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/errors"
	tchttp "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/http"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	"golang.org/x/time/rate"

	"goscripts/config"
)

const (
	ServiceName = "ags"
	APIVersion  = "2025-09-20"
)

// NewClient 创建 AGS 客户端
func NewClient() (*Client, error) {
	credential := common.NewCredential(
		config.C.TencentCloud.SecretID,
		config.C.TencentCloud.SecretKey,
	)

	cpf := profile.NewClientProfile()
	cpf.HttpProfile.ReqMethod = "POST"

	// 根据配置的 mode 设置不同的 endpoint
	switch config.C.TencentCloud.AGS.Mode {
	case "pre":
		cpf.HttpProfile.Endpoint = "ags.pre.tencentcloudapi.woa.com"
	case "internal":
		cpf.HttpProfile.Endpoint = fmt.Sprintf("ags.%s.tencentcloudapi.woa.com", config.C.TencentCloud.Region)
	default:
		cpf.HttpProfile.Endpoint = "ags.tencentcloudapi.com"
	}

	sdkClient, err := ags.NewClient(credential, config.C.TencentCloud.Region, cpf)
	if err != nil {
		return nil, fmt.Errorf("创建 AGS SDK 客户端失败: %w", err)
	}

	// 初始化通用客户端用于调用未封装的接口
	var commonClient common.Client
	commonClient.Init(config.C.TencentCloud.Region).
		WithCredential(credential).
		WithProfile(cpf)

	return &Client{
		Client:       sdkClient,
		commonClient: &commonClient,
		limiter:      rate.NewLimiter(rate.Limit(5), 5),
	}, nil
}

// CallWithResponse 调用 AGS 接口并解析响应（用于调用 SDK 未封装的接口）
func (c *Client) CallWithResponse(action string, params map[string]any, result any) error {
	err := c.limiter.Wait(context.Background())
	if err != nil {
		return err
	}

	request := tchttp.NewCommonRequest(ServiceName, APIVersion, action)

	paramsBytes, err := json.Marshal(params)
	if err != nil {
		return fmt.Errorf("序列化请求参数失败: %w", err)
	}

	if err := request.SetActionParameters(paramsBytes); err != nil {
		return fmt.Errorf("设置请求参数失败: %w", err)
	}

	response := tchttp.NewCommonResponse()
	if err := c.commonClient.Send(request, response); err != nil {
		return err
	}

	respBytes := response.GetBody()

	// 检查 API 错误
	var commonResp struct {
		Response struct {
			Error *struct {
				Code    string `json:"Code"`
				Message string `json:"Message"`
			} `json:"Error,omitempty"`
			RequestId string `json:"RequestId"`
		} `json:"Response"`
	}

	if err := json.Unmarshal(respBytes, &commonResp); err != nil {
		return fmt.Errorf("解析响应失败: %w", err)
	}

	if commonResp.Response.Error != nil {
		return tcerrors.NewTencentCloudSDKError(
			commonResp.Response.Error.Code,
			commonResp.Response.Error.Message,
			commonResp.Response.RequestId,
		)
	}

	if result != nil {
		if err := json.Unmarshal(respBytes, result); err != nil {
			return fmt.Errorf("解析响应到目标结构体失败: %w", err)
		}
	}

	return nil
}
