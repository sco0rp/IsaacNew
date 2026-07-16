#!/usr/bin/env python3
"""Validate Google AI Studio / Gemini connectivity for Isaac (no secrets printed)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k and k not in os.environ:
            os.environ[k] = v.strip().strip('"').strip("'")


def _key() -> str:
    return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def _get(url: str, timeout: int = 45) -> tuple[int, str]:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _post(url: str, payload: dict, timeout: int = 60) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main() -> int:
    _load_dotenv()
    key = _key()
    model = (os.getenv("GEMINI_MODEL") or "gemini-flash-lite-latest").strip()
    base = (
        os.getenv("GEMINI_BASE_URL")
        or "https://generativelanguage.googleapis.com/v1beta/models"
    ).rstrip("/")

    print(f"key_present={bool(key)} key_len={len(key)} key_prefix={key[:6]+'...' if key else '-'}")
    print(f"model={model}")
    print(f"base={base}")

    if not key:
        print("FAIL: kein GOOGLE_API_KEY / GEMINI_API_KEY")
        return 2

    status, body = _get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
    if status != 200:
        print(f"FAIL listModels status={status} body={body[:200]}")
        return 3
    models = json.loads(body).get("models") or []
    print(f"listModels=OK count={len(models)}")

    url = f"{base}/{model}:generateContent?key={key}"
    payload = {
        "systemInstruction": {"parts": [{"text": "Du bist Isaac. Antworte mit einem Wort."}]},
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 256, "temperature": 0.1},
    }
    status, body = _post(url, payload)
    if status == 200:
        data = json.loads(body)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            texts = [
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and p.get("thought") is not True and p.get("text")
            ]
            text = "".join(texts).strip() or "<empty>"
        except Exception:
            text = "<parse-error>"
        print(f"generateContent=OK model={model} reply={text!r}"[:200])
        return 0

    snippet = body[:240].replace("\n", " ")
    print(f"generateContent=FAIL status={status} body={snippet}")
    if status == 429:
        print("HINT: Free-Tier-Quota erschöpft — Billing in AI Studio / Cloud aktivieren oder warten.")
        print("      https://ai.dev/rate-limit  |  https://aistudio.google.com/")
        return 4
    if status == 404:
        print("HINT: Modell für diesen Key nicht verfügbar — GEMINI_MODEL anpassen.")
        print("      Empfohlen: gemini-flash-lite-latest (Stand 2026-07)")
        return 5
    return 6


if __name__ == "__main__":
    sys.exit(main())
