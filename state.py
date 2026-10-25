"""她自己的今天：每天几件发生在她身上的小事。

独立插件，不读也不改其它插件的数据。

* 每天按时间段抽 1~2 件「今天的事」：早上/中午/下午/晚上各有一池
* 只在她还没提过、且冷却时间到了的时候注入一句，不提也完全没关系
* 对方问「在干嘛」「今天怎么样」时必然会想起今天的事
"""

from __future__ import annotations

import json
import os
import random
import time

SLOTS = ["morning", "noon", "afternoon", "evening", "night"]

SLOT_LABEL = {
    "morning": "早上",
    "noon": "中午",
    "afternoon": "下午",
    "evening": "晚上",
    "night": "夜里",
}

POOLS: dict[str, list[dict]] = {
    "morning": [
        {"text": "早上起晚了，差点没赶上第一节课", "kind": "school"},
        {"text": "早餐吃的是昨天剩的面包", "kind": "life"},
        {"text": "阳台那盆月季今天早开了一朵", "kind": "flower"},
        {"text": "路上遇到隔壁的猫，蹭了我一下", "kind": "life"},
        {"text": "今天穿少了，出门就打哆嗦", "kind": "life"},
        {"text": "早读的时候一直在打哈欠", "kind": "school"},
        {"text": "早饭没吃完就出门了，现在有点饿", "kind": "life"},
    ],
    "noon": [
        {"text": "中午食堂排了很久的队", "kind": "school"},
        {"text": "午休没睡着，一直看窗外", "kind": "life"},
        {"text": "数学小测发下来了，比估的分高两分", "kind": "school"},
        {"text": "同桌把耳机借走了，到现在还没还", "kind": "school"},
        {"text": "中午太阳很好，晒得被子很暖", "kind": "life"},
        {"text": "午饭吃太快，现在有点撑", "kind": "life"},
    ],
    "afternoon": [
        {"text": "体育课跑了两圈，腿有点软", "kind": "school"},
        {"text": "老师拖堂拖到下课铃响完", "kind": "school"},
        {"text": "画了半张速写，手一直抖", "kind": "flower"},
        {"text": "阳台的土有点干，浇了水", "kind": "flower"},
        {"text": "下午风很大，窗户一直响", "kind": "life"},
        {"text": "自习课把作业写完了，剩下的时间在发呆", "kind": "school"},
    ],
    "evening": [
        {"text": "晚上在阳台坐了一会儿，风挺凉", "kind": "flower"},
        {"text": "看了两集番，剧情有点拖", "kind": "life"},
        {"text": "打了会儿游戏，输得挺惨", "kind": "life"},
        {"text": "洗完澡发现头发还没干", "kind": "life"},
        {"text": "晚饭吃的是面，汤有点咸", "kind": "life"},
        {"text": "把书架上落灰的一本翻出来了", "kind": "life"},
    ],
    "night": [
        {"text": "有点困了，但还不想睡", "kind": "life"},
        {"text": "在想要不要明天早点起", "kind": "life"},
        {"text": "翻了几页书，看着看着走神了", "kind": "life"},
        {"text": "晚上降温了，窗户没关严", "kind": "life"},
        {"text": "在床上躺着，脑子里在想一些没用的", "kind": "life"},
    ],
    "any": [
        {"text": "今天降温了，手指有点僵", "kind": "life"},
        {"text": "下了一天雨，窗户一直是湿的", "kind": "life"},
        {"text": "太阳很好，把被子拿出去晒了", "kind": "life"},
        {"text": "楼道里的灯坏了一盏，走的时候有点怕", "kind": "life"},
    ],
}

MAX_DAYS = 14


def slot_of(now: float | None = None) -> str:
    hour = time.localtime(now or time.time()).tm_hour
    if 5 <= hour < 10:
        return "morning"
    if 10 <= hour < 13:
        return "noon"
    if 13 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


class TodayStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.data: dict = {"days": {}}
        self.load()

    # ---------------- 持久化 ----------------

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        days = raw.get("days") if isinstance(raw, dict) else {}
        self.data = {"days": days if isinstance(days, dict) else {}}

    def save(self) -> None:
        days = self.data.get("days", {})
        if len(days) > MAX_DAYS:
            for key in sorted(days)[:-MAX_DAYS]:
                days.pop(key, None)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---------------- 当天 ----------------

    @staticmethod
    def day_key(now: float | None = None) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(now or time.time()))

    def _day(self, now: float | None = None) -> dict:
        key = self.day_key(now)
        days = self.data.setdefault("days", {})
        day = days.get(key)
        if not isinstance(day, dict):
            day = {"events": [], "created_at": time.time(), "last_inject": 0}
            days[key] = day
        day.setdefault("events", [])
        day.setdefault("last_inject", 0)
        return day

    def ensure(self, now: float | None = None) -> dict:
        """当天还没事就生成 1~2 件。"""
        now = now or time.time()
        day = self._day(now)
        if day["events"]:
            return day
        current = SLOTS.index(slot_of(now))
        allowed = [s for s in SLOTS[: current + 1]] + ["any"]
        picked: list[dict] = []
        count = random.choice([1, 2])
        for _ in range(count):
            slot = random.choice(allowed)
            pool = POOLS.get(slot) or POOLS["any"]
            candidate = random.choice(pool)
            if any(item["text"] == candidate["text"] for item in picked):
                continue
            picked.append(
                {
                    "id": "%d" % int(time.time() * 1000) + str(len(picked)),
                    "text": candidate["text"],
                    "kind": candidate.get("kind", "life"),
                    "slot": slot,
                    "at": now,
                    "said": False,
                    "said_at": 0,
                }
            )
        day["events"] = picked
        day["created_at"] = now
        self.save()
        return day

    def events(self) -> list[dict]:
        return list(self._day().get("events") or [])

    def reroll(self) -> list[dict]:
        day = self._day()
        day["events"] = []
        day["last_inject"] = 0
        self.save()
        return self.ensure()["events"]

    def add(self, text: str, slot: str | None = None) -> dict:
        day = self._day()
        item = {
            "id": "%d" % int(time.time() * 1000) + str(len(day["events"])),
            "text": str(text or "").strip()[:120],
            "kind": "custom",
            "slot": slot if slot in POOLS else slot_of(),
            "at": time.time(),
            "said": False,
            "said_at": 0,
        }
        day["events"].append(item)
        self.save()
        return item

    def mark_said(self, event_id: str) -> None:
        now = time.time()
        for item in self._day().get("events") or []:
            if item.get("id") == event_id:
                item["said"] = True
                item["said_at"] = now
        self._day()["last_inject"] = now
        self.save()

    # ---------------- 取一件该说的 ----------------

    def due(self, probability: float = 0.15, cooldown_minutes: int = 60, force: bool = False) -> dict | None:
        now = time.time()
        day = self.ensure(now)
        if now - float(day.get("last_inject") or 0) < cooldown_minutes * 60 and not force:
            return None
        current = SLOTS.index(slot_of(now))
        pending = [
            item
            for item in day.get("events") or []
            if not item.get("said")
            and (
                item.get("slot") == "any"
                or SLOTS.index(item.get("slot", "morning")) <= current
            )
        ]
        if not pending:
            return None
        if not force and random.random() > probability:
            return None
        day["last_inject"] = now  # 取走即占冷却
        self.save()
        return pending[0]

    def history(self, days: int = 7) -> list[dict]:
        out = []
        for key in sorted(self.data.get("days", {}))[-days:]:
            day = self.data["days"][key]
            out.append(
                {
                    "date": key,
                    "events": [
                        {"text": e.get("text"), "said": bool(e.get("said")), "kind": e.get("kind")}
                        for e in day.get("events") or []
                    ],
                }
            )
        return out

    def snapshot(self) -> dict:
        day = self.ensure()
        return {
            "date": self.day_key(),
            "slot": slot_of(),
            "slot_label": SLOT_LABEL.get(slot_of(), ""),
            "events": [
                {
                    "id": e.get("id"),
                    "text": e.get("text"),
                    "kind": e.get("kind"),
                    "slot": e.get("slot"),
                    "slot_label": SLOT_LABEL.get(e.get("slot", ""), ""),
                    "said": bool(e.get("said")),
                }
                for e in day.get("events") or []
            ],
            "last_inject": day.get("last_inject") or 0,
            "history": self.history(7),
        }
