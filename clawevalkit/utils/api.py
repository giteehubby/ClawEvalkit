"""统一的 LLM API 调用接口。

call_llm() 支持 ARK / GPT Proxy / OpenRouter 三个 provider，
使用 urllib 实现，无需额外依赖。
"""
import json
import ssl
import time
import urllib.request


def call_llm(messages: list, config: dict, max_tokens: int = 4096, timeout: float = 120) -> str:
    """调用 /chat/completions API，返回回复文本。

    参数:
        messages: OpenAI 格式的消息列表 [{"role": ..., "content": ...}]
        config: 包含 api_url, api_key, model 的字典 (由 get_api_config 返回)
        max_tokens: 最大生成 token 数
        timeout: 单次请求超时秒数
    返回: LLM 回复的纯文本 (str)
    """
    api_url = f"{config['api_url'].rstrip('/')}/chat/completions"
    payload = {
        "model": config["model"],
        "max_tokens": max_tokens,
        "messages": messages,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
        except Exception as exc:
            if attempt >= 2:
                return f"ERROR: {exc}"
            time.sleep(2 * (2 ** attempt))
    return ""
