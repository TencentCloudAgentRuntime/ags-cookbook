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
    instanceTimeout: config.instanceTimeout || '10m',
    shell2httpPort: config.shell2httpPort || '8080',
    stressDelaySeconds: config.stressDelaySeconds || 10,
    rate: config.qps || 5,
    duration: config.duration || '30m',
    preAllocatedVUs: config.preAllocatedVUs || 30,
    maxVUs: config.maxVUs || 100,
    stressRounds: config.stressRounds || [],
};

// 镜像列表直接从 config 获取
const imageList = config.images || [];
console.log(`Loaded ${imageList.length} images from config`);

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
        'ags_start_success_ratio': ['rate>0.95'],
        'ags_stress_success_ratio': ['rate>0.90'],
        'ags_stop_success_ratio': ['rate>0.95'],
        'ags_start_duration': ['p(95)<20000'],
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
    stress: {
        duration: new Trend('ags_stress_duration', true),
        successRate: new Rate('ags_stress_success_ratio'),
        successCount: new Counter('ags_stress_success'),
        failCount: new Counter('ags_stress_fail'),
        roundCount: new Counter('ags_stress_round_count'),
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

// 处理异步 stress 结果（每轮独立返回 Shell2HttpResponse）
function processAsyncStressResults() {
    const results = ags.getAsyncStressResults();
    for (const r of results) {
        const resp = r.result;
        const instanceId = r.task_id;

        metrics.stress.roundCount.add(1);

        if (!resp) {
            metrics.stress.successRate.add(0);
            metrics.stress.failCount.add(1);
            metrics.errorsByType.add(1, { operation: 'stress', type: 'empty_result' });
            console.log(`[AsyncStress] Empty result for instance: ${instanceId}, error: ${r.error}`);
            continue;
        }

        metrics.stress.duration.add(resp.timing_ms);
        if (resp.success) {
            metrics.stress.successRate.add(1);
            metrics.stress.successCount.add(1);
        } else {
            metrics.stress.successRate.add(0);
            metrics.stress.failCount.add(1);
            const errType = getErrorType(resp.error);
            metrics.errorsByType.add(1, { operation: 'stress', type: errType });
            console.log(`[AsyncStress] Failed: ${instanceId}, error: ${resp.error}`);
        }
    }
    return results.length;
}

// 处理异步 stop 结果
function processAsyncStopResults() {
    const results = ags.getAsyncStopResults();
    for (const r of results) {
        const resp = r.result;
        const instanceId = r.task_id;

        if (!resp) {
            metrics.stop.successRate.add(0);
            metrics.stop.failCount.add(1);
            metrics.errorsByType.add(1, { operation: 'stop', type: 'empty_result' });
            console.log(`[AsyncStop] Empty result for instance: ${instanceId}, error: ${r.error}`);
            continue;
        }

        metrics.stop.duration.add(resp.timing_ms);
        if (resp.success) {
            metrics.stop.successRate.add(1);
            metrics.stop.successCount.add(1);
            console.log(`[AsyncStop] Stopped: ${instanceId}, timing: ${resp.timing_ms}ms`);
        } else {
            metrics.stop.successRate.add(0);
            metrics.stop.failCount.add(1);
            const errType = getErrorType(resp.error);
            metrics.errorsByType.add(1, { operation: 'stop', type: errType });
            console.log(`[AsyncStop] Failed: ${instanceId}, error: ${resp.error}`);
        }
    }
    return results.length;
}

// ============================================================================
// 主函数
// ============================================================================

export default function () {
    if (!CONFIG.toolName) {
        throw new Error('toolName is required in config.js');
    }

    // 1. 启动实例
    const image = getImageForIteration();
    const params = {
        ToolName: CONFIG.toolName,
        Timeout: CONFIG.instanceTimeout,
    };
    if (image) {
        params.CustomConfiguration = { Image: image, ImageRegistryType: 'enterprise' };
    }

    const startResult = ags.startSandboxInstance(params);

    metrics.start.duration.add(startResult.timing_ms);

    if (!startResult.success || !startResult.data?.Instance?.InstanceId) {
        metrics.start.successRate.add(0);
        metrics.start.failCount.add(1);
        const errType = getErrorType(startResult.error);
        metrics.errorsByType.add(1, { operation: 'start', type: errType });
        log(`Start failed: ${startResult.error}, type: ${errType}`);
        processAsyncStressResults();
        return;
    }

    const instanceId = startResult.data.Instance.InstanceId;
    metrics.start.successRate.add(1);
    metrics.start.successCount.add(1);
    log(`Started: ${instanceId}${image ? `, image: ${image}` : ''}, timing: ${startResult.timing_ms}ms`);

    // 2. 提交异步 stress + stop 任务
    const stressConfigs = CONFIG.stressRounds;
    const err = ags.runAsyncStress(
        instanceId,
        CONFIG.shell2httpPort,
        CONFIG.stressDelaySeconds,
        stressConfigs
    );

    if (err) {
        log(`Failed to submit stress task: ${err}`);
        // 如果提交失败，同步 stop
        ags.stopSandboxInstance({ InstanceId: instanceId });
    } else {
        log(`Submitted stress task: ${instanceId}, delay: ${CONFIG.stressDelaySeconds}s, rounds: ${stressConfigs.length}`);
    }

    // 3. 收集已完成的异步结果
    processAsyncStressResults();
    processAsyncStopResults();
}

// ============================================================================
// Teardown: 等待所有异步任务完成
// ============================================================================

export function teardown() {
    console.log(`[Teardown] Waiting for async tasks to complete...`);

    // 等待 stress 和 stop 都完成
    while (ags.getAsyncStressPendingCount() > 0 || ags.getAsyncStopPendingCount() > 0) {
        const stressProcessed = processAsyncStressResults();
        const stopProcessed = processAsyncStopResults();
        if (stressProcessed > 0 || stopProcessed > 0) {
            console.log(`[Teardown] Processed stress: ${stressProcessed}, stop: ${stopProcessed}, pending stress: ${ags.getAsyncStressPendingCount()}, pending stop: ${ags.getAsyncStopPendingCount()}`);
        }
        sleep(1);
    }

    // 最终收集
    const finalStress = processAsyncStressResults();
    const finalStop = processAsyncStopResults();
    if (finalStress > 0 || finalStop > 0) {
        console.log(`[Teardown] Final processed stress: ${finalStress}, stop: ${finalStop}`);
    }

    console.log(`[Teardown] All async tasks completed`);
}
