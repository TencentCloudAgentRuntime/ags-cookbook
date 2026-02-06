import ags from 'k6/x/ags';
import exec from 'k6/execution';
import { Counter, Trend, Rate } from 'k6/metrics';
import { sleep } from 'k6';
import { config } from './config.js';

// ============================================================================
// 配置 (从 config.js 读取)
// ============================================================================

const CONFIG = {
    toolName: config.toolName,
    instanceTimeout: config.instanceTimeout || '5m',
    stopDelaySeconds: config.stopDelaySeconds || 60,
    rate: config.qps || 10,
    duration: config.duration || '30m',
    preAllocatedVUs: config.preAllocatedVUs || 50,
    maxVUs: config.maxVUs || 200,
};

// 镜像列表直接从 config 获取
const imageList = config.images || [];
console.log(`Loaded ${imageList.length} images from config`);

// ============================================================================
// K6 配置
// ============================================================================

export const options = {
    scenarios: {
        load_test: {
            executor: 'constant-arrival-rate',
            rate: CONFIG.rate,
            timeUnit: '1s',
            duration: CONFIG.duration,
            preAllocatedVUs: CONFIG.preAllocatedVUs,
            maxVUs: CONFIG.maxVUs,
        },
    },
    teardownTimeout: '30m',
    thresholds: {
        'ags_start_success_ratio': ['rate>0.99'],
        'ags_stop_success_ratio': ['rate>0.99'],
        'ags_start_duration': ['p(95)<20000'],
        'ags_stop_duration': ['p(95)<5000'],
    },
};

// ============================================================================
// 指标
// ============================================================================

const metrics = {
    start: {
        duration: new Trend('ags_start_duration', true),
        successRate: new Rate('ags_start_success_ratio'),
        successCount: new Counter('ags_start_success'),
        failCount: new Counter('ags_start_fail'),
    },
    stop: {
        duration: new Trend('ags_stop_duration', true),
        successRate: new Rate('ags_stop_success_ratio'),
        successCount: new Counter('ags_stop_success'),
        failCount: new Counter('ags_stop_fail'),
    },
    errorsByType: new Counter('ags_errors_by_type'),
};

// ============================================================================
// 工具函数
// ============================================================================

function log(msg) {
    console.log(`[VU${exec.vu.idInTest}] ${msg}`);
}

// 获取当前迭代应该使用的镜像 (轮流分配，保证每个镜像使用次数基本一致)
function getImageForIteration() {
    if (imageList.length === 0) {
        return null;
    }
    return imageList[(exec.vu.idInTest + exec.vu.iterationInScenario) % imageList.length];
}

const ERROR_PATTERNS = [
    { patterns: ['timeout', 'Timeout'], type: 'timeout' },
    { patterns: ['connection', 'Connection'], type: 'connection' },
    { patterns: ['auth', 'Auth', 'credential'], type: 'auth' },
    { patterns: ['LimitExceeded'], type: 'quota' },
    { patterns: ['rate', 'Rate', 'limit'], type: 'rate_limit' },
    { patterns: ['not found', 'NotFound'], type: 'not_found' },
    { patterns: ['invalid', 'Invalid'], type: 'invalid_param' },
];

function getErrorType(error) {
    if (!error) return 'unknown';
    for (const { patterns, type } of ERROR_PATTERNS) {
        if (patterns.some(p => error.includes(p))) return type;
    }
    return 'other';
}

// 处理异步 stop 结果
function processAsyncStopResults() {
    const results = ags.getAsyncStopResults();
    for (const r of results) {
        const resp = r.result;
        if (!resp) {
            metrics.stop.successRate.add(0);
            metrics.stop.failCount.add(1);
            metrics.errorsByType.add(1, { operation: 'stop', type: 'empty_result' });
            console.log(`[AsyncStop] Empty result for task: ${r.task_id}, error: ${r.error}`);
            continue;
        }
        metrics.stop.duration.add(resp.timing_ms);

        if (resp.success) {
            metrics.stop.successRate.add(1);
            metrics.stop.successCount.add(1);
            console.log(`[AsyncStop] Stopped: ${r.task_id}, timing: ${resp.timing_ms}ms, request_id: ${resp.request_id}`);
        } else {
            metrics.stop.successRate.add(0);
            metrics.stop.failCount.add(1);
            const errType = getErrorType(resp.error);
            metrics.errorsByType.add(1, { operation: 'stop', type: errType });
            console.log(`[AsyncStop] Stop failed: ${r.task_id}, error: ${resp.error}, type: ${errType}, timing: ${resp.timing_ms}ms, request_id: ${resp.request_id}`);
        }
    }
    return results.length;
}

// ============================================================================
// 实例管理
// ============================================================================

function createInstanceWithAsyncStop() {
    const image = getImageForIteration();
    const params = {
        ToolName: CONFIG.toolName,
        Timeout: CONFIG.instanceTimeout,
    };
    if (image) {
        params.CustomConfiguration = { Image: image, ImageRegistryType: 'enterprise' }
    }

    // 异步 stop 独立于迭代，不阻塞测试结束
    const result = ags.startSandboxInstanceWithAsyncStop(params, CONFIG.stopDelaySeconds);

    metrics.start.duration.add(result.timing_ms);

    if (result.success && result.data?.Instance?.InstanceId) {
        const instId = result.data.Instance.InstanceId;
        metrics.start.successRate.add(1);
        metrics.start.successCount.add(1);
        log(`Created: ${instId}${image ? `, image: ${image}` : ''}, timing: ${result.timing_ms}ms, request_id: ${result.request_id}, will stop in ~${CONFIG.stopDelaySeconds}s`);
    } else {
        metrics.start.successRate.add(0);
        metrics.start.failCount.add(1);
        const errType = getErrorType(result.error);
        metrics.errorsByType.add(1, { operation: 'start', type: errType });
        log(`Create failed: ${result.error}, type: ${errType}, timing: ${result.timing_ms}ms, request_id: ${result.request_id}`);
    }

    return result.success;
}

// ============================================================================
// 主函数
// ============================================================================

export default function () {
    if (!CONFIG.toolName) {
        throw new Error('toolName is required in config.js');
    }

    createInstanceWithAsyncStop();

    // 每轮迭代收集已完成的异步 stop 结果
    processAsyncStopResults();
}

// ============================================================================
// Teardown: 收集所有异步 stop 结果
// ============================================================================

export function teardown() {
    console.log(`[Teardown] Waiting for async stop tasks to complete...`);

    // 轮询等待所有 stop 完成并收集结果
    while (ags.getAsyncStopPendingCount() > 0) {
        const processed = processAsyncStopResults();
        if (processed > 0) {
            console.log(`[Teardown] Processed ${processed} stop results, ${ags.getAsyncStopPendingCount()} pending`);
        }
        sleep(1);
    }

    // 最后一次收集
    const finalProcessed = processAsyncStopResults();
    if (finalProcessed > 0) {
        console.log(`[Teardown] Processed final ${finalProcessed} stop results`);
    }

    console.log(`[Teardown] All async stop tasks completed`);
}
