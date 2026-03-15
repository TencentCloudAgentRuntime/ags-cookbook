"""
强化学习 + AgentSandbox 沙箱 的最小示例（单文件版）

核心目标：
- 展示"模型输出 ToolCall → VERL 解析 → 启动沙箱 → 回填结果"的完整流程
- 强调：沙箱由 runtime 启动，不是模型
- 用真实数学题，而不是 toy 示例

该脚本是"流程示意"，不是完整训练代码
"""

import os
from e2b_code_interpreter import Sandbox
import re
import json


# =========================================================
# Step 0: AgentSandbox 环境配置（真实）
# =========================================================

# AgentSandbox 域名（兼容 E2B），可通过环境变量预先设置
if not os.getenv("E2B_DOMAIN"):
    os.environ["E2B_DOMAIN"] = "ap-guangzhou.tencentags.com"
# API Key（可通过环境变量预先设置）
if not os.getenv("E2B_API_KEY"):
    # E2B_API_KEY should be obtained from Tencent Cloud Agent Sandbox product
    os.environ["E2B_API_KEY"] = ""


def parse_tool_call(model_output: str):
    """
    从 <toolcall>...</toolcall> 中解析 tool 和 code
    """

    m = re.search(r"<toolcall>\s*(\{.*\})\s*</toolcall>", model_output, re.S)
    if not m:
        raise ValueError("toolcall not found")

    obj = json.loads(m.group(1))
    return obj["tool"], obj["code"]



# =========================================================
# Step 1: 模型输出 ToolCall（Policy 行为）
# =========================================================

def model_generate(question: str) -> str:
    """
    模型的行为（Policy πθ）

    在强化学习视角中：
    - 当前 state = question + 历史上下文
    - 模型选择 action = 是否调用工具 & 调用什么工具

    这里直接模拟模型输出一个 ToolCall
    """
    return f"""
我需要通过计算题目来得到答案。
<toolcall>
{{
  "tool": "sandbox.exec_python",
  "code": "result = (23 * 17) - 19\\nprint(result)"
}}
</toolcall>
"""


# =========================================================
# Step 2: VERL 解析 ToolCall，并触发沙箱执行
# =========================================================

def verl_parse_and_execute(model_output: str) -> str:
    """
    VERL Runtime 的职责：

    1. 从模型输出中解析 ToolCall
    2. 启动 AgentSandbox 沙箱
    3. 在沙箱中安全执行模型生成的代码
    """

    # === Step 1: Parse tool call ===
    tool_name, python_code = parse_tool_call(model_output)

    if tool_name != "sandbox.exec_python":
        raise ValueError(f"Unsupported tool: {tool_name}")

    # === Step 2: Create sandbox ===
    sandbox = Sandbox.create(
        template="code-interpreter-v1",
        timeout=300
    )

    output_buffer = []

    def on_stdout(data):
        output_buffer.append(data.line.rstrip("\n"))

    try:
        sandbox.run_code(
            python_code,
            on_stdout=on_stdout,
        )
    finally:
        sandbox.kill()

    return "\n".join(output_buffer)


# =========================================================
# Step 3: 沙箱结果回填上下文（状态转移）
# =========================================================

def stitch_context(question: str, sandbox_result: str) -> str:
    """
    将沙箱执行结果拼回上下文

    强化学习中：
    - sandbox_result = environment 的 observation
    - 拼回后形成 new state
    """
    return f"""
问题：{question}
工具执行结果：{sandbox_result}
请给出最终答案。
"""


# =========================================================
# 强化学习中的一次 Rollout（Episode）
# =========================================================

def rollout_one_episode():
    """
    一次完整的强化学习轨迹（trajectory）：

    Policy → Environment → Observation → Reward
    """

    # 初始状态
    question = "计算：23 × 17 − 19"

    # Step 1: Policy 生成 ToolCall
    model_output = model_generate(question)

    # Step 2: VERL 解析并触发 AgentSandbox 沙箱
    sandbox_result = verl_parse_and_execute(model_output)

    # Step 3: 回填上下文
    final_context = stitch_context(question, sandbox_result)

    # Reward（示例）
    # 正确答案是 372
    reward = 1.0 if sandbox_result == "372" else 0.0

    return {
        "question": question,
        "sandbox_result": sandbox_result,
        "final_context": final_context,
        "reward": reward
    }


# =========================================================
# 主入口
# =========================================================

if __name__ == "__main__":
    trajectory = rollout_one_episode()

    print("=== Rollout Result ===")
    print("Question:", trajectory["question"])
    print("Sandbox Result:", trajectory["sandbox_result"])
    print("Reward:", trajectory["reward"])
