package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"

	"goscripts/config"
	tuispinner "goscripts/tui/spinner"
	"goscripts/yunapi/ags"
	"goscripts/yunapi/tcr"

	"github.com/google/uuid"
)

// 预热模式
const (
	ModePrecache    = "precache"    // 使用 PreCacheImageTask API
	ModeSandboxTool = "sandboxtool" // 使用 CreateSandboxTool 并等待 Active
)

// Precacher 镜像预热器
type Precacher struct {
	cfg        config.PrecacheConfg
	agsClient  *ags.Client
	tcrClient  *tcr.Client
	spinner    *tuispinner.Manager
	imageRegex *regexp.Regexp

	// 并发控制
	semaphore chan struct{}
	wg        sync.WaitGroup

	// 失败重试队列
	failedQueue []failedTask
	failedMu    sync.Mutex

	// 常量配置
	pollInterval time.Duration
	taskTimeout  time.Duration
}

type failedTask struct {
	imageRef   string
	retryCount int
}

// NewPrecacher 创建预热器实例
func NewPrecacher(cfg config.PrecacheConfg) (*Precacher, error) {
	agsClient, err := ags.NewClient()
	if err != nil {
		return nil, fmt.Errorf("创建 AGS 客户端失败: %w", err)
	}

	tcrClient, err := tcr.NewClient()
	if err != nil {
		return nil, fmt.Errorf("创建 TCR 客户端失败: %w", err)
	}

	var imageRegex *regexp.Regexp
	if cfg.TCRImageRegex != "" {
		imageRegex, err = regexp.Compile(cfg.TCRImageRegex)
		if err != nil {
			return nil, fmt.Errorf("编译镜像正则表达式失败: %w", err)
		}
	}

	concurrency := cfg.Concurrency
	if concurrency <= 0 {
		concurrency = 5
	}

	return &Precacher{
		cfg:          cfg,
		agsClient:    agsClient,
		tcrClient:    tcrClient,
		spinner:      tuispinner.NewManager(),
		imageRegex:   imageRegex,
		semaphore:    make(chan struct{}, concurrency),
		pollInterval: 5 * time.Second,
		taskTimeout:  30 * time.Minute,
	}, nil
}

// Run 执行预热任务
func (p *Precacher) Run(ctx context.Context) error {
	mode := p.cfg.Mode
	if mode == "" {
		mode = ModePrecache
	}

	slog.Info("开始预热任务",
		"mode", mode,
		"registry_id", p.cfg.TCRRegistryID,
		"namespace", p.cfg.TCRNamespace,
		"concurrency", p.cfg.Concurrency,
		"max_retries", p.cfg.MaxRetries,
	)

	// 获取 TCR 实例信息
	registryInfo, err := p.tcrClient.DescribeInstance(ctx, p.cfg.TCRRegistryID)
	if err != nil {
		return fmt.Errorf("获取 TCR 实例信息失败: %w", err)
	}
	registryName := *registryInfo.RegistryName

	// 后台执行预热任务
	go func() {
		defer func() {
			p.wg.Wait()
			slog.Info("所有预热任务完成")
			p.spinner.Quit()
		}()

		// 遍历并预热镜像
		p.processImages(ctx, registryName, mode)

		// 等待首轮完成后处理重试
		p.wg.Wait()
		p.processRetries(ctx, mode)
	}()

	// 启动 TUI（阻塞直到退出）
	return p.spinner.Start()
}

// Shutdown 优雅关闭
func (p *Precacher) Shutdown() {
	p.spinner.Quit()
}

// processImages 遍历并处理所有镜像
func (p *Precacher) processImages(ctx context.Context, registryName, mode string) {
	for repo, err := range p.tcrClient.Repositories(ctx, p.cfg.TCRRegistryID, p.cfg.TCRNamespace) {
		if err != nil {
			slog.Error("遍历镜像仓库失败", "error", err)
			return
		}

		repoName := strings.TrimPrefix(*repo.Name, p.cfg.TCRNamespace+"/")

		for image, err := range p.tcrClient.RepositoryImages(ctx, p.cfg.TCRRegistryID, p.cfg.TCRNamespace, repoName) {
			if err != nil {
				slog.Error("遍历仓库镜像失败", "repo", repoName, "error", err)
				return
			}

			fullImageName := fmt.Sprintf("%s.tencentcloudcr.com/%s/%s:%s",
				registryName, p.cfg.TCRNamespace, repoName, *image.ImageVersion)

			if p.imageRegex != nil && !p.imageRegex.MatchString(fullImageName) {
				continue
			}

			p.submitTask(ctx, fullImageName, mode, 0)
		}
	}
}

// processRetries 处理失败重试
func (p *Precacher) processRetries(ctx context.Context, mode string) {
	maxRetries := p.cfg.MaxRetries
	if maxRetries <= 0 {
		maxRetries = 3
	}

	for round := 1; ; round++ {
		p.failedMu.Lock()
		if len(p.failedQueue) == 0 {
			p.failedMu.Unlock()
			break
		}
		tasks := p.failedQueue
		p.failedQueue = nil
		p.failedMu.Unlock()

		slog.Info("开始重试失败任务", "round", round, "count", len(tasks))

		for _, task := range tasks {
			if task.retryCount >= maxRetries {
				slog.Warn("任务超过最大重试次数", "image", task.imageRef, "retry_count", task.retryCount)
				continue
			}
			p.submitTask(ctx, task.imageRef, mode, task.retryCount+1)
		}

		p.wg.Wait()
	}
}

// submitTask 提交预热任务
func (p *Precacher) submitTask(ctx context.Context, imageRef, mode string, retryCount int) {
	// 先获取信号量，控制并发
	p.semaphore <- struct{}{}

	p.wg.Add(1)

	taskName := imageRef
	if retryCount > 0 {
		taskName = fmt.Sprintf("%s (重试 %d)", imageRef, retryCount)
	}
	p.spinner.AddTask(imageRef, taskName)

	go func() {
		defer func() {
			<-p.semaphore
			p.wg.Done()
		}()

		var err error
		switch mode {
		case ModeSandboxTool:
			err = p.precacheViaSandboxTool(ctx, imageRef)
		default:
			err = p.precacheViaAPI(ctx, imageRef)
		}

		if err != nil {
			slog.Error("预热任务失败", "image", imageRef, "error", err)
			p.spinner.FailTask(imageRef, err.Error())
			p.addFailedTask(imageRef, retryCount)
		} else {
			slog.Info("预热任务成功", "image", imageRef)
			p.spinner.FinishTask(imageRef)
		}
	}()
}

// precacheViaAPI 通过 PreCacheImageTask API 预热
func (p *Precacher) precacheViaAPI(ctx context.Context, imageRef string) error {
	createResp, err := p.agsClient.CreatePreCacheImageTask(&ags.CreatePreCacheImageTaskRequest{
		Image:             imageRef,
		ImageRegistryType: "enterprise",
	})
	if err != nil {
		return fmt.Errorf("创建预热任务失败: %w", err)
	}

	return p.waitPreCacheComplete(ctx,
		createResp.Response.Image,
		createResp.Response.ImageDigest,
		createResp.Response.ImageRegistryType,
	)
}

// waitPreCacheComplete 等待预热任务完成
func (p *Precacher) waitPreCacheComplete(ctx context.Context, imageRef, imageDigest, registryType string) error {
	ctx, cancel := context.WithTimeout(ctx, p.taskTimeout)
	defer cancel()

	ticker := time.NewTicker(p.pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("等待超时: %w", ctx.Err())
		case <-ticker.C:
			resp, err := p.agsClient.DescribePreCacheImageTask(&ags.DescribePreCacheImageTaskRequest{
				Image:             imageRef,
				ImageDigest:       &imageDigest,
				ImageRegistryType: registryType,
			})
			if err != nil {
				continue
			}

			switch resp.Response.Status {
			case "Success":
				return nil
			case "Failed":
				return fmt.Errorf("预热失败: %s", resp.Response.Message)
			}
		}
	}
}

// precacheViaSandboxTool 通过创建 SandboxTool 预热
func (p *Precacher) precacheViaSandboxTool(ctx context.Context, imageRef string) error {
	toolName := fmt.Sprintf("precache-%s", strings.ReplaceAll(uuid.NewString(), "-", ""))

	registryType := p.cfg.ImageRegistryType
	if registryType == "" {
		registryType = "enterprise"
	}

	createResp, err := p.agsClient.CreateSandboxTool(&ags.CreateSandboxToolRequest{
		ToolName: ags.String(toolName),
		ToolType: ags.String("custom"),
		RoleArn:  ags.String(p.cfg.RoleArn),
		NetworkConfiguration: &ags.NetworkConfiguration{
			NetworkMode: ags.String("PUBLIC"),
		},
		CustomConfiguration: &ags.CustomConfiguration{
			Image:             ags.String(imageRef),
			ImageRegistryType: ags.String(registryType),
			Command:           []*string{ags.String("sleep")},
			Resources: &ags.ResourceConfiguration{
				CPU:    ags.String("100m"),
				Memory: ags.String("256Mi"),
			},
			Probe: &ags.ProbeConfiguration{
				HttpGet: &ags.HttpGetAction{
					Path:   ags.String("/"),
					Port:   ags.Int64(80),
					Scheme: ags.String("HTTP"),
				},
				ReadyTimeoutMs:   ags.Int64(30000),
				ProbeTimeoutMs:   ags.Int64(3000),
				ProbePeriodMs:    ags.Int64(10000),
				SuccessThreshold: ags.Int64(1),
				FailureThreshold: ags.Int64(3),
			},
		},
	})
	if err != nil {
		return fmt.Errorf("创建 SandboxTool 失败: %w", err)
	}

	toolID := *createResp.Response.ToolId
	defer p.cleanupTool(toolID)

	waitCtx, cancel := context.WithTimeout(ctx, p.taskTimeout)
	defer cancel()

	return p.agsClient.WaitToolActive(waitCtx, toolID, &ags.WaitToolActiveOptions{
		PollInterval: p.pollInterval,
	})
}

// cleanupTool 清理 SandboxTool
func (p *Precacher) cleanupTool(toolID string) {
	if _, err := p.agsClient.DeleteSandboxTool(&ags.DeleteSandboxToolRequest{
		ToolId: ags.String(toolID),
	}); err != nil {
		slog.Warn("删除 SandboxTool 失败", "tool_id", toolID, "error", err)
	} else {
		slog.Info("删除 SandboxTool 成功", "tool_id", toolID)
	}
}

// addFailedTask 添加失败任务到重试队列
func (p *Precacher) addFailedTask(imageRef string, retryCount int) {
	p.failedMu.Lock()
	defer p.failedMu.Unlock()
	p.failedQueue = append(p.failedQueue, failedTask{
		imageRef:   imageRef,
		retryCount: retryCount,
	})
}

// ============== 程序入口 ==============

var logFile *os.File

func main() {
	config.Init()

	if err := initLogger(); err != nil {
		fmt.Fprintf(os.Stderr, "初始化日志失败: %v\n", err)
		os.Exit(1)
	}
	defer closeLogger()

	precacher, err := NewPrecacher(config.C.Cmd.Precache)
	if err != nil {
		slog.Error("初始化预热器失败", "error", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 监听退出信号
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		slog.Info("收到退出信号，正在停止...")
		precacher.Shutdown()
		cancel()
	}()

	if err := precacher.Run(ctx); err != nil {
		slog.Error("执行失败", "error", err)
		os.Exit(1)
	}
}

func initLogger() error {
	logPath := config.C.Cmd.Precache.LogFile
	if logPath == "" {
		logPath = "precache.log"
	}

	var err error
	logFile, err = os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("打开日志文件失败: %w", err)
	}

	slog.SetDefault(slog.New(slog.NewJSONHandler(logFile, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))
	return nil
}

func closeLogger() {
	if logFile != nil {
		logFile.Close()
	}
}
