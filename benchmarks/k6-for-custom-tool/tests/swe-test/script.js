import { sleep } from 'k6';
import ags from 'k6/x/ags';

// ============================================================================
// 辅助函数
// ============================================================================

// 解析命令参数，支持字符串或 JSON 数组
function parseCommands(value, defaultValue) {
    if (!value) {
        return defaultValue ? [defaultValue] : [];
    }
    // 尝试解析为 JSON 数组
    if (value.startsWith('[')) {
        try {
            return JSON.parse(value);
        } catch (e) {
            // 解析失败，当作普通字符串
        }
    }
    return [value];
}

// 执行命令并打印结果
function runCommand(instanceId, port, command, timeout, options, stepName) {
    console.log(`  命令: ${command}`);
    console.log(`  超时: ${timeout}s`);
    
    if (options.env) {
        console.log(`  环境变量: ${JSON.stringify(options.env)}`);
    }
    if (options.workdir) {
        console.log(`  工作目录: ${options.workdir}`);
    }
    
    const result = ags.execShell2Http(instanceId, port, command, timeout, options);
    
    console.log(`  成功: ${result.success}`);
    console.log(`  退出码: ${result.exit_code}`);
    console.log(`  耗时: ${result.duration_ms}ms`);
    console.log(`  HTTP耗时: ${result.timing_ms}ms`);
    console.log(`  错误: ${result.error}`);
    
    if (result.output) {
        console.log('  输出:');
        console.log('-'.repeat(40));
        console.log(result.output);
        console.log('-'.repeat(40));
    }
    
    return result;
}

// ============================================================================
// 配置项
// ============================================================================
const CONFIG = {
    // 工具名称
    toolName: __ENV.TOOL_NAME || 'swe-test-tool',
    
    // 镜像配置
    image: __ENV.IMAGE || 'ccr.ccs.tencentyun.com/your-namespace/your-image:latest',
    imageRegistryType: __ENV.IMAGE_REGISTRY_TYPE || 'enterprise',
    
    // 实例超时时间
    instanceTimeout: __ENV.INSTANCE_TIMEOUT || '10m',
    
    // shell2http 端口
    shell2httpPort: __ENV.SHELL2HTTP_PORT || '8080',
    
    // 安装命令（可选，支持字符串或 JSON 数组）
    installCommands: parseCommands(__ENV.INSTALL_COMMAND, ''),
    
    // 测试命令（支持字符串或 JSON 数组）
    testCommands: parseCommands(__ENV.TEST_COMMAND, 'echo "Hello from sandbox!"'),
    
    // 命令执行超时（秒）
    commandTimeout: parseInt(__ENV.COMMAND_TIMEOUT || '300'),
    
    // 执行选项（JSON 格式，如: {"env":{"FOO":"bar"},"workdir":"/testbed"}）
    execOptions: __ENV.EXEC_OPTIONS ? JSON.parse(__ENV.EXEC_OPTIONS) : {},
};

// ============================================================================
// k6 配置
// ============================================================================
export const options = {
    vus: 1,
    iterations: 1,
};

// ============================================================================
// 主测试逻辑
// ============================================================================
export default function () {
    let instanceId = null;
    
    try {
        // ========================================
        // Step 1: 启动沙箱实例（指定镜像）
        // ========================================
        console.log('='.repeat(60));
        console.log('[Step 1] 启动沙箱实例...');
        console.log(`  镜像: ${CONFIG.image}`);
        console.log(`  工具名: ${CONFIG.toolName}`);
        
        const startParams = {
            ToolName: CONFIG.toolName,
            Timeout: CONFIG.instanceTimeout,
            CustomConfiguration: {
                Image: CONFIG.image,
                ImageRegistryType: CONFIG.imageRegistryType,
                Resources: {
                    CPU: "4",
                    Memory: "8Gi"
                }
            },
        };
        
        const startResult = ags.startSandboxInstance(startParams);
        
        if (!startResult.success) {
            console.error(`启动实例失败: ${startResult.error}`);
            console.error(`请求ID: ${startResult.request_id}`);
            return;
        }
        
        instanceId = startResult.data.Instance.InstanceId;
        console.log(`  实例ID: ${instanceId}`);
        console.log(`  耗时: ${startResult.timing_ms}ms`);
        console.log('[Step 1] 沙箱实例启动成功!');
        sleep(120)
        
        // ========================================
        // Step 2: 运行安装命令（如果有）
        // ========================================
        if (CONFIG.installCommands.length > 0 && CONFIG.installCommands[0]) {
            console.log('='.repeat(60));
            console.log(`[Step 2] 运行安装命令 (共 ${CONFIG.installCommands.length} 条)...`);
            
            for (let i = 0; i < CONFIG.installCommands.length; i++) {
                const cmd = CONFIG.installCommands[i];
                console.log(`\n[Step 2.${i + 1}] 执行第 ${i + 1} 条安装命令:`);
                
                const result = runCommand(
                    instanceId,
                    CONFIG.shell2httpPort,
                    cmd,
                    CONFIG.commandTimeout,
                    CONFIG.execOptions,
                    `安装命令 ${i + 1}`
                );
                
                if (!result.success || result.exit_code !== 0) {
                    console.error(`安装命令 ${i + 1} 执行失败!`);
                    if (result.timeout) {
                        console.error('命令执行超时!');
                    }
                    return;
                }
                console.log(`[Step 2.${i + 1}] 安装命令 ${i + 1} 执行成功!`);
            }
            console.log('[Step 2] 所有安装命令执行成功!');
        }
        
        // ========================================
        // Step 3: 运行测试命令
        // ========================================
        console.log('='.repeat(60));
        console.log(`[Step 3] 运行测试命令 (共 ${CONFIG.testCommands.length} 条)...`);
        
        let allTestsPassed = true;
        for (let i = 0; i < CONFIG.testCommands.length; i++) {
            const cmd = CONFIG.testCommands[i];
            console.log(`\n[Step 3.${i + 1}] 执行第 ${i + 1} 条测试命令:`);
            
            const result = runCommand(
                instanceId,
                CONFIG.shell2httpPort,
                cmd,
                CONFIG.commandTimeout,
                CONFIG.execOptions,
                `测试命令 ${i + 1}`
            );
            
            if (!result.success || result.exit_code !== 0) {
                console.error(`测试命令 ${i + 1} 执行失败!`);
                if (result.timeout) {
                    console.error('命令执行超时!');
                }
                allTestsPassed = false;
                // 继续执行剩余测试命令
            } else {
                console.log(`[Step 3.${i + 1}] 测试命令 ${i + 1} 执行成功!`);
            }
        }
        
        if (allTestsPassed) {
            console.log('[Step 3] 所有测试命令执行成功!');
        } else {
            console.error('[Step 3] 部分测试命令执行失败!');
        }
        
    } catch (error) {
        console.error(`执行过程中发生错误: ${error}`);
    } finally {
        // ========================================
        // Step 4: 停止沙箱实例
        // ========================================
        if (instanceId) {
            console.log('='.repeat(60));
            console.log('[Step 4] 停止沙箱实例...');
            console.log(`  实例ID: ${instanceId}`);
            
            const stopResult = ags.stopSandboxInstance({
                InstanceId: instanceId,
            });
            
            if (stopResult.success) {
                console.log(`  耗时: ${stopResult.timing_ms}ms`);
                console.log('[Step 4] 沙箱实例已停止!');
            } else {
                console.error(`停止实例失败: ${stopResult.error}`);
                console.error(`请求ID: ${stopResult.request_id}`);
            }
        }
        
        console.log('='.repeat(60));
        console.log('测试流程完成');
    }
}
