import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright
from e2b import Sandbox
from typing import List, Dict


# ========== 配置 ==========
# 运行前请通过环境变量设置所需配置
E2B_DOMAIN = os.getenv("E2B_DOMAIN", "")
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")

if E2B_DOMAIN:
    os.environ["E2B_DOMAIN"] = E2B_DOMAIN
if E2B_API_KEY:
    os.environ["E2B_API_KEY"] = E2B_API_KEY


def call_llm(messages: List[Dict], tools: List[Dict] = None) -> Dict:
    """调用 LLM API"""
    if not OPENAI_API_KEY or not OPENAI_BASE_URL or not OPENAI_MODEL:
        raise RuntimeError("OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL 未完整设置")

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": OPENAI_MODEL, "messages": messages, "max_tokens": 4096}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    response = requests.post(f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


# 浏览器工具定义
BROWSER_TOOLS = [
    {"type": "function", "function": {"name": "navigate", "description": "导航到指定 URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "highlight_elements", "description": "高亮所有可交互元素并返回编号列表", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "click_element", "description": "点击指定编号的元素", "parameters": {"type": "object", "properties": {"element_id": {"type": "integer"}}, "required": ["element_id"]}}},
    {"type": "function", "function": {"name": "click_text", "description": "点击包含指定文本的元素", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "get_page_text", "description": "获取页面文本", "parameters": {"type": "object", "properties": {"max_length": {"type": "integer", "default": 2000}}, "required": []}}},
    {"type": "function", "function": {"name": "scroll_down", "description": "向下滚动", "parameters": {"type": "object", "properties": {"pixels": {"type": "integer", "default": 500}}, "required": []}}},
    {"type": "function", "function": {"name": "screenshot", "description": "截图", "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}, "required": ["filename"]}}},
    {"type": "function", "function": {"name": "task_complete", "description": "标记任务完成", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "result": {"type": "string"}}, "required": ["summary"]}}},
]


class SandboxBrowserAgent:
    """基于云端沙箱的 Browser Agent"""

    def __init__(self):
        self.sandbox = None
        self.playwright = None
        self.browser = None
        self.page = None
        self.vnc_url = None

    async def start(self, timeout: int = 600):
        """创建沙箱并连接浏览器"""

        if not E2B_API_KEY or E2B_API_KEY.startswith("oak_xxx"):
            raise ValueError("E2B_API_KEY 未设置")
        if not OPENAI_API_KEY or not OPENAI_BASE_URL or not OPENAI_MODEL:
            raise ValueError("OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL 未完整设置")

        # 创建浏览器沙箱
        self.sandbox = Sandbox.create(template="browser-v1", timeout=timeout)

        # 生成 VNC 链接
        self.vnc_url = (
            f"https://{self.sandbox.get_host(9000)}/novnc/vnc_lite.html"
            f"?path=websockify&access_token={self.sandbox._envd_access_token}"
        )
        print(f"VNC: {self.vnc_url}")

        # 通过 CDP 协议连接远程浏览器
        cdp_url = f"https://{self.sandbox.get_host(9000)}/cdp"
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect_over_cdp(
            cdp_url,
            headers={"X-Access-Token": str(self.sandbox._envd_access_token)}
        )

        context = self.browser.contexts[0]
        self.page = context.pages[0] if context.pages else await context.new_page()
        return self

    async def stop(self):
        """关闭沙箱"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.sandbox:
            self.sandbox.kill()

    async def execute_tool(self, tool_name: str, params: Dict) -> str:
        """执行工具"""
        try:
            if tool_name == "navigate":
                await self.page.goto(params["url"], wait_until="domcontentloaded")
                return f"已导航到: {params['url']}"

            elif tool_name == "highlight_elements":
                elements = await self.page.evaluate('''() => {
                    document.querySelectorAll('[data-highlight-id]').forEach(el => { el.style.outline = ''; });
                    document.querySelectorAll('.highlight-label').forEach(el => el.remove());
                    const colors = { link: '#FF6B6B', button: '#4ECDC4', input: '#45B7D1', other: '#DDA0DD' };
                    const results = []; let id = 1;
                    document.querySelectorAll('a[href], button, [role="button"], input:not([type="hidden"]), textarea').forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0 || rect.top > window.innerHeight) return;
                        let type = 'other', color = colors.other;
                        if (el.tagName === 'A') { type = 'link'; color = colors.link; }
                        else if (el.tagName === 'BUTTON') { type = 'button'; color = colors.button; }
                        else if (el.tagName === 'INPUT') { type = 'input'; color = colors.input; }
                        el.style.outline = '3px solid ' + color;
                        el.setAttribute('data-highlight-id', id);
                        const label = document.createElement('div');
                        label.className = 'highlight-label';
                        label.textContent = id;
                        label.style.cssText = 'position:absolute;background:' + color + ';color:white;padding:2px 6px;border-radius:10px;font-size:12px;font-weight:bold;z-index:10000;left:' + (rect.left+window.scrollX-10) + 'px;top:' + (rect.top+window.scrollY-10) + 'px;';
                        document.body.appendChild(label);
                        results.push({ id, type, text: (el.innerText?.trim() || el.value || '').substring(0, 40) });
                        id++;
                    });
                    return results.slice(0, 30);
                }''')
                result = f"已高亮 {len(elements)} 个元素:\n"
                for el in elements[:12]:
                    emoji = {'link': '🔗', 'button': '🔘', 'input': '📝'}.get(el['type'], '⚪')
                    result += f"  [{el['id']:2d}] {emoji} {el['text'][:30]}\n"
                return result

            elif tool_name == "click_element":
                clicked = await self.page.evaluate(
                    """(id) => {
                        const el = document.querySelector(`[data-highlight-id="${id}"]`);
                        if (el) {
                            el.click();
                            return true;
                        }
                        return false;
                    }""",
                    params["element_id"],
                )
                await asyncio.sleep(0.5)
                return f"已点击元素 [{params['element_id']}]" if clicked else "未找到元素"

            elif tool_name == "click_text":
                await self.page.get_by_text(params["text"], exact=False).first.click(timeout=5000)
                return f"已点击: {params['text']}"

            elif tool_name == "get_page_text":
                text = await self.page.inner_text("body")
                return f"页面文本:\n{text[:params.get('max_length', 2000)]}..."

            elif tool_name == "scroll_down":
                await self.page.mouse.wheel(0, params.get("pixels", 500))
                return "已滚动"

            elif tool_name == "screenshot":
                await self.page.screenshot(path=params["filename"])
                return f"已截图: {params['filename']}"

            elif tool_name == "task_complete":
                return f"任务完成: {params.get('summary', '')}"

            return f"未知工具: {tool_name}"
        except Exception as e:
            return f"失败: {str(e)}"

    async def run_task(self, task: str, max_steps: int = 15) -> Dict:
        """执行多步任务"""
        system_prompt = f"""你是浏览器自动化助手。任务: {task}

工具: navigate, highlight_elements, click_element, click_text, get_page_text, scroll_down, screenshot, task_complete

策略:
1. 优先用最少步骤完成任务。
2. 当搜索结果页或目标站点页面已经明确出现“产品文档”或能确认用户要找的产品文档入口时，立即调用 task_complete，总结你找到的信息。
3. 如果 click_text 不稳定，可先 highlight_elements 再用 click_element。
4. 不要无意义重复截图或重复读取整页文本。"""

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"执行: {task}"}]
        history = []

        for step in range(1, max_steps + 1):
            print(f"[Step {step}] Current URL: {self.page.url}")
            messages.append({"role": "user", "content": f"[状态] URL: {self.page.url}"})
            response = call_llm(messages, tools=BROWSER_TOOLS)
            message = response["choices"][0]["message"]
            if message.get("content"):
                print(f"[Step {step}] LLM content: {message['content'][:200]}")
            messages.append(message)

            if "tool_calls" not in message or not message["tool_calls"]:
                print(f"[Step {step}] No tool_calls returned")
                continue

            for tc in message["tool_calls"]:
                name, params = tc["function"]["name"], json.loads(tc["function"]["arguments"])
                print(f"[Step {step}] Execute tool: {name} params={params}")
                result = await self.execute_tool(name, params)
                print(f"[Step {step}] Tool result: {result[:300]}")
                history.append({"step": step, "tool": name, "result": result})
                tool_content = result if len(result) <= 1200 else (result[:1200] + "\n...[truncated]")
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_content})

                if name == "task_complete":
                    return {"completed": True, "steps": step, "history": history}

        return {"completed": False, "steps": max_steps, "history": history}


async def main():
    """主函数"""
    agent = SandboxBrowserAgent()
    await agent.start(timeout=600)

    try:
        task = "进入百度官网，然后搜索腾讯云的Agent沙箱服务这个产品，通过点击查找产品文档。"
        result = await agent.run_task(task, max_steps=30)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
