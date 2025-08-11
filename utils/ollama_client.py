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
    return any(m.lower()==name for m in list_models(timeout))

def stream_chat(model: str, messages: list, connect_timeout=5, read_timeout=300):
    url = f"{BASE}/api/chat"
    headers = {"Content-Type":"application/json"}
    data = {"model": model, "messages": messages}
    r = requests.post(url, json=data, headers=headers, stream=True, timeout=(connect_timeout, read_timeout))
    r.raise_for_status()
    decoder = codecs.getincrementaldecoder('utf-8')()
    buf = ""
    for chunk in r.iter_content(chunk_size=None):
        text = decoder.decode(chunk)
        if not text:
            continue
        buf += text
        while True:
            if "\n" not in buf:
                break
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
                # 容错：有些实现可能不是严格 JSONL
                yield line
    tail = decoder.decode(b"", final=True)
    if tail:
        yield tail