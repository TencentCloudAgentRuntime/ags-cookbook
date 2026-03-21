import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import http from 'k6/http';

// Metrics
const sandboxCreateDuration = new Trend('sandbox_create_duration', true);
const sandboxDeleteDuration = new Trend('sandbox_delete_duration', true);
const sandboxLifecycleDuration = new Trend('sandbox_lifecycle_duration', true);
const tokenAcquireDuration = new Trend('token_acquire_duration', true);
const codeExecuteDuration = new Trend('code_execute_duration', true);
const sandboxCreateSuccessRate = new Rate('sandbox_create_success_rate');
const sandboxDeleteSuccessRate = new Rate('sandbox_delete_success_rate');
const tokenAcquireSuccessRate = new Rate('token_acquire_success_rate');
const codeExecuteSuccessRate = new Rate('code_execute_success_rate');
const sandboxCreateCounter = new Counter('sandbox_create_total');
const sandboxDeleteCounter = new Counter('sandbox_delete_total');
const sandboxCreateSuccessCounter = new Counter('sandbox_create_success');
const sandboxDeleteSuccessCounter = new Counter('sandbox_delete_success');
const tokenAcquireCounter = new Counter('token_acquire_total');
const tokenAcquireSuccessCounter = new Counter('token_acquire_success');
const codeExecuteCounter = new Counter('code_execute_total');
const codeExecuteSuccessCounter = new Counter('code_execute_success');

// Test scenario selection
const TEST_SCENARIO = __ENV.TEST_SCENARIO || 'ramping'; // ramping, spike, stress, soak, smoke

// Test configuration - Ramping test (default)
const RAMP_UP_DURATION = __ENV.RAMP_UP_DURATION || '30s';
const TARGET_VUS = parseInt(__ENV.TARGET_VUS) || 5;  // Default for personal quota (max 10 sandboxes)
const STEADY_DURATION = __ENV.STEADY_DURATION || '2m';
const RAMP_DOWN_DURATION = __ENV.RAMP_DOWN_DURATION || '30s';
const GRACEFUL_RAMP_DOWN = __ENV.GRACEFUL_RAMP_DOWN || '30s';

// Spike test configuration
const SPIKE_DURATION = __ENV.SPIKE_DURATION || '30s';
const SPIKE_VUS = parseInt(__ENV.SPIKE_VUS) || 10;  // Default for personal quota (max 10 sandboxes)

// Stress test configuration
const STRESS_STAGES = parseInt(__ENV.STRESS_STAGES) || 3;
const STRESS_STAGE_DURATION = __ENV.STRESS_STAGE_DURATION || '1m';
const STRESS_VUS_STEP = parseInt(__ENV.STRESS_VUS_STEP) || 3;  // Default for personal quota

// Soak test configuration
const SOAK_VUS = parseInt(__ENV.SOAK_VUS) || 5;  // Default for personal quota
const SOAK_DURATION = __ENV.SOAK_DURATION || '10m';

// Smoke test configuration
const SMOKE_VUS = parseInt(__ENV.SMOKE_VUS) || 1;
const SMOKE_DURATION = __ENV.SMOKE_DURATION || '1m';

// Thresholds
const HTTP_REQ_DURATION_P95 = parseInt(__ENV.HTTP_REQ_DURATION_P95) || 5000;
const HTTP_REQ_FAILED_RATE = parseFloat(__ENV.HTTP_REQ_FAILED_RATE) || 0.1;
const CREATE_DURATION_P95 = parseInt(__ENV.CREATE_DURATION_P95) || 10000;
const DELETE_DURATION_P95 = parseInt(__ENV.DELETE_DURATION_P95) || 5000;

// Timeout configuration
const API_TIMEOUT = __ENV.API_TIMEOUT || '30s';
const EXECUTE_TIMEOUT = __ENV.EXECUTE_TIMEOUT || '30s';

// Sleep configuration
const SLEEP_ON_ERROR = parseFloat(__ENV.SLEEP_ON_ERROR) || 1;
const SLEEP_BETWEEN_ITERATIONS = parseFloat(__ENV.SLEEP_BETWEEN_ITERATIONS) || 1.0;
const WAIT_AFTER_CREATE = parseFloat(__ENV.WAIT_AFTER_CREATE) || 0.1;

// Check thresholds
const CREATE_TIMEOUT_THRESHOLD = parseInt(__ENV.CREATE_TIMEOUT_THRESHOLD) || 15000;
const EXECUTE_TIMEOUT_THRESHOLD = parseInt(__ENV.EXECUTE_TIMEOUT_THRESHOLD) || 10000;
const DELETE_TIMEOUT_THRESHOLD = parseInt(__ENV.DELETE_TIMEOUT_THRESHOLD) || 10000;

// API configuration
const API_REGION = __ENV.API_REGION || 'ap-guangzhou';
const E2B_API_KEY = __ENV.E2B_API_KEY;
const USE_INTERNAL = __ENV.USE_INTERNAL === 'true'; // Set to 'true' for Tencent Cloud internal network
const API_GATEWAY_URL = USE_INTERNAL 
  ? `https://api.${API_REGION}.internal.tencentags.com`
  : `https://api.${API_REGION}.tencentags.com`;
const SANDBOX_DOMAIN = USE_INTERNAL 
  ? 'internal.tencentags.com'
  : 'tencentags.com';

// Sandbox configuration
const SANDBOX_TOOL_NAME = __ENV.SANDBOX_TOOL_NAME || 'code-interpreter-v1';
const SANDBOX_PORT = __ENV.SANDBOX_PORT || '49999';
const SANDBOX_TIMEOUT = parseInt(__ENV.SANDBOX_TIMEOUT) || 1000;

// Test code configuration
const TEST_CODE = __ENV.TEST_CODE || 'print("hello world")';
const TEST_LANGUAGE = __ENV.TEST_LANGUAGE || 'python';

// HTTP status
const HTTP_SUCCESS_STATUS = 200;

// Build scenarios based on TEST_SCENARIO
function buildScenarios() {
  const scenarios = {};
  
  switch (TEST_SCENARIO) {
    case 'ramping':
      // Gradual ramp-up test - Good for finding capacity limits
      scenarios.ramping_load = {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
          { duration: RAMP_UP_DURATION, target: TARGET_VUS },
          { duration: STEADY_DURATION, target: TARGET_VUS },
          { duration: RAMP_DOWN_DURATION, target: 0 },
        ],
        gracefulRampDown: GRACEFUL_RAMP_DOWN,
      };
      break;
      
    case 'spike':
      // Sudden spike test - Tests system behavior under sudden traffic surge
      scenarios.spike_test = {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
          { duration: '1m', target: TARGET_VUS },
          { duration: SPIKE_DURATION, target: SPIKE_VUS },
          { duration: '1m', target: TARGET_VUS },
          { duration: '1m', target: 0 },
        ],
        gracefulRampDown: GRACEFUL_RAMP_DOWN,
      };
      break;
      
    case 'stress':
      // Stress test - Gradually increase load to find breaking point
      const stressStages = [];
      for (let i = 1; i <= STRESS_STAGES; i++) {
        stressStages.push({ duration: STRESS_STAGE_DURATION, target: STRESS_VUS_STEP * i });
      }
      stressStages.push({ duration: '2m', target: 0 });
      
      scenarios.stress_test = {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: stressStages,
        gracefulRampDown: GRACEFUL_RAMP_DOWN,
      };
      break;
      
    case 'soak':
      // Soak/endurance test - Sustained load over long period
      scenarios.soak_test = {
        executor: 'constant-vus',
        vus: SOAK_VUS,
        duration: SOAK_DURATION,
      };
      break;
      
    case 'smoke':
      // Smoke test - Minimal load to verify basic functionality
      scenarios.smoke_test = {
        executor: 'constant-vus',
        vus: SMOKE_VUS,
        duration: SMOKE_DURATION,
      };
      break;
      
    case 'breakpoint':
      // Breakpoint test - Keep increasing until system breaks
      scenarios.breakpoint_test = {
        executor: 'ramping-arrival-rate',
        startRate: 1,
        timeUnit: '1s',
        preAllocatedVUs: 10,
        maxVUs: 1000,
        stages: [
          { duration: '2m', target: 10 },
          { duration: '5m', target: 50 },
          { duration: '5m', target: 100 },
          { duration: '5m', target: 200 },
          { duration: '5m', target: 300 },
        ],
      };
      break;
      
    default:
      // Default to ramping test
      scenarios.default_load = {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
          { duration: RAMP_UP_DURATION, target: TARGET_VUS },
          { duration: STEADY_DURATION, target: TARGET_VUS },
          { duration: RAMP_DOWN_DURATION, target: 0 },
        ],
        gracefulRampDown: GRACEFUL_RAMP_DOWN,
      };
  }
  
  return scenarios;
}

export let options = {
  scenarios: buildScenarios(),
  thresholds: {
    http_req_duration: [`p(95)<${HTTP_REQ_DURATION_P95}`],
    http_req_failed: [`rate<${HTTP_REQ_FAILED_RATE}`],
    'sandbox_create_duration': [`p(95)<${CREATE_DURATION_P95}`],
    'sandbox_delete_duration': [`p(95)<${DELETE_DURATION_P95}`],
  },
};

// 冲突计数器
const sandboxCreateConflictCounter = new Counter('sandbox_create_conflict');

function createSandboxInstance() {
  try {
    const payload = JSON.stringify({
      templateID: SANDBOX_TOOL_NAME,
      timeout: SANDBOX_TIMEOUT
    });

    const response = http.post(`${API_GATEWAY_URL}/sandboxes`, payload, {
      headers: {
        'X-API-Key': E2B_API_KEY,
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'k6/benchmark',
        'Connection': 'keep-alive'
      },
      timeout: API_TIMEOUT,
    });

    // Use k6's built-in HTTP timing for accurate measurement
    const duration = response.timings.duration;

    sandboxCreateDuration.add(duration);
    sandboxCreateCounter.add(1);

    // 409 Conflict - 资源冲突，跳过但不算错误
    if (response.status === 409) {
      console.warn(`VU ${__VU}: ⚠️  Create conflict (409), skip this iteration`);
      sandboxCreateSuccessRate.add(false);
      sandboxCreateConflictCounter.add(1);
      
      return {
        success: false,
        skipped: true,
        reason: 'conflict',
        statusCode: 409,
        response: response.body,
        duration: duration
      };
    }

    // 200/201 - 创建成功
    if (response.status === 200 || response.status === 201) {
      const data = JSON.parse(response.body);
      const instanceId = data.sandboxID;
      const token = data.envdAccessToken;

      sandboxCreateSuccessRate.add(true);
      sandboxCreateSuccessCounter.add(1);

      console.log(`VU ${__VU}: Created successfully, InstanceId: ${instanceId}`);

      return {
        success: true,
        instanceId: instanceId,
        token: token,
        response: data,
        duration: duration
      };
    } else {
      sandboxCreateSuccessRate.add(false);
      console.error(`VU ${__VU}: Create failed - HTTP ${response.status}, Response: ${response.body}`);
      return {
        success: false,
        error: `HTTP error: ${response.status}`,
        duration: duration
      };
    }
  } catch (error) {
    sandboxCreateSuccessRate.add(false);
    
    console.error(`VU ${__VU}: Create exception: ${error.message}`);
    
    return {
      success: false,
      error: error.message,
      duration: 0
    };
  }
}

function acquireSandboxToken(instanceId) {
  // Token is already acquired during creation, return immediately
  console.log(`VU ${__VU}: Token already acquired during creation, InstanceId: ${instanceId}`);
  return {
    success: true,
    token: null, // Token is passed from createSandboxInstance
    duration: 0
  };
}

function executeSandboxCode(instanceId, token) {
  try {
    const sandboxUrl = `https://${SANDBOX_PORT}-${instanceId}.${API_REGION}.${SANDBOX_DOMAIN}/execute`;
    
    const payload = {
      code: TEST_CODE,
      language: TEST_LANGUAGE
    };
    
    const response = http.post(sandboxUrl, JSON.stringify(payload), {
      headers: {
        'X-Access-Token': token,
        'Content-Type': 'application/json',
        'Connection': 'keep-alive'
      },
      timeout: EXECUTE_TIMEOUT,
    });
    
    // Use k6's built-in HTTP timing for accurate measurement
    const duration = response.timings.duration;
    
    codeExecuteDuration.add(duration);
    codeExecuteCounter.add(1);
    
    if (response.status === HTTP_SUCCESS_STATUS) {
      codeExecuteSuccessRate.add(true);
      codeExecuteSuccessCounter.add(1);
      console.log(`VU ${__VU}: Code executed, InstanceId: ${instanceId}, Response: ${response.body}`);
      return {
        success: true,
        response: response.body,
        duration: duration
      };
    } else {
      codeExecuteSuccessRate.add(false);
      console.warn(`VU ${__VU}: ⚠️  Code execution failed, InstanceId: ${instanceId}, HTTP ${response.status}, Response: ${response.body}`);
      return {
        success: false,
        error: `Execution failed: HTTP ${response.status}`,
        duration: duration
      };
    }
  } catch (error) {
    codeExecuteSuccessRate.add(false);
    console.warn(`VU ${__VU}: ⚠️  Code execution failed, InstanceId: ${instanceId}, Error: ${error.message}`);
    return {
      success: false,
      error: error.message,
      duration: 0
    };
  }
}

function deleteSandboxInstance(instanceId) {
  try {
    const response = http.del(`${API_GATEWAY_URL}/sandboxes/${instanceId}`, null, {
      headers: {
        'X-API-Key': E2B_API_KEY,
        'User-Agent': 'k6/benchmark'
      },
      timeout: API_TIMEOUT,
    });

    // Use k6's built-in HTTP timing for accurate measurement
    const duration = response.timings.duration;

    sandboxDeleteDuration.add(duration);
    sandboxDeleteCounter.add(1);

    if (response.status === 200 || response.status === 204) {
      sandboxDeleteSuccessRate.add(true);
      sandboxDeleteSuccessCounter.add(1);

      console.log(`VU ${__VU}: Deleted successfully, InstanceId: ${instanceId}`);

      return {
        success: true,
        response: response.body,
        duration: duration
      };
    } else {
      sandboxDeleteSuccessRate.add(false);
      console.error(`VU ${__VU}: ❌ Delete failed, InstanceId: ${instanceId} - HTTP ${response.status}, Response: ${response.body}`);
      console.warn(`VU ${__VU}: ⚠️  Instance ${instanceId} may need manual cleanup`);
      return {
        success: false,
        error: `HTTP error: ${response.status}`,
        duration: duration
      };
    }
  } catch (error) {
    sandboxDeleteSuccessRate.add(false);
    
    console.error(`VU ${__VU}: ❌ Delete exception, InstanceId: ${instanceId} - ${error.message}`);
    console.warn(`VU ${__VU}: ⚠️  Instance ${instanceId} may need manual cleanup`);
    
    return {
      success: false,
      error: error.message,
      duration: 0
    };
  }
}

export default function () {
  if (!E2B_API_KEY) {
    console.error('Please set E2B_API_KEY environment variable');
    return;
  }

  console.log(`VU ${__VU} Iteration ${__ITER}: Starting sandbox lifecycle`);
  
  const createResult = createSandboxInstance();
  
  check(createResult, {
    'Sandbox instance created': (r) => r.success === true,
    'Create response time reasonable': (r) => r.duration < CREATE_TIMEOUT_THRESHOLD,
    'Valid InstanceId returned': (r) => r.success && r.instanceId && r.instanceId.length > 0,
    'Valid Token returned': (r) => r.success && r.token && r.token.length > 0,
  });
  
  // 处理 409 冲突：直接返回，K6 会启动新迭代
  if (createResult.skipped && createResult.reason === 'conflict') {
    console.log(`VU ${__VU} Iteration ${__ITER}: Skipped (409 conflict)`);
    return;
  }
  
  if (!createResult.success || !createResult.instanceId || !createResult.token) {
    console.error(`VU ${__VU} Iteration ${__ITER}: Create failed or no InstanceId/Token, skipping subsequent steps`);
    sleep(SLEEP_ON_ERROR);
    return;
  }
  
  sleep(WAIT_AFTER_CREATE);
  
  // Token is already acquired during creation, use it directly
  const token = createResult.token;
  
  let executeResult = { success: false, duration: 0 };
  if (token) {
    executeResult = executeSandboxCode(createResult.instanceId, token);
    
    check(executeResult, {
      'Code executed': (r) => r.success === true,
      'Execute response time reasonable': (r) => r.duration < EXECUTE_TIMEOUT_THRESHOLD,
    });
  } else {
    console.warn(`VU ${__VU} Iteration ${__ITER}: No token available, skipping code execution`);
  }
  
  const deleteResult = deleteSandboxInstance(createResult.instanceId);
  
  check(deleteResult, {
    'Sandbox instance deleted': (r) => r.success === true,
    'Delete response time reasonable': (r) => r.duration < DELETE_TIMEOUT_THRESHOLD,
  });
  
  const executeDuration = executeResult.duration || 0;
  // Calculate total HTTP time only (excluding sleep/wait time for accurate performance metrics)
  const totalDuration = createResult.duration + executeDuration + deleteResult.duration;
  console.log(`VU ${__VU} Iteration ${__ITER}: Instance ${createResult.instanceId} lifecycle ${totalDuration.toFixed(2)}ms (create:${createResult.duration.toFixed(2)}ms, execute:${executeDuration.toFixed(2)}ms, delete:${deleteResult.duration.toFixed(2)}ms)`);
  
  sandboxLifecycleDuration.add(totalDuration);
  
  sleep(SLEEP_BETWEEN_ITERATIONS);
}

export function setup() {
  console.log('Starting sandbox stress test...');
  
  if (!E2B_API_KEY) {
    throw new Error('Please set E2B_API_KEY environment variable');
  }
  
  return {
    startTime: new Date().toISOString()
  };
}

export function teardown(data) {
  console.log('Stress test completed!');
  console.log(`Test start time: ${data.startTime}`);
  console.log(`Test end time: ${new Date().toISOString()}`);
  console.log('💡 If any instances failed to delete, check logs above and clean up manually');
}

export function handleSummary(data) {
  const testDurationSeconds = data.state.testRunDurationMs / 1000;
  const createQPS = data.metrics.sandbox_create_total ? (data.metrics.sandbox_create_total.values.count / testDurationSeconds) : 0;
  const deleteQPS = data.metrics.sandbox_delete_total ? (data.metrics.sandbox_delete_total.values.count / testDurationSeconds) : 0;
  const createSuccessQPS = data.metrics.sandbox_create_success ? (data.metrics.sandbox_create_success.values.count / testDurationSeconds) : 0;
  const deleteSuccessQPS = data.metrics.sandbox_delete_success ? (data.metrics.sandbox_delete_success.values.count / testDurationSeconds) : 0;
  const executeQPS = data.metrics.code_execute_total ? (data.metrics.code_execute_total.values.count / testDurationSeconds) : 0;
  const createConflicts = data.metrics.sandbox_create_conflict ? data.metrics.sandbox_create_conflict.values.count : 0;
  
  return {
    'summary.json': JSON.stringify(data, null, 2),
    stdout: `
========================================
Sandbox Stress Test Results
========================================

Overview:
- Total iterations: ${data.metrics.iterations.values.count}
- Test duration: ${testDurationSeconds.toFixed(1)}s
- HTTP success rate: ${((1 - data.metrics.http_req_failed.values.rate) * 100).toFixed(2)}%
- Average response time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms

QPS Statistics:
- Create QPS: ${createQPS.toFixed(2)} requests/s (success: ${createSuccessQPS.toFixed(2)} requests/s)
- Delete QPS: ${deleteQPS.toFixed(2)} requests/s (success: ${deleteSuccessQPS.toFixed(2)} requests/s)
- Code Execute QPS: ${executeQPS.toFixed(2)} requests/s
- Total API QPS: ${(createQPS + deleteQPS + executeQPS).toFixed(2)} requests/s

Sandbox Operations:
- Create success rate: ${data.metrics.sandbox_create_success_rate ? (data.metrics.sandbox_create_success_rate.values.avg * 100).toFixed(2) : 'N/A'}%
- Create avg time: ${data.metrics.sandbox_create_duration ? data.metrics.sandbox_create_duration.values.avg.toFixed(2) : 'N/A'}ms
- Create p95: ${data.metrics.sandbox_create_duration ? data.metrics.sandbox_create_duration.values['p(95)'].toFixed(2) : 'N/A'}ms
${createConflicts > 0 ? `- Create conflicts (409): ${createConflicts} (skipped, not counted as errors)\n` : ''}
- Delete success rate: ${data.metrics.sandbox_delete_success_rate ? (data.metrics.sandbox_delete_success_rate.values.avg * 100).toFixed(2) : 'N/A'}%
- Delete avg time: ${data.metrics.sandbox_delete_duration ? data.metrics.sandbox_delete_duration.values.avg.toFixed(2) : 'N/A'}ms
- Delete p95: ${data.metrics.sandbox_delete_duration ? data.metrics.sandbox_delete_duration.values['p(95)'].toFixed(2) : 'N/A'}ms
- Code execute success rate: ${data.metrics.code_execute_success_rate ? (data.metrics.code_execute_success_rate.values.avg * 100).toFixed(2) : 'N/A'}%
- Code execute avg time: ${data.metrics.code_execute_duration ? data.metrics.code_execute_duration.values.avg.toFixed(2) : 'N/A'}ms
- Code execute p95: ${data.metrics.code_execute_duration ? data.metrics.code_execute_duration.values['p(95)'].toFixed(2) : 'N/A'}ms
- Lifecycle avg time: ${data.metrics.sandbox_lifecycle_duration ? data.metrics.sandbox_lifecycle_duration.values.avg.toFixed(2) : 'N/A'}ms

Virtual Users:
- Max VUs: ${data.metrics.vus_max.values.max}
- Avg VUs: ${data.metrics.vus.values.avg.toFixed(2)}

========================================
    `,
  };
}
