# utils/ollama_client.py  v9.5
import requests, codecs, json

BASE = "http://localhost:11434"

def is_alive(timeout=0.5):
    try:
        requests.get(f"{BASE}/api/version", timeout=timeout)
        return True
    except requests.RequestException:
        return False

def list_models(timeout=2):
    try:
        r = requests.get(f"{BASE}/api/tags", timeout=timeout)
        if r.ok:
            return [m.get("name", "") for m in r.json().get("models", [])]
    except requests.RequestException:
        pass
    return []

def has_model(name: str, timeout=2):
    name = (name or "").lower()
    return any(m.lower() == name for m in list_models(timeout))

def get_model_info(name: str, timeout=3) -> dict:
    """
    调用 /api/show 获取模型 modelfile，
    返回字典；失败时返回 {}。
    """
    try:
        r = requests.post(
            f"{BASE}/api/show",
            json={"name": name},
            timeout=timeout,
        )
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return {}

def is_vision_model(name: str, timeout=3) -> bool:
    """
    优先用 /api/show 的 modelfile 判断是否为视觉模型；
    失败时回退到名字关键字匹配。
    """
    # 1) 尝试 API 检测
    try:
        info = get_model_info(name, timeout=timeout)
        modelfile = info.get("modelfile", "") or ""
        # Ollama modelfile 中视觉模型通常含 "vision" 或 "multimodal"
        if any(k in modelfile.lower() for k in ("vision", "multimodal", "image")):
            return True
        # 部分模型在 details.families 中标注
        families = info.get("details", {}).get("families", []) or []
        if any("vision" in f.lower() or "clip" in f.lower() for f in families):
            return True
    except Exception:
        pass

    # 2) 回退：名字关键字匹配（扩充至 2025 年主流视觉模型）
    return _is_vision_model_name(name)

def _is_vision_model_name(name: str) -> bool:
    n = (name or "").lower().replace("-", "").replace("_", "").replace(".", "")
    keys = (
        # 经典视觉模型
        "llava", "bakllava", "llavaphi", "phi3vision", "phi4vision",
        "moondream", "nanollava",
        # Qwen 系列
        "qwen2vl", "qwenvl",
        # MiniCPM / InternVL / GLM
        "minicpmv", "internvl", "glm4v",
        # LLaMA 视觉
        "llama32vision", "llama3vision",
        # Gemma 视觉
        "gemma3", "paligemma",
        # 其他常见
        "cogvlm", "cogvlm2",
        "idefics",
        "pixtral",
        "molmo",
        "janus",
        "florence",
        "deepseekvl",
        "smolvlm",
        "mistralpixel",
    )
    return any(k in n for k in keys)

def stream_chat(model: str, messages: list, connect_timeout=5, read_timeout=300):
    url = f"{BASE}/api/chat"
    headers = {"Content-Type": "application/json"}
    data = {"model": model, "messages": messages}
    r = requests.post(
        url, json=data, headers=headers,
        stream=True, timeout=(connect_timeout, read_timeout),
    )
    r.raise_for_status()
    decoder = codecs.getincrementaldecoder("utf-8")()
    buf = ""
    for chunk in r.iter_content(chunk_size=None):
        text = decoder.decode(chunk)
        if not text:
            continue
        buf += text
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                content = obj.get("message", {}).get("content", "")
                if content:
                    yield content
            except Exception:
                yield line
    tail = decoder.decode(b"", final=True)
    if tail:
        yield tail
