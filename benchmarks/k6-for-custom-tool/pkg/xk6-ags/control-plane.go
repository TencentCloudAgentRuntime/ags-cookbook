package xk6ags

import (
	"encoding/json"
	"fmt"
	"time"

	ags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
)

// ControlPlaneResponse 控制面 API 响应结构
type ControlPlaneResponse struct {
	Success   bool           `json:"success"`
	Data      map[string]any `json:"data,omitempty"`
	Error     string         `json:"error,omitempty"`
	RequestID string         `json:"request_id"`
	TimingMs  int64          `json:"timing_ms"`
}

// GetAsyncStopPendingCount 获取待执行的 stop 任务数量
func (m *AGS) GetAsyncStopPendingCount() int64 {
	return getAsyncStopExecutor().GetPendingCount()
}

// GetAsyncStopResults 获取所有已完成的异步 stop 结果
func (m *AGS) GetAsyncStopResults() []*AsyncTaskResult[*ControlPlaneResponse] {
	return getAsyncStopExecutor().GetResults()
}

// StartSandboxInstance 启动沙箱实例
func (m *AGS) StartSandboxInstance(params map[string]any) *ControlPlaneResponse {
	start := time.Now()
	resp := &ControlPlaneResponse{}

	if m.client == nil {
		resp.Error = "client not initialized"
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}

	request := ags.NewStartSandboxInstanceRequest()
	data, err := json.Marshal(params)
	if err != nil {
		resp.Error = fmt.Sprintf("failed to marshal params: %v", err)
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}
	if err := json.Unmarshal(data, request); err != nil {
		resp.Error = fmt.Sprintf("failed to unmarshal to request: %v", err)
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}

	start = time.Now()
	sdkResp, err := m.client.StartSandboxInstance(request)
	resp.TimingMs = time.Since(start).Milliseconds()

	if err != nil {
		resp.Error = err.Error()
		if resp.Error == "" {
			resp.Error = fmt.Sprintf("unknown error: %T", err)
		}
		return resp
	}

	if sdkResp == nil || sdkResp.Response == nil {
		resp.Error = "empty response from API"
		return resp
	}

	if sdkResp.Response.RequestId != nil {
		resp.RequestID = *sdkResp.Response.RequestId
	}

	respData, err := json.Marshal(sdkResp.Response)
	if err != nil {
		resp.Error = fmt.Sprintf("failed to marshal response: %v", err)
		return resp
	}

	var dataMap map[string]any
	if err := json.Unmarshal(respData, &dataMap); err != nil {
		resp.Error = fmt.Sprintf("failed to unmarshal response to map: %v", err)
		return resp
	}

	resp.Success = true
	resp.Data = dataMap
	return resp
}

// StartSandboxInstanceWithAsyncStop 启动沙箱实例，并在指定时间后自动停止（独立于迭代生命周期）
// delaySeconds: 延迟停止的秒数，实际延迟会在 ±20% 范围内随机波动
func (m *AGS) StartSandboxInstanceWithAsyncStop(params map[string]any, delaySeconds int) *ControlPlaneResponse {
	if delaySeconds <= 0 {
		return &ControlPlaneResponse{
			Success: false,
			Error:   "delaySeconds must be greater than 0",
		}
	}

	resp := m.StartSandboxInstance(params)
	if !resp.Success {
		return resp
	}

	// 从响应中获取 InstanceId (路径: Data.Instance.InstanceId)
	instance, ok := resp.Data["Instance"].(map[string]any)
	if !ok {
		return resp
	}
	instanceId, ok := instance["InstanceId"].(string)
	if !ok || instanceId == "" {
		return resp
	}

	// 提交异步停止任务
	err := getAsyncStopExecutor().Submit(instanceId, delaySeconds, func() (*ControlPlaneResponse, error) {
		return m.StopSandboxInstance(map[string]any{"InstanceId": instanceId}), nil
	})

	if err != nil {
		resp.Success = false
		resp.Error = fmt.Sprintf("failed to submit stop task: %v", err)
	}

	return resp
}

// StopSandboxInstance 停止沙箱实例
func (m *AGS) StopSandboxInstance(params map[string]any) *ControlPlaneResponse {
	start := time.Now()
	resp := &ControlPlaneResponse{}

	if m.client == nil {
		resp.Error = "client not initialized"
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}

	request := ags.NewStopSandboxInstanceRequest()
	data, err := json.Marshal(params)
	if err != nil {
		resp.Error = fmt.Sprintf("failed to marshal params: %v", err)
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}
	if err := json.Unmarshal(data, request); err != nil {
		resp.Error = fmt.Sprintf("failed to unmarshal to request: %v", err)
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}

	start = time.Now()
	sdkResp, err := m.client.StopSandboxInstance(request)
	resp.TimingMs = time.Since(start).Milliseconds()

	if err != nil {
		resp.Error = err.Error()
		return resp
	}

	if sdkResp.Response != nil && sdkResp.Response.RequestId != nil {
		resp.RequestID = *sdkResp.Response.RequestId
	}

	respData, err := json.Marshal(sdkResp.Response)
	if err != nil {
		resp.Error = fmt.Sprintf("failed to marshal response: %v", err)
		return resp
	}

	var dataMap map[string]any
	if err := json.Unmarshal(respData, &dataMap); err != nil {
		resp.Error = fmt.Sprintf("failed to unmarshal response to map: %v", err)
		return resp
	}

	resp.Success = true
	resp.Data = dataMap
	return resp
}
