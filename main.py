"""她自己的今天（astrbot_plugin_today）

独立插件：每天给角色几件「发生在她自己身上的小事」，让她有自己的生活，
而不是所有话题都绕着对方转。

* 按时间段抽 1~2 件（早上 / 中午 / 下午 / 晚上）
* 有冷却、有概率，只在她还没提过时注入一句，不提也完全没关系
* 对方问「在干嘛」「今天怎么样」时必定想起今天的事
* 注入走临时内容块，不改 system_prompt
"""

from __future__ import annotations

import os
import time
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .settings import DEFAULTS, Settings
from .state import SLOT_LABEL, TodayStore

PLUGIN_NAME = "astrbot_plugin_today"
API_PREFIX = f"/{PLUGIN_NAME}"

# 被问起的时候必定想起来
ASK_WORDS = (
    "在干嘛", "干嘛呢", "在做什么", "做什么呢", "忙什么", "在忙什么",
    "今天怎么样", "今天过得", "今天干嘛", "今天做什么", "今天干什么", "今天做了",
    "今儿", "今天有什么", "一天干嘛", "白天干嘛",
)

try:
    from quart import request
except Exception:  # pragma: no cover
    request = None


@register(
    PLUGIN_NAME,
    "若剑清",
    "她自己的今天：每天几件发生在她身上的小事，让她有自己的生活。",
    "0.4.0",
    "",
)
class TodayPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        data_dir = os.path.join(get_astrbot_plugin_data_path(), PLUGIN_NAME)
        self.settings = Settings(os.path.join(data_dir, "settings.json"))
        self.store = TodayStore(os.path.join(data_dir, "today.json"), self.settings.data)

        self.enabled = self._bool("enabled", True)
        self.inject_enabled = self._bool("inject_enabled", True)
        self.probability = self._float("probability", 0.15)
        self.cooldown = self._int("cooldown_minutes", 60)

        self._register_web_apis()
        snap = self.store.snapshot()
        logger.info(
            "[Today] 她自己的今天加载完成：%s，今天 %d 件小事",
            snap.get("slot_label"),
            len(snap.get("events") or []),
        )

    # ---------------- 基础 ----------------

    def _bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self.config.get(key, default))
        except Exception:
            return default

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except Exception:
            return default

    async def _json_body(self) -> dict:
        if request is None:
            return {}
        try:
            payload = await request.get_json(silent=True)
        except Exception:
            payload = None
        return payload if isinstance(payload, dict) else {}

    # ---------------- 面板 API ----------------

    def _register_web_apis(self) -> None:
        register = getattr(self.context, "register_web_api", None)
        if not callable(register):
            logger.info("[Today] 当前 AstrBot 版本不支持插件 Web API，跳过面板注册")
            return
        routes = [
            ("/today", self.api_today, ["GET"], "今天的小事"),
            ("/reroll", self.api_reroll, ["POST"], "换一批"),
            ("/add", self.api_add, ["POST"], "加一件"),
            ("/said", self.api_said, ["POST"], "标记已提起"),
            ("/pending", self.api_pending, ["POST"], "把挂着的事划掉"),
            ("/settings", self.api_settings, ["GET"], "读取参数"),
            ("/settings/save", self.api_settings_save, ["POST"], "保存参数"),
        ]
        for path, handler, methods, desc in routes:
            try:
                register(f"{API_PREFIX}{path}", handler, methods, desc)
            except Exception as exc:
                logger.warning("[Today] 注册面板 API 失败 %s: %s", path, exc)

    async def api_today(self):
        snap = self.store.snapshot()
        snap["ok"] = True
        snap["ts"] = time.time()
        return snap

    async def api_reroll(self):
        events = self.store.reroll()
        return {"ok": True, "events": events, "state": self.store.snapshot()}

    async def api_add(self):
        payload = await self._json_body()
        text = str(payload.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "内容不能为空"}
        item = self.store.add(text, str(payload.get("slot") or "") or None)
        return {"ok": True, "event": item, "state": self.store.snapshot()}

    async def api_said(self):
        payload = await self._json_body()
        event_id = str(payload.get("id") or "").strip()
        if not event_id:
            return {"ok": False, "error": "缺少 id"}
        self.store.mark_said(event_id)
        return {"ok": True, "state": self.store.snapshot()}

    async def api_pending(self):
        payload = await self._json_body()
        item_id = str(payload.get("id") or "").strip()
        if not item_id:
            return {"ok": False, "error": "缺少 id"}
        ok = self.store.done_pending(item_id)
        return {"ok": ok, "state": self.store.snapshot()}

    async def api_settings(self):
        return {"ok": True, "settings": self.settings.data, "defaults": DEFAULTS}

    async def api_settings_save(self):
        payload = await self._json_body()
        data = self.settings.update(payload)
        self.store.settings = data  # 让下一次生成就用新参数
        return {"ok": True, "settings": data}

    # ---------------- 注入 ----------------

    @filter.on_llm_request()
    async def inject_today(self, event: AstrMessageEvent, req: Any) -> None:
        if not self.enabled or not self.inject_enabled:
            return
        text = (getattr(event, "message_str", "") or "").strip()
        if text.startswith(("/今天", "今天 ")):
            return

        asked = any(word in text for word in ASK_WORDS)

        if asked:
            block = self._grounded_block()
            try:
                parts = getattr(req, "extra_user_content_parts", None)
                if not isinstance(parts, list):
                    parts = []
                    req.extra_user_content_parts = parts
                parts.append(TextPart(text=block).mark_as_temp())
            except Exception as exc:
                logger.debug("[Today] 注入失败: %s", exc)
            return

        try:
            item = self.store.due(self.probability, self.cooldown, force=False)
        except Exception as exc:
            logger.debug("[Today] 取事件失败: %s", exc)
            return
        if not item:
            return

        effect = str(item.get("effect") or "").strip()
        lines = [
            "【你今天的一件小事（你自己的日子，不是对方的事）】",
            self._slot_text(item),
        ]
        if effect:
            lines.append("这件事让你现在%s，说话会跟着变一点" % effect)
        left = self.store.open_pending()
        if left:
            lines.append("另外你还有件事没做完：%s" % left.get("text"))
        lines.append("如果对方问起、或者话题正好合适，可以顺口提一句；不提也完全没关系，别硬塞。")
        block = "\n".join(lines)
        try:
            parts = getattr(req, "extra_user_content_parts", None)
            if not isinstance(parts, list):
                parts = []
                req.extra_user_content_parts = parts
            parts.append(TextPart(text=block).mark_as_temp())
            self.store.mark_said(str(item.get("id")))
        except Exception as exc:
            logger.debug("[Today] 注入失败: %s", exc)

    @staticmethod
    def _slot_text(item: dict) -> str:
        """时段前缀 + 正文；正文已经以时段开头就不再重复。"""
        text = str(item.get("text") or "")
        label = SLOT_LABEL.get(item.get("slot", "any"), "")
        if not label or text.startswith(label):
            return text
        return label + text

    def _grounded_block(self) -> str:
        """被问今天时，把真实发生过的事全部交出来，并禁止编造。"""
        lines = ["【今天你真正做过的事（只能从这里挑，不许编）】"]
        events = self.store.events()
        if events:
            for item in events:
                effect = str(item.get("effect") or "").strip()
                line = "- " + self._slot_text(item)
                if effect:
                    line += "（当时%s）" % effect
                lines.append(line)
        else:
            lines.append("- 今天还没什么特别的，大多在发呆、写作业或者在阳台待着")
        left = self.store.open_pending()
        if left:
            lines.append("还挂着一件没做完的：%s" % left.get("text"))
        lines.append(
            "对方问的是你今天在干嘛。只能从上面这些里挑一两件说，"
            "没有的不要补，细节不要编；实在都不合适就说记不太清了。"
        )
        return "\n".join(lines)

    # ---------------- 命令 ----------------

    @filter.command("今天")
    async def today_command(self, event: AstrMessageEvent):
        """看看她今天的事：今天 / 今天 换 / 今天 加 xxx"""
        args = (getattr(event, "message_str", "") or "").strip()
        for prefix in ("/今天", "今天"):
            if args.startswith(prefix):
                args = args[len(prefix) :].strip()
                break
        action, _, rest = args.partition(" ")
        rest = rest.strip()

        if action in ("换", "重来", "reroll"):
            events = self.store.reroll()
            yield event.plain_result("换好了：\n" + "\n".join("- " + e["text"] for e in events))
            return

        if action in ("加", "add"):
            if not rest:
                yield event.plain_result("要加什么？例：今天 加 阳台的风很大")
                return
            item = self.store.add(rest)
            yield event.plain_result("记下了：" + item["text"])
            return

        events = self.store.events()
        if not events:
            yield event.plain_result("今天还没有什么特别的事。")
            return
        lines = ["今天："]
        for item in events:
            mark = "提过" if item.get("said") else "还没提"
            lines.append("· %s（%s）" % (item.get("text"), mark))
        yield event.plain_result("\n".join(lines))

    async def terminate(self) -> None:
        try:
            self.store.save()
        except Exception:
            pass
        logger.info("[Today] 她自己的今天已停止。")
