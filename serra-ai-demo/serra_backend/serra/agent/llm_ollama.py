"""Client per un LLM open source locale via Ollama (facoltativo).

Stessa interfaccia di MockLLM. Per usarlo:
  1. installare Ollama (https://ollama.com) e scaricare un modello con tool calling,
     es. `ollama pull qwen2.5:3b` (~2 GB, adatto a un Mac con 8 GB di RAM);
  2. avviare il backend con LLM_MODE=ollama (ed eventualmente OLLAMA_MODEL=...).
Nessuna chiave API: il modello gira in locale.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request


class OllamaLLM:
    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
        self.host = host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.name = f"{self.model} (Ollama locale)"

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        clean = []
        for m in messages:
            m2 = {k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "name")}
            clean.append(m2)
        body = json.dumps({"model": self.model, "messages": clean, "tools": tools, "stream": False,
                           "options": {"temperature": 0.2}}).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        msg = data["message"]
        for i, tc in enumerate(msg.get("tool_calls") or []):
            tc.setdefault("id", f"call_{len(messages)}_{i}")
            tc.setdefault("type", "function")
        return {"model": self.name, "message": msg, "done": True,
                "eval_count": data.get("eval_count", 0), "prompt_eval_count": data.get("prompt_eval_count", 0),
                "total_duration_ms": int((time.time() - t0) * 1000)}
