package xk6ags

import (
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	ags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
)

// ============================================
// Token 管理
// ============================================

type tokenCache struct {
	token     string
	expiresAt time.Time
}

type tokenManager struct {
	ags   *AGS
	mu    sync.RWMutex
	cache map[string]*tokenCache
}

func newTokenManager(ags *AGS) *tokenManager {
	return &tokenManager{
		ags:   ags,
		cache: make(map[string]*tokenCache),
	}
}

func (tm *tokenManager) getToken(instanceID string) (string, error) {
	tm.mu.RLock()
	if c, ok := tm.cache[instanceID]; ok && time.Now().Add(30*time.Second).Before(c.expiresAt) {
		token := c.token
		tm.mu.RUnlock()
		return token, nil
	}
	tm.mu.RUnlock()

	tm.mu.Lock()
	defer tm.mu.Unlock()

	// double check
	if c, ok := tm.cache[instanceID]; ok && time.Now().Add(30*time.Second).Before(c.expiresAt) {
		return c.token, nil
	}

	request := ags.NewAcquireSandboxInstanceTokenRequest()
	request.InstanceId = &instanceID

	response, err := tm.ags.client.AcquireSandboxInstanceToken(request)
	if err != nil {
		return "", fmt.Errorf("failed to acquire token: %w", err)
	}

	if response.Response == nil || response.Response.Token == nil {
		return "", fmt.Errorf("empty token response")
	}

	token := *response.Response.Token
	expiresAt := time.Now().Add(5 * time.Minute)
	if response.Response.ExpiresAt != nil {
		if t, err := time.Parse(time.RFC3339Nano, *response.Response.ExpiresAt); err == nil {
			expiresAt = t
		}
	}

	tm.cache[instanceID] = &tokenCache{token: token, expiresAt: expiresAt}
	return token, nil
}

// ============================================
// HTTP 请求
// ============================================

// Response HTTP 响应结构
type Response struct {
	Status   int               `json:"status"`
	Body     string            `json:"body"`
	Headers  map[string]string `json:"headers"`
	Error    string            `json:"error,omitempty"`
	RemoteIP string            `json:"remote_ip"`
	TimingMs float64           `json:"timings_ms"`
}

func (m *AGS) buildURL(instanceID, port, path string) (string, error) {
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	rawURL := fmt.Sprintf("https://%s-%s.%s.%s%s", port, instanceID, m.region, m.dataPlaneDomainSuffix, path)
	if _, err := url.Parse(rawURL); err != nil {
		return "", fmt.Errorf("invalid URL: %w", err)
	}
	return rawURL, nil
}

func (m *AGS) doRequest(method, instanceID, port, path, body string, headers map[string]string) *Response {
	return m.doRequestWithTimeout(method, instanceID, port, path, body, headers, 30*time.Second)
}

func (m *AGS) doRequestWithTimeout(method, instanceID, port, path, body string, headers map[string]string, timeout time.Duration) *Response {
	start := time.Now()
	resp := &Response{Headers: make(map[string]string)}

	token, err := m.tokenManager.getToken(instanceID)
	if err != nil {
		resp.Error = err.Error()
		return resp
	}

	fullURL, err := m.buildURL(instanceID, port, path)
	if err != nil {
		resp.Error = err.Error()
		return resp
	}

	var bodyReader io.Reader
	if body != "" {
		bodyReader = strings.NewReader(body)
	}

	req, err := http.NewRequest(method, fullURL, bodyReader)
	if err != nil {
		resp.Error = err.Error()
		return resp
	}

	req.Header.Set("X-Access-Token", token)
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	client := &http.Client{Timeout: timeout}
	httpResp, err := client.Do(req)
	if err != nil {
		resp.Error = err.Error()
		return resp
	}
	defer httpResp.Body.Close() //nolint:errcheck

	resp.Status = httpResp.StatusCode
	resp.TimingMs = float64(time.Since(start).Milliseconds())

	for k, v := range httpResp.Header {
		if len(v) > 0 {
			resp.Headers[k] = v[0]
		}
	}

	bodyBytes, err := io.ReadAll(httpResp.Body)
	if err != nil {
		resp.Error = err.Error()
		return resp
	}
	resp.Body = string(bodyBytes)

	return resp
}

// Get 发送 GET 请求
func (m *AGS) Get(instanceID, port, path string, headers map[string]string) *Response {
	return m.doRequest(http.MethodGet, instanceID, port, path, "", headers)
}

// Post 发送 POST 请求
func (m *AGS) Post(instanceID, port, path, body string, headers map[string]string) *Response {
	return m.doRequest(http.MethodPost, instanceID, port, path, body, headers)
}

// Put 发送 PUT 请求
func (m *AGS) Put(instanceID, port, path, body string, headers map[string]string) *Response {
	return m.doRequest(http.MethodPut, instanceID, port, path, body, headers)
}

// Delete 发送 DELETE 请求
func (m *AGS) Delete(instanceID, port, path string, headers map[string]string) *Response {
	return m.doRequest(http.MethodDelete, instanceID, port, path, "", headers)
}

// Patch 发送 PATCH 请求
func (m *AGS) Patch(instanceID, port, path, body string, headers map[string]string) *Response {
	return m.doRequest(http.MethodPatch, instanceID, port, path, body, headers)
}

// ============================================
// Shell2Http & Stress-ng
// ============================================

// Shell2HttpResponse shell2http API 响应结构
type Shell2HttpResponse struct {
	Success    bool   `json:"success"`
	ExitCode   int    `json:"exit_code"`
	Output     string `json:"output"`
	Error      string `json:"error,omitempty"`
	DurationMs int64  `json:"duration_ms"`
	Timeout    bool   `json:"timeout"`
	TimingMs   int64  `json:"timing_ms"`
}

// ExecShell2Http 通过 shell2http 执行命令
// options 可选参数: env (map[string]any), workdir (string)
func (m *AGS) ExecShell2Http(instanceID, port, command string, timeout int, options ...map[string]any) *Shell2HttpResponse {
	start := time.Now()
	resp := &Shell2HttpResponse{}

	if port == "" {
		port = "8080"
	}

	reqBody := map[string]any{"command": command}
	if timeout > 0 {
		reqBody["timeout"] = timeout
	}

	// 处理可选参数
	if len(options) > 0 && options[0] != nil {
		opts := options[0]
		if env, ok := opts["env"]; ok && env != nil {
			reqBody["env"] = env
		}
		if workdir, ok := opts["workdir"].(string); ok && workdir != "" {
			reqBody["workdir"] = workdir
		}
	}

	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		resp.Error = fmt.Sprintf("failed to marshal request: %v", err)
		resp.TimingMs = time.Since(start).Milliseconds()
		return resp
	}

	// HTTP 超时 = 命令超时 + 30s 余量（网络、启动开销）
	httpTimeout := time.Duration(timeout+30) * time.Second
	if httpTimeout < 60*time.Second {
		httpTimeout = 60 * time.Second
	}

	httpResp := m.doRequestWithTimeout(
		http.MethodPost, instanceID, port, "/exec",
		string(bodyBytes),
		map[string]string{"Content-Type": "application/json"},
		httpTimeout,
	)

	resp.TimingMs = time.Since(start).Milliseconds()

	if httpResp.Error != "" {
		resp.Error = httpResp.Error
		return resp
	}

	if httpResp.Status != http.StatusOK {
		resp.Error = fmt.Sprintf("unexpected status code: %d, body: %s", httpResp.Status, httpResp.Body)
		return resp
	}

	if err := json.Unmarshal([]byte(httpResp.Body), resp); err != nil {
		resp.Error = fmt.Sprintf("failed to parse response: %v, body: %s", err, httpResp.Body)
		return resp
	}

	return resp
}

// StressConfig stress-ng 压测配置
type StressConfig struct {
	CPUWorkers int    `json:"cpu_workers"` // CPU worker 数量
	CPULoad    int    `json:"cpu_load"`    // CPU 负载百分比 (1-100)
	VMWorkers  int    `json:"vm_workers"`  // 内存 worker 数量
	VMBytes    string `json:"vm_bytes"`    // 内存大小，如 "256M"
	IOWorkers  int    `json:"io_workers"`  // IO worker 数量
	Timeout    int    `json:"timeout"`     // 持续时间（秒）
	Jitter     int    `json:"jitter"`      // 数值浮动百分比 (0-100)，默认 20
}

// DefaultStressConfig 默认压测配置
func DefaultStressConfig() *StressConfig {
	return &StressConfig{
		CPUWorkers: 2,
		CPULoad:    50,
		VMWorkers:  1,
		VMBytes:    "128M",
		IOWorkers:  1,
		Timeout:    30,
		Jitter:     20,
	}
}

// applyJitter 对数值应用 ±jitter% 的浮动
func applyJitter(value, jitterPct int) int {
	if jitterPct <= 0 || value <= 0 {
		return value
	}
	jitter := float64(value) * float64(jitterPct) / 100.0
	delta := (rand.Float64()*2 - 1) * jitter
	result := int(float64(value) + delta)
	if result < 1 {
		result = 1
	}
	return result
}

// applyConfigJitter 对配置应用浮动
func applyConfigJitter(cfg *StressConfig) *StressConfig {
	jitter := cfg.Jitter
	return &StressConfig{
		CPUWorkers: applyJitter(cfg.CPUWorkers, jitter),
		CPULoad:    clamp(applyJitter(cfg.CPULoad, jitter), 1, 100),
		VMWorkers:  applyJitter(cfg.VMWorkers, jitter),
		VMBytes:    cfg.VMBytes,
		IOWorkers:  applyJitter(cfg.IOWorkers, jitter),
		Timeout:    applyJitter(cfg.Timeout, jitter),
		Jitter:     0, // 已应用
	}
}

func clamp(v, min, max int) int {
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}

func buildStressNGCommand(cfg *StressConfig) string {
	var args []string
	args = append(args, "stress-ng")

	if cfg.CPUWorkers > 0 {
		args = append(args, fmt.Sprintf("--cpu %d", cfg.CPUWorkers))
		if cfg.CPULoad > 0 && cfg.CPULoad <= 100 {
			args = append(args, fmt.Sprintf("--cpu-load %d", cfg.CPULoad))
		}
	}

	if cfg.VMWorkers > 0 {
		args = append(args, fmt.Sprintf("--vm %d", cfg.VMWorkers))
		if cfg.VMBytes != "" {
			args = append(args, fmt.Sprintf("--vm-bytes %s", cfg.VMBytes))
		}
	}

	if cfg.IOWorkers > 0 {
		args = append(args, fmt.Sprintf("--io %d", cfg.IOWorkers))
	}

	if cfg.Timeout > 0 {
		args = append(args, fmt.Sprintf("--timeout %ds", cfg.Timeout))
	}

	args = append(args, "--metrics-brief")
	return strings.Join(args, " ")
}

func parseStressConfig(config map[string]any) (*StressConfig, error) {
	cfg := DefaultStressConfig()
	if config != nil {
		configBytes, err := json.Marshal(config)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal config: %v", err)
		}
		if err := json.Unmarshal(configBytes, cfg); err != nil {
			return nil, fmt.Errorf("failed to parse config: %v", err)
		}
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 30
	}
	return cfg, nil
}

// GetAsyncStressPendingCount 获取待执行的 stress 任务数量
func (m *AGS) GetAsyncStressPendingCount() int64 {
	return getAsyncStressExecutor().GetPendingCount()
}

// GetAsyncStressResults 获取所有已完成的异步 stress 结果（每轮独立）
func (m *AGS) GetAsyncStressResults() []*AsyncTaskResult[*Shell2HttpResponse] {
	return getAsyncStressExecutor().GetResults()
}

// RunAsyncStress 异步运行多轮 stress-ng 压测，每轮独立返回结果，最后自动 stop 实例
// instanceID: 实例 ID
// port: shell2http 端口（默认 8080）
// delaySeconds: 首轮延迟执行秒数（支持 ±20% 抖动），0 表示立即执行
// configs: 压测配置数组，每个元素 {cpu_workers, cpu_load, vm_workers, vm_bytes, io_workers, timeout, jitter}
//   - 按顺序执行每轮 stress，每轮独立提交结果
//   - nil 或空数组使用默认配置执行一轮
func (m *AGS) RunAsyncStress(instanceID, port string, delaySeconds int, configs []map[string]any) error {
	// 解析所有配置
	var stressConfigs []*StressConfig
	if len(configs) == 0 {
		cfg := applyConfigJitter(DefaultStressConfig())
		stressConfigs = append(stressConfigs, cfg)
	} else {
		for _, config := range configs {
			cfg, err := parseStressConfig(config)
			if err != nil {
				return err
			}
			stressConfigs = append(stressConfigs, applyConfigJitter(cfg))
		}
	}

	stressExecutor := getAsyncStressExecutor()
	stopExecutor := getAsyncStopExecutor()

	// 提交一个任务，内部顺序执行每轮 stress，每轮完成后独立提交结果
	return stressExecutor.Submit(instanceID, delaySeconds, func() (*Shell2HttpResponse, error) {
		var lastResp *Shell2HttpResponse

		for i, cfg := range stressConfigs {
			command := buildStressNGCommand(cfg)
			timeout := cfg.Timeout + 10
			resp := m.ExecShell2Http(instanceID, port, command, timeout)
			lastResp = resp

			// 非最后一轮，独立提交结果
			if i < len(stressConfigs)-1 {
				_ = stressExecutor.Submit(instanceID, 0, func() (*Shell2HttpResponse, error) {
					return resp, nil
				})
			}
		}

		// 所有 stress 完成后提交 stop 任务
		_ = stopExecutor.Submit(instanceID, 0, func() (*ControlPlaneResponse, error) {
			return m.StopSandboxInstance(map[string]any{"InstanceId": instanceID}), nil
		})

		// 返回最后一轮结果
		return lastResp, nil
	})
}
