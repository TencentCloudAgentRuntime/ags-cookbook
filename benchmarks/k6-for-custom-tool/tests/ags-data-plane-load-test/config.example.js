// ============================================================================
// 配置文件示例 - 复制为 local/config.js 并修改
// ============================================================================

// SWE-bench 场景多轮 Stress 配置（1c2g 沙箱，峰值 70% CPU）
// 模拟多次迭代：分析 → 推理等待 → 测试 → ...
const stressRounds = [
    // === 第 1 次迭代 ===
    { cpu_workers: 1, cpu_load: 40, vm_workers: 1, vm_bytes: "384M", io_workers: 1, timeout: 15, jitter: 20 },  // 分析
    { cpu_workers: 1, cpu_load: 15, vm_workers: 1, vm_bytes: "256M", io_workers: 0, timeout: 18, jitter: 25 },  // 推理等待
    { cpu_workers: 1, cpu_load: 70, vm_workers: 1, vm_bytes: "512M", io_workers: 1, timeout: 20, jitter: 15 },  // 测试

    // === 第 2 次迭代 ===
    { cpu_workers: 1, cpu_load: 35, vm_workers: 1, vm_bytes: "384M", io_workers: 1, timeout: 10, jitter: 20 },  // 分析
    { cpu_workers: 1, cpu_load: 12, vm_workers: 1, vm_bytes: "256M", io_workers: 0, timeout: 20, jitter: 25 },  // 推理等待
    { cpu_workers: 1, cpu_load: 65, vm_workers: 1, vm_bytes: "512M", io_workers: 1, timeout: 18, jitter: 15 },  // 测试

    // === 第 3 次迭代 ===
    { cpu_workers: 1, cpu_load: 45, vm_workers: 1, vm_bytes: "384M", io_workers: 1, timeout: 20, jitter: 20 },  // 分析
    { cpu_workers: 1, cpu_load: 10, vm_workers: 1, vm_bytes: "256M", io_workers: 0, timeout: 15, jitter: 25 },  // 推理等待
    { cpu_workers: 1, cpu_load: 70, vm_workers: 1, vm_bytes: "512M", io_workers: 1, timeout: 20, jitter: 15 },  // 测试
];

export const config = {
    // ------------------------------------------------------------------------
    // AGS 配置
    // ------------------------------------------------------------------------
    toolName: 'your-tool-name',
    instanceTimeout: '30m',
    shell2httpPort: '8080',

    // ------------------------------------------------------------------------
    // 压测参数 (constant-arrival-rate 模式)
    // ------------------------------------------------------------------------
    // 每秒请求数 (QPS)
    qps: 5,
    // 测试持续时间
    duration: '5m',
    // 预分配 VU 数
    preAllocatedVUs: 30,
    // 最大 VU 数
    maxVUs: 100,
    // stress 延迟执行秒数
    stressDelaySeconds: 10,

    // ------------------------------------------------------------------------
    // Stress 配置
    // ------------------------------------------------------------------------
    stressRounds: stressRounds,

    // ------------------------------------------------------------------------
    // 镜像列表 (设为空数组则不使用自定义镜像)
    // ------------------------------------------------------------------------
    images: [],
};
