"""Avisos al celular (ntfy y/o Telegram). Si fallan, no detienen la corrida."""
from __future__ import annotations

import json
import os
import urllib.request


def avisar(cfg: dict, titulo: str, texto: str, urgente: bool = False):
    a = cfg.get("avisos", {})
    if a.get("ntfy"):
        try:
            req = urllib.request.Request(a["ntfy"], data=texto.encode(), method="POST",
                                         headers={"Title": titulo.encode("utf-8").decode("latin-1", "ignore"),
                                                  "Priority": "high" if urgente else "default",
                                                  "Tags": "repeat"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    token = os.environ.get(a.get("telegram_token_env") or "", "")
    if token and a.get("telegram_chat"):
        try:
            datos = json.dumps({"chat_id": a["telegram_chat"], "text": f"{titulo}\n\n{texto}"[:4000]}).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=datos,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
