"""DeepSeek 大模型客户端与通用 Agent 执行循环。"""

import json
import os

import requests

from .config import load_dotenv

load_dotenv()

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
MODEL_PRO = os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro").strip()
TIMEOUT = 600


class LlmError(RuntimeError):
    pass


def chat(messages, temperature=0.7, max_tokens=384000, tools=None, json_mode=False, model=None):
    """调用 DeepSeek Chat Completions,返回 message 字典。"""
    if not API_KEY:
        raise LlmError("未配置 DEEPSEEK_API_KEY,请在项目根目录 .env 中填写")

    payload = {
        "model": model or MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    url = f"{BASE_URL}/chat/completions"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise LlmError(f"无法连接 DeepSeek API: {exc}") from exc

    if resp.status_code != 200:
        raise LlmError(f"DeepSeek API 返回错误 {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    return data["choices"][0]["message"]


def parse_json_text(text):
    """从模型输出中稳健地解析 JSON(兼容代码块与前后缀文本)。"""
    if not text:
        raise LlmError("模型返回为空,无法解析 JSON")
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        t = t[start : end + 1]
    return json.loads(t)


def chat_json(messages, temperature=0.3, max_tokens=384000, model=None):
    """请求 JSON 输出;若模型不支持 response_format 则降级为文本解析。"""
    try:
        msg = chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True, model=model)
        return parse_json_text(msg.get("content") or "")
    except (LlmError, json.JSONDecodeError):
        msg = chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=False, model=model)
        return parse_json_text(msg.get("content") or "")


TOOL_REGISTRY = {}
MAX_TOOL_CALLS = int(os.environ.get("AGENT_MAX_TOOL_CALLS", "30"))
TOOL_CAPS = {
    "verified_search": int(os.environ.get("TOOL_CAP_VERIFIED_SEARCH", "10")),
    "fetch_page": int(os.environ.get("TOOL_CAP_FETCH_PAGE", "8")),
    "bilibili_search": int(os.environ.get("TOOL_CAP_BILIBILI", "14")),
    "render_page": int(os.environ.get("TOOL_CAP_RENDER_PAGE", "6")),
    "find_recruitment_links": int(os.environ.get("TOOL_CAP_FIND_RECRUIT", "3")),
    "parse_pdf": int(os.environ.get("TOOL_CAP_PARSE_PDF", "4")),
}


def register_tool(fn):
    TOOL_REGISTRY[fn.__name__] = fn
    return fn


def _describe_tool(name, args):
    """把工具调用翻译成用户可读的过程文案。"""
    if name == "verified_search":
        return "正在核实并搜索:" + str(args.get("query", ""))
    if name == "fetch_page":
        return "正在读取网页:" + str(args.get("url", ""))
    if name == "bilibili_search":
        return "正在搜索B站视频:" + str(args.get("query", ""))
    if name == "find_recruitment_links":
        return "正在发掘招聘入口:" + str(args.get("company", ""))
    if name == "parse_pdf":
        return "正在识别PDF:" + str(args.get("filename", ""))
    return "调用工具:" + name


def run_agent(system, user, tools=None, max_steps=6, temperature=0.7, max_tokens=384000,
              on_process=None, model=None):
    """通用 Agent 循环:模型可反复调用工具,直到给出最终回答。"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    total_calls = 0
    tool_counts = {}

    def process(text):
        if on_process:
            on_process(text)

    def _force_finish(tip_content):
        """停止工具调用,强制模型基于现有信息给出最终回答。"""
        messages.append(
            {
                "role": "user",
                "content": "已收集到足够信息。请停止调用任何工具,直接基于现有信息输出你的最终完整回答。",
            }
        )
        try:
            final_msg = chat(messages, temperature=temperature, max_tokens=max_tokens, tools=None, model=model)
            return final_msg.get("content") or tip_content
        except Exception as exc:
            print(f"[agent] 强制收尾失败,返回已有内容: {exc}")
            return tip_content

    for step in range(max_steps):
        msg = chat(messages, temperature=temperature, max_tokens=max_tokens, tools=tools, model=model)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            reasoning = msg.get("reasoning_content") or ""
            if reasoning:
                process("思考:" + reasoning[:200])
            content = msg.get("content") or ""
            if content:
                return content
            # 推理模型可能把 token 预算全花在“思考”,content 为空导致用户看不到回答。
            # 此时强制收尾一次,要求模型直接输出最终文本。
            return _force_finish("")
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            process("思考:" + reasoning[:200])
        names = [c.get("function", {}).get("name", "") for c in tool_calls]
        would_exceed = total_calls + len(tool_calls) > MAX_TOOL_CALLS or any(
            tool_counts.get(n, 0) + names.count(n) > TOOL_CAPS.get(n, 10**9)
            for n in set(names)
        )
        if would_exceed:
            print(f"[agent] 工具调用达到上限(总量{total_calls + len(tool_calls)}/{MAX_TOOL_CALLS}, {tool_counts}),强制收尾")
            process("信息收集完成,正在整理最终回答…")
            return _force_finish(msg.get("content") or "")
        messages.append(msg)
        total_calls += len(tool_calls)
        for n in names:
            tool_counts[n] = tool_counts.get(n, 0) + 1
        if msg.get("content"):
            print(f"[agent] 第{step + 1}步:模型边回答边调用工具: {names}")
            process("思考:" + (msg.get("content") or "")[:200])
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            process(_describe_tool(name, args))
            print(f"[agent] 第{step + 1}步调用工具: {name}")
            handler = TOOL_REGISTRY.get(name)
            if handler is None:
                result = {"error": f"未知工具: {name}"}
            else:
                try:
                    result = handler(**args)
                except Exception as exc:
                    result = {"error": str(exc)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False)[:8000],
                }
            )
    # 步数耗尽仍未给出最终答案:强制收尾
    print(f"[agent] 达到最大步数({max_steps}),强制收尾")
    process("信息收集完成,正在整理最终回答…")
    return _force_finish(messages[-1].get("content") or "")
