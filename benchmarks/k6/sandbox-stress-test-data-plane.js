import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import http from 'k6/http';
import crypto from 'k6/crypto';

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

// Data plane stress test configuration
const MAX_VUS = parseInt(__ENV.MAX_VUS) || 5;  // Default for personal quota (max 10 sandboxes)
const VUS_INCREASE_PER_SECOND = parseInt(__ENV.VUS_INCREASE_PER_SECOND) || 1;  // Slow ramp for personal quota
const CODE_EXECUTION_DURATION = parseInt(__ENV.CODE_EXECUTION_DURATION) || 30; // seconds
const STEADY_DURATION = __ENV.STEADY_DURATION || '2m'; // Keep max VUs for this duration
const RAMP_DOWN_DURATION = __ENV.RAMP_DOWN_DURATION || '30s';
const GRACEFUL_RAMP_DOWN = __ENV.GRACEFUL_RAMP_DOWN || '30s';

// Thresholds
const HTTP_REQ_DURATION_P95 = parseInt(__ENV.HTTP_REQ_DURATION_P95) || 5000;
const HTTP_REQ_FAILED_RATE = parseFloat(__ENV.HTTP_REQ_FAILED_RATE) || 0.1;
const CREATE_DURATION_P95 = parseInt(__ENV.CREATE_DURATION_P95) || 10000;
const DELETE_DURATION_P95 = parseInt(__ENV.DELETE_DURATION_P95) || 5000;

// Timeout configuration
const API_TIMEOUT = __ENV.API_TIMEOUT || '30s';
const EXECUTE_TIMEOUT = __ENV.EXECUTE_TIMEOUT || '3m';

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
const USE_INTERNAL = __ENV.USE_INTERNAL === 'true'; // Set to 'true' for Tencent Cloud internal network
const API_HOST = __ENV.API_HOST || (USE_INTERNAL ? 'ags.internal.tencentcloudapi.com' : 'ags.tencentcloudapi.com');
const API_VERSION = __ENV.API_VERSION || '2025-09-20';
const API_SERVICE = 'ags';

// Sandbox configuration
const SANDBOX_TOOL_NAME = __ENV.SANDBOX_TOOL_NAME || 'code-interpreter-v1';
const SANDBOX_PORT = __ENV.SANDBOX_PORT || '49999';
const SANDBOX_DOMAIN_SUFFIX = USE_INTERNAL ? 'internal.tencentags.com' : 'tencentags.com';

// Test code configuration - Long running code for data plane stress test
const TEST_CODE = __ENV.TEST_CODE || `import time\ntime.sleep(${CODE_EXECUTION_DURATION})`;
const TEST_LANGUAGE = __ENV.TEST_LANGUAGE || 'python';

// HTTP status
const HTTP_SUCCESS_STATUS = 200;

// Build scenarios based on TEST_SCENARIO
function buildScenarios() {
  // Calculate ramp up duration: MAX_VUS / VUS_INCREASE_PER_SECOND
  const rampUpSeconds = Math.ceil(MAX_VUS / VUS_INCREASE_PER_SECOND);
  const rampUpDuration = `${rampUpSeconds}s`;
  
  console.log(`Data plane stress test configuration:`);
  console.log(`- Max VUs: ${MAX_VUS}`);
  console.log(`- VUs increase per second: ${VUS_INCREASE_PER_SECOND}`);
  console.log(`- Ramp up duration: ${rampUpDuration} (${rampUpSeconds} seconds)`);
  console.log(`- Steady duration: ${STEADY_DURATION}`);
  console.log(`- Code execution duration: ${CODE_EXECUTION_DURATION} seconds`);
  console.log(`- Max connections will be maintained during steady state`);
  
  return {
    data_plane_stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: rampUpDuration, target: MAX_VUS },
        { duration: STEADY_DURATION, target: MAX_VUS },
        { duration: RAMP_DOWN_DURATION, target: 0 },
      ],
      gracefulRampDown: GRACEFUL_RAMP_DOWN,
    }
  };
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

const API_CONFIG = {
  host: API_HOST,
  service: API_SERVICE,
  region: API_REGION,
  version: API_VERSION,
};

function getDate(timestamp) {
  const date = new Date(timestamp * 1000);
  const year = date.getUTCFullYear();
  const month = ("0" + (date.getUTCMonth() + 1)).slice(-2);
  const day = ("0" + date.getUTCDate()).slice(-2);
  return `${year}-${month}-${day}`;
}

function getHash(message, encoding = "hex") {
  return crypto.sha256(message, encoding);
}

function createTencentCloudSignature(action, payload, timestamp) {
  const SECRET_ID = __ENV.TENCENTCLOUD_SECRET_ID;
  const SECRET_KEY = __ENV.TENCENTCLOUD_SECRET_KEY;
  const TOKEN = "";

  const { host, service, region, version } = API_CONFIG;
  const date = getDate(timestamp);

  const signedHeaders = "content-type;host";
  const hashedRequestPayload = getHash(payload);
  const httpRequestMethod = "POST";
  const canonicalUri = "/";
  const canonicalQueryString = "";
  const canonicalHeaders =
    "content-type:application/json; charset=utf-8\n" + "host:" + host + "\n";

  const canonicalRequest =
    httpRequestMethod +
    "\n" +
    canonicalUri +
    "\n" +
    canonicalQueryString +
    "\n" +
    canonicalHeaders +
    "\n" +
    signedHeaders +
    "\n" +
    hashedRequestPayload;

  const algorithm = "TC3-HMAC-SHA256";
  const hashedCanonicalRequest = getHash(canonicalRequest);
  const credentialScope = date + "/" + service + "/" + "tc3_request";
  const stringToSign =
    algorithm +
    "\n" +
    timestamp +
    "\n" +
    credentialScope +
    "\n" +
    hashedCanonicalRequest;

  const kDate = crypto.hmac('sha256', "TC3" + SECRET_KEY, date, 'binary');
  const kService = crypto.hmac('sha256', kDate, service, 'binary');
  const kSigning = crypto.hmac('sha256', kService, "tc3_request", 'binary');
  const signature = crypto.hmac('sha256', kSigning, stringToSign, 'hex');

  const authorization =
    algorithm +
    " " +
    "Credential=" +
    SECRET_ID +
    "/" +
    credentialScope +
    ", " +
    "SignedHeaders=" +
    signedHeaders +
    ", " +
    "Signature=" +
    signature;

  const headers = {
    Authorization: authorization,
    "Content-Type": "application/json; charset=utf-8",
    Host: host,
    "X-TC-Action": action,
    "X-TC-Timestamp": timestamp,
    "X-TC-Version": version,
  };

  if (region) {
    headers["X-TC-Region"] = region;
  }
  if (TOKEN) {
    headers["X-TC-Token"] = TOKEN;
  }

  return {
    authorization,
    timestamp,
    headers: headers
  };
}

function callTencentCloudAPI(action, payload = {}) {
  const timestamp = Math.floor(Date.now() / 1000);
  const payloadStr = JSON.stringify(payload);
  
  const { headers } = createTencentCloudSignature(action, payloadStr, timestamp);
  
  const response = http.post(`https://${API_CONFIG.host}/`, payloadStr, {
    headers: headers,
    timeout: API_TIMEOUT,
  });
  
  return {
    status: response.status,
    body: response.body,
    duration: response.timings.duration,
  };
}

function createSandboxInstance() {
  try {
    const result = callTencentCloudAPI('StartSandboxInstance', {"ToolName": SANDBOX_TOOL_NAME});
    // Use k6's built-in HTTP timing for accurate measurement
    const duration = result.duration;
    
    sandboxCreateDuration.add(duration);
    sandboxCreateCounter.add(1);
    
    if (result.status !== HTTP_SUCCESS_STATUS) {
      sandboxCreateSuccessRate.add(false);
      console.error(`VU ${__VU}: Create failed - HTTP ${result.status}`);
      return {
        success: false,
        error: `HTTP error: ${result.status}`,
        duration: duration
      };
    }
    
    const data = JSON.parse(result.body);
    
    if (data.Response && data.Response.Error) {
      sandboxCreateSuccessRate.add(false);
      console.error(`VU ${__VU}: Create failed - ${data.Response.Error.Code}: ${data.Response.Error.Message}`);
      return {
        success: false,
        error: `${data.Response.Error.Code}: ${data.Response.Error.Message}`,
        errorCode: data.Response.Error.Code,
        duration: duration
      };
    }
    
    if (!data.Response?.Instance?.InstanceId) {
      sandboxCreateSuccessRate.add(false);
      console.error(`VU ${__VU}: Create failed - No InstanceId returned`);
      return {
        success: false,
        error: 'No InstanceId returned',
        duration: duration
      };
    }
    
    const instanceId = data.Response.Instance.InstanceId;
    sandboxCreateSuccessRate.add(true);
    sandboxCreateSuccessCounter.add(1);
    
    console.log(`VU ${__VU}: Created successfully, InstanceId: ${instanceId}`);
    console.log(`VU ${__VU}: Status: ${data.Response.Instance.Status}, Tool: ${data.Response.Instance.ToolName}`);
    
    return {
      success: true,
      instanceId: instanceId,
      response: data,
      duration: duration
    };
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
  try {
    const result = callTencentCloudAPI('AcquireSandboxInstanceToken', {
      InstanceId: instanceId
    });
    // Use k6's built-in HTTP timing for accurate measurement
    const duration = result.duration;
    
    tokenAcquireDuration.add(duration);
    tokenAcquireCounter.add(1);
    
    if (result.status !== HTTP_SUCCESS_STATUS) {
      tokenAcquireSuccessRate.add(false);
      console.warn(`VU ${__VU}: ⚠️  Acquire token failed, InstanceId: ${instanceId} - HTTP ${result.status}`);
      return {
        success: false,
        error: `HTTP error: ${result.status}`,
        duration: duration
      };
    }
    
    const data = JSON.parse(result.body);
    
    if (data.Response && data.Response.Error) {
      tokenAcquireSuccessRate.add(false);
      console.warn(`VU ${__VU}: ⚠️  Acquire token failed, InstanceId: ${instanceId} - ${data.Response.Error.Code}: ${data.Response.Error.Message}`);
      return {
        success: false,
        error: `${data.Response.Error.Code}: ${data.Response.Error.Message}`,
        errorCode: data.Response.Error.Code,
        duration: duration
      };
    }
    
    if (!data.Response?.Token) {
      tokenAcquireSuccessRate.add(false);
      console.warn(`VU ${__VU}: ⚠️  Acquire token failed, InstanceId: ${instanceId} - No token returned`);
      return {
        success: false,
        error: 'No token returned',
        duration: duration
      };
    }
    
    const token = data.Response.Token;
    const expiresAt = data.Response.ExpiresAt;
    tokenAcquireSuccessRate.add(true);
    tokenAcquireSuccessCounter.add(1);
    console.log(`VU ${__VU}: Token acquired, InstanceId: ${instanceId}, ExpiresAt: ${expiresAt}`);
    
    return {
      success: true,
      token: token,
      expiresAt: expiresAt,
      duration: duration
    };
  } catch (error) {
    tokenAcquireSuccessRate.add(false);
    console.warn(`VU ${__VU}: ⚠️  Acquire token exception, InstanceId: ${instanceId} - ${error.message}`);
    return {
      success: false,
      error: error.message,
      duration: 0
    };
  }
}

function executeSandboxCode(instanceId, token) {
  try {
    const sandboxUrl = `https://${SANDBOX_PORT}-${instanceId}.${API_REGION}.${SANDBOX_DOMAIN_SUFFIX}/execute`;
    
    const payload = {
      code: TEST_CODE,
      language: TEST_LANGUAGE
    };
    
    const response = http.post(sandboxUrl, JSON.stringify(payload), {
      headers: {
        'X-Access-Token': token,
        'Content-Type': 'application/json'
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
    const result = callTencentCloudAPI('StopSandboxInstance', {
      InstanceId: instanceId
    });
    // Use k6's built-in HTTP timing for accurate measurement
    const duration = result.duration;
    
    sandboxDeleteDuration.add(duration);
    sandboxDeleteCounter.add(1);
    
    if (result.status !== HTTP_SUCCESS_STATUS) {
      sandboxDeleteSuccessRate.add(false);
      console.error(`VU ${__VU}: ❌ Delete failed, InstanceId: ${instanceId} - HTTP ${result.status}`);
      console.warn(`VU ${__VU}: ⚠️  Instance ${instanceId} may need manual cleanup`);
      return {
        success: false,
        error: `HTTP error: ${result.status}`,
        duration: duration
      };
    }
    
    const data = JSON.parse(result.body);
    
    if (data.Response && data.Response.Error) {
      sandboxDeleteSuccessRate.add(false);
      console.error(`VU ${__VU}: ❌ Delete failed, InstanceId: ${instanceId} - ${data.Response.Error.Code}: ${data.Response.Error.Message}`);
      console.warn(`VU ${__VU}: ⚠️  Instance ${instanceId} may need manual cleanup`);
      return {
        success: false,
        error: `${data.Response.Error.Code}: ${data.Response.Error.Message}`,
        errorCode: data.Response.Error.Code,
        duration: duration
      };
    }
    
    sandboxDeleteSuccessRate.add(true);
    sandboxDeleteSuccessCounter.add(1);
    
    console.log(`VU ${__VU}: Deleted successfully, InstanceId: ${instanceId}`);
    
    return {
      success: true,
      response: data,
      duration: duration
    };
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
  if (!__ENV.TENCENTCLOUD_SECRET_ID || !__ENV.TENCENTCLOUD_SECRET_KEY) {
    console.error('Please set TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY environment variables');
    return;
  }

  console.log(`VU ${__VU} Iteration ${__ITER}: Starting sandbox lifecycle`);
  
  const createResult = createSandboxInstance();
  
  check(createResult, {
    'Sandbox instance created': (r) => r.success === true,
    'Create response time reasonable': (r) => r.duration < CREATE_TIMEOUT_THRESHOLD,
    'Valid InstanceId returned': (r) => r.success && r.instanceId && r.instanceId.length > 0,
  });
  
  if (!createResult.success || !createResult.instanceId) {
    console.error(`VU ${__VU} Iteration ${__ITER}: Create failed or no InstanceId, skipping subsequent steps`);
    sleep(SLEEP_ON_ERROR);
    return;
  }
  
  sleep(WAIT_AFTER_CREATE);
  
  const tokenResult = acquireSandboxToken(createResult.instanceId);
  
  check(tokenResult, {
    'Token acquired': (r) => r.success === true,
  });
  
  let executeResult = { success: false, duration: 0 };
  if (tokenResult.success && tokenResult.token) {
    executeResult = executeSandboxCode(createResult.instanceId, tokenResult.token);
    
    check(executeResult, {
      'Code executed': (r) => r.success === true,
      'Execute response time reasonable': (r) => r.duration < EXECUTE_TIMEOUT_THRESHOLD,
    });
  } else {
    console.warn(`VU ${__VU} Iteration ${__ITER}: Token acquisition failed, skipping code execution`);
  }
  
  const deleteResult = deleteSandboxInstance(createResult.instanceId);
  
  check(deleteResult, {
    'Sandbox instance deleted': (r) => r.success === true,
    'Delete response time reasonable': (r) => r.duration < DELETE_TIMEOUT_THRESHOLD,
  });
  
  const tokenDuration = tokenResult.duration || 0;
  const executeDuration = executeResult.duration || 0;
  // Calculate total HTTP time only (excluding sleep/wait time for accurate performance metrics)
  const totalDuration = createResult.duration + tokenDuration + executeDuration + deleteResult.duration;
  console.log(`VU ${__VU} Iteration ${__ITER}: Instance ${createResult.instanceId} lifecycle ${totalDuration.toFixed(2)}ms (create:${createResult.duration.toFixed(2)}ms, token:${tokenDuration.toFixed(2)}ms, execute:${executeDuration.toFixed(2)}ms, delete:${deleteResult.duration.toFixed(2)}ms)`);
  
  sandboxLifecycleDuration.add(totalDuration);
  
  sleep(SLEEP_BETWEEN_ITERATIONS);
}

export function setup() {
  console.log('Starting data plane stress test...');
  console.log(`Configuration:`);
  console.log(`- Max VUs: ${MAX_VUS}`);
  console.log(`- VUs increase rate: ${VUS_INCREASE_PER_SECOND}/s`);
  console.log(`- Steady duration: ${STEADY_DURATION}`);
  console.log(`- Code execution duration: ${CODE_EXECUTION_DURATION}s`);
  console.log(`- Expected max concurrent connections: ${MAX_VUS}`);
  
  if (!__ENV.TENCENTCLOUD_SECRET_ID || !__ENV.TENCENTCLOUD_SECRET_KEY) {
    throw new Error('Please set TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY environment variables');
  }
  
  return {
    startTime: new Date().toISOString()
  };
}

export function teardown(data) {
  console.log('Data plane stress test completed!');
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
  const tokenQPS = data.metrics.token_acquire_total ? (data.metrics.token_acquire_total.values.count / testDurationSeconds) : 0;
  const executeQPS = data.metrics.code_execute_total ? (data.metrics.code_execute_total.values.count / testDurationSeconds) : 0;
  
  return {
    'summary.json': JSON.stringify(data, null, 2),
    stdout: `
========================================
Data Plane Stress Test Results
========================================

Test Configuration:
- Max VUs: ${MAX_VUS}
- VUs increase rate: ${VUS_INCREASE_PER_SECOND}/s
- Steady duration: ${STEADY_DURATION}
- Code execution duration: ${CODE_EXECUTION_DURATION}s
- Expected max concurrent connections: ${MAX_VUS}

Overview:
- Total iterations: ${data.metrics.iterations.values.count}
- Test duration: ${testDurationSeconds.toFixed(1)}s
- HTTP success rate: ${((1 - data.metrics.http_req_failed.values.rate) * 100).toFixed(2)}%
- Average response time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms

QPS Statistics:
- Create QPS: ${createQPS.toFixed(2)} requests/s (success: ${createSuccessQPS.toFixed(2)} requests/s)
- Delete QPS: ${deleteQPS.toFixed(2)} requests/s (success: ${deleteSuccessQPS.toFixed(2)} requests/s)
- Token Acquire QPS: ${tokenQPS.toFixed(2)} requests/s
- Code Execute QPS: ${executeQPS.toFixed(2)} requests/s
- Total API QPS: ${(createQPS + deleteQPS + tokenQPS).toFixed(2)} requests/s

Sandbox Operations:
- Create success rate: ${data.metrics.sandbox_create_success_rate ? (data.metrics.sandbox_create_success_rate.values.avg * 100).toFixed(2) : 'N/A'}%
- Create avg time: ${data.metrics.sandbox_create_duration ? data.metrics.sandbox_create_duration.values.avg.toFixed(2) : 'N/A'}ms
- Create p95: ${data.metrics.sandbox_create_duration ? data.metrics.sandbox_create_duration.values['p(95)'].toFixed(2) : 'N/A'}ms
- Delete success rate: ${data.metrics.sandbox_delete_success_rate ? (data.metrics.sandbox_delete_success_rate.values.avg * 100).toFixed(2) : 'N/A'}%
- Delete avg time: ${data.metrics.sandbox_delete_duration ? data.metrics.sandbox_delete_duration.values.avg.toFixed(2) : 'N/A'}ms
- Delete p95: ${data.metrics.sandbox_delete_duration ? data.metrics.sandbox_delete_duration.values['p(95)'].toFixed(2) : 'N/A'}ms
- Token acquire success rate: ${data.metrics.token_acquire_success_rate ? (data.metrics.token_acquire_success_rate.values.avg * 100).toFixed(2) : 'N/A'}%
- Token acquire avg time: ${data.metrics.token_acquire_duration ? data.metrics.token_acquire_duration.values.avg.toFixed(2) : 'N/A'}ms
- Token acquire p95: ${data.metrics.token_acquire_duration ? data.metrics.token_acquire_duration.values['p(95)'].toFixed(2) : 'N/A'}ms
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
