package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"time"

	"mvdan.cc/sh/v3/shell"
)

// ExecRequest 执行命令请求
type ExecRequest struct {
	Command string            `json:"command"`           // 要执行的命令
	Timeout int               `json:"timeout"`           // 超时时间（秒），0 表示使用默认值
	Env     map[string]string `json:"env,omitempty"`     // 额外的环境变量
	Workdir string            `json:"workdir,omitempty"` // 工作目录
}

// ExecResponse 执行命令响应
type ExecResponse struct {
	Success  bool   `json:"success"`            // 是否成功
	ExitCode int    `json:"exit_code"`          // 退出码
	Output   string `json:"output"`             // 标准输出和标准错误合并
	Error    string `json:"error,omitempty"`    // 错误信息
	Duration int64  `json:"duration_ms"`        // 执行耗时（毫秒）
	Timeout  bool   `json:"timeout,omitempty"`  // 是否超时
}

// Server HTTP 服务
type Server struct {
	defaultTimeout int // 默认超时时间（秒）
	maxTimeout     int // 最大超时时间（秒）
}

func NewServer() *Server {
	defaultTimeout := 60
	if v := os.Getenv("DEFAULT_TIMEOUT"); v != "" {
		if t, err := strconv.Atoi(v); err == nil && t > 0 {
			defaultTimeout = t
		}
	}

	maxTimeout := 3600
	if v := os.Getenv("MAX_TIMEOUT"); v != "" {
		if t, err := strconv.Atoi(v); err == nil && t > 0 {
			maxTimeout = t
		}
	}

	return &Server{
		defaultTimeout: defaultTimeout,
		maxTimeout:     maxTimeout,
	}
}

// handleHealth 健康检查端点
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{
		"status": "ok",
		"time":   time.Now().Format(time.RFC3339),
	})
}

// handleExec 执行命令端点
func (s *Server) handleExec(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	var req ExecRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(ExecResponse{
			Success: false,
			Error:   "invalid json: " + err.Error(),
		})
		return
	}

	if req.Command == "" {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(ExecResponse{
			Success: false,
			Error:   "command is required",
		})
		return
	}

	// 设置超时时间
	timeout := s.defaultTimeout
	if req.Timeout > 0 {
		timeout = req.Timeout
	}
	if timeout > s.maxTimeout {
		timeout = s.maxTimeout
	}

	// 执行命令
	resp := s.executeCommand(req.Command, req.Env, req.Workdir, timeout)

	w.Header().Set("Content-Type", "application/json")
	if resp.Success {
		w.WriteHeader(http.StatusOK)
	} else {
		w.WriteHeader(http.StatusOK) // 命令执行失败也返回 200，通过 success 字段判断
	}
	json.NewEncoder(w).Encode(resp)
}

// executeCommand 执行命令
func (s *Server) executeCommand(command string, env map[string]string, workdir string, timeoutSec int) ExecResponse {
	start := time.Now()

	// 构建环境变量函数，用于解析命令中的变量
	envFunc := func(name string) string {
		if v, ok := env[name]; ok {
			return v
		}
		return os.Getenv(name)
	}

	// 解析命令行（支持环境变量展开）
	args, err := shell.Fields(command, envFunc)
	if err != nil {
		return ExecResponse{
			Success:  false,
			ExitCode: -1,
			Error:    "failed to parse command: " + err.Error(),
			Duration: time.Since(start).Milliseconds(),
		}
	}
	if len(args) == 0 {
		return ExecResponse{
			Success:  false,
			ExitCode: -1,
			Error:    "empty command",
			Duration: time.Since(start).Milliseconds(),
		}
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSec)*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, args[0], args[1:]...)

	// 设置工作目录
	if workdir != "" {
		if info, err := os.Stat(workdir); err != nil {
			return ExecResponse{
				Success:  false,
				ExitCode: -1,
				Error:    "workdir does not exist: " + workdir,
				Duration: time.Since(start).Milliseconds(),
			}
		} else if !info.IsDir() {
			return ExecResponse{
				Success:  false,
				ExitCode: -1,
				Error:    "workdir is not a directory: " + workdir,
				Duration: time.Since(start).Milliseconds(),
			}
		}
		cmd.Dir = workdir
	}

	// 继承当前环境变量并添加额外的环境变量
	cmd.Env = os.Environ()
	for k, v := range env {
		cmd.Env = append(cmd.Env, k+"="+v)
	}

	// 合并 stdout 和 stderr
	output, err := cmd.CombinedOutput()

	duration := time.Since(start).Milliseconds()

	resp := ExecResponse{
		Output:   string(output),
		Duration: duration,
	}

	if ctx.Err() == context.DeadlineExceeded {
		resp.Success = false
		resp.Timeout = true
		resp.Error = fmt.Sprintf("command timed out after %d seconds", timeoutSec)
		resp.ExitCode = -1
		return resp
	}

	if err != nil {
		resp.Success = false
		resp.Error = err.Error()
		if exitErr, ok := err.(*exec.ExitError); ok {
			resp.ExitCode = exitErr.ExitCode()
		} else {
			resp.ExitCode = -1
		}
		return resp
	}

	resp.Success = true
	resp.ExitCode = 0
	return resp
}

func main() {
	// 检查并添加 nix 环境到 PATH
	nixEnvPath := "/nix/shell2http/nix-env/bin"
	if _, err := os.Stat(nixEnvPath); err == nil {
		currentPath := os.Getenv("PATH")
		if currentPath == "" {
			os.Setenv("PATH", nixEnvPath)
		} else {
			os.Setenv("PATH", nixEnvPath+":"+currentPath)
		}
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	server := NewServer()

	http.HandleFunc("/health", server.handleHealth)
	http.HandleFunc("/exec", server.handleExec)

	addr := ":" + port
	log.Printf("shell2http server starting on port %s...", port)
	log.Printf("  - Default timeout: %ds", server.defaultTimeout)
	log.Printf("  - Max timeout: %ds", server.maxTimeout)
	log.Printf("Endpoints:")
	log.Printf("  GET  /health  - Health check")
	log.Printf("  POST /exec    - Execute shell command")

	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
