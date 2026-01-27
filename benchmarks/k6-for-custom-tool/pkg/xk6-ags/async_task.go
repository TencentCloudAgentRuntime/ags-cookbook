package xk6ags

import (
	"fmt"
	"math/rand"
	"sync"
	"sync/atomic"
	"time"

	"github.com/panjf2000/ants/v2"
)

// AsyncTaskResult 通用异步任务结果
type AsyncTaskResult[T any] struct {
	TaskID     string `json:"task_id"`               // 任务标识
	Result     T      `json:"result"`                // 任务结果
	Error      string `json:"error,omitempty"`       // 错误信息
	StartedAt  int64  `json:"started_at"`            // 开始执行时间戳（毫秒）
	EndedAt    int64  `json:"ended_at"`              // 结束时间戳（毫秒）
	DurationMs int64  `json:"duration_ms"`           // 执行耗时（毫秒）
}

// AsyncTaskExecutor 通用异步任务执行器
type AsyncTaskExecutor[T any] struct {
	name         string
	pool         *ants.Pool
	poolOnce     sync.Once
	poolSize     int
	results      []*AsyncTaskResult[T]
	resultsLock  sync.Mutex
	pendingCount int64
}

// NewAsyncTaskExecutor 创建异步任务执行器
func NewAsyncTaskExecutor[T any](name string, poolSize int) *AsyncTaskExecutor[T] {
	if poolSize <= 0 {
		poolSize = 1e5
	}
	return &AsyncTaskExecutor[T]{
		name:     name,
		poolSize: poolSize,
	}
}

// getPool 延迟初始化 goroutine 池
func (e *AsyncTaskExecutor[T]) getPool() *ants.Pool {
	e.poolOnce.Do(func() {
		var err error
		e.pool, err = ants.NewPool(e.poolSize, ants.WithPreAlloc(true))
		if err != nil {
			panic(fmt.Sprintf("failed to create ants pool for %s: %v", e.name, err))
		}
	})
	return e.pool
}

// Submit 提交异步任务
// taskID: 任务标识
// delaySeconds: 延迟执行秒数（支持 ±20% 抖动），0 表示立即执行
// taskFunc: 任务执行函数
func (e *AsyncTaskExecutor[T]) Submit(taskID string, delaySeconds int, taskFunc func() (T, error)) error {
	// 计算随机延迟时间 (±20%)
	var actualDelay float64
	if delaySeconds > 0 {
		jitter := float64(delaySeconds) * 0.2
		actualDelay = float64(delaySeconds) + (rand.Float64()*2-1)*jitter
		if actualDelay < 0 {
			actualDelay = 0
		}
	}

	atomic.AddInt64(&e.pendingCount, 1)

	return e.getPool().Submit(func() {
		if actualDelay > 0 {
			time.Sleep(time.Duration(actualDelay * float64(time.Second)))
		}

		startedAt := time.Now().UnixMilli()
		result, err := taskFunc()
		endedAt := time.Now().UnixMilli()

		taskResult := &AsyncTaskResult[T]{
			TaskID:     taskID,
			Result:     result,
			StartedAt:  startedAt,
			EndedAt:    endedAt,
			DurationMs: endedAt - startedAt,
		}
		if err != nil {
			taskResult.Error = err.Error()
		}

		e.resultsLock.Lock()
		e.results = append(e.results, taskResult)
		e.resultsLock.Unlock()

		atomic.AddInt64(&e.pendingCount, -1)
	})
}

// GetPendingCount 获取待执行的任务数量
func (e *AsyncTaskExecutor[T]) GetPendingCount() int64 {
	return atomic.LoadInt64(&e.pendingCount)
}

// GetResults 获取所有已完成的结果（原子交换，非阻塞）
func (e *AsyncTaskExecutor[T]) GetResults() []*AsyncTaskResult[T] {
	e.resultsLock.Lock()
	defer e.resultsLock.Unlock()
	if len(e.results) == 0 {
		return nil
	}
	results := e.results
	e.results = nil
	return results
}

// Release 释放资源
func (e *AsyncTaskExecutor[T]) Release() {
	if e.pool != nil {
		e.pool.Release()
	}
}

// ============================================
// 全局异步执行器实例
// ============================================

var (
	asyncStopExecutor       *AsyncTaskExecutor[*ControlPlaneResponse]
	asyncStopExecutorOnce   sync.Once
	asyncStressExecutor     *AsyncTaskExecutor[*Shell2HttpResponse]
	asyncStressExecutorOnce sync.Once
)

func getAsyncStopExecutor() *AsyncTaskExecutor[*ControlPlaneResponse] {
	asyncStopExecutorOnce.Do(func() {
		asyncStopExecutor = NewAsyncTaskExecutor[*ControlPlaneResponse]("async-stop", 1e5)
	})
	return asyncStopExecutor
}

func getAsyncStressExecutor() *AsyncTaskExecutor[*Shell2HttpResponse] {
	asyncStressExecutorOnce.Do(func() {
		asyncStressExecutor = NewAsyncTaskExecutor[*Shell2HttpResponse]("async-stress", 1e5)
	})
	return asyncStressExecutor
}
