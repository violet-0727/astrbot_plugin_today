"""她自己的今天：面板可调的参数。"""

from __future__ import annotations

import json
import os

DEFAULTS = {
    "max_events": 4,            # 每天最多几件事
    "accident_probability": 0.08,  # 每天出现一次小意外的概率
    "day_tone_enabled": True,   # 是否掷「今天是什么日子」
    "lucky_probability": 0.03,  # 顺的一天
    "unlucky_probability": 0.01,  # 倒霉的一天
    "weighted": True,           # 按稀有度权重抽，而不是等概率
}

RULES = {
    "max_events": (1, 8, int),
    "accident_probability": (0.0, 0.5, float),
    "lucky_probability": (0.0, 0.2, float),
    "unlucky_probability": (0.0, 0.2, float),
}


def _clean(data: dict) -> dict:
    out = dict(DEFAULTS)
    for key, (low, high, typ) in RULES.items():
        try:
            value = typ((data or {}).get(key, DEFAULTS[key]))
        except Exception:
            value = DEFAULTS[key]
        out[key] = max(low, min(high, value))
    for key in ("day_tone_enabled", "weighted"):
        raw = (data or {}).get(key, DEFAULTS[key])
        if isinstance(raw, str):
            out[key] = raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            out[key] = bool(raw)
    return out


class Settings:
    def __init__(self, path: str) -> None:
        self.path = path
        self.data = dict(DEFAULTS)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.load()

    def load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = _clean(json.load(f))
        except FileNotFoundError:
            self.data = dict(DEFAULTS)
            self.save()
        except Exception:
            self.data = dict(DEFAULTS)
        return self.data

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def update(self, payload: dict) -> dict:
        merged = dict(self.data)
        merged.update(payload or {})
        self.data = _clean(merged)
        self.save()
        return self.data
