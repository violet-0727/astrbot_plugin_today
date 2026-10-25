"""她自己的今天 v0.2：有因果、能跨天、贴人设。

* 工作日偏学校，周末偏家里：事件池按「星期几」筛
* 事件串成链：起晚了 → 没吃早饭 → 中午吃太急（读起来是一天，不是随机条）
* 跨天连续：昨天没做完的事今天还挂着；阳台的月季会一天天开
* 每件事带 effect：注入时一起给她，让语气跟着变
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

# ---------------- 长线：会跨天变化的东西 ----------------

THREADS = [
    {
        "key": "rose",
        "name": "阳台那盆月季",
        "stages": [
            "还是花苞，看不出颜色",
            "开了一朵，粉白色",
            "开了三朵，风一吹就晃",
            "开始谢了，花瓣掉在土上",
            "彻底谢了，剪掉了残花",
        ],
        "text": "{name}{stage}",
        "effect": "心里很安静",
    },
    {
        "key": "exam",
        "name": "下个月的月考",
        "stages": ["还没开始复习", "翻了翻课本", "做了两套卷子", "开始有点着急了"],
        "text": "{name}：{stage}",
        "effect": "有点压着",
    },
]

# ---------------- 事件链 ----------------

CHAINS = [
    {
        "id": "late",
        "day": "weekday",
        "steps": [
            {"slot": "morning", "text": "早上起晚了，差点没赶上第一节课", "effect": "有点慌"},
            {"slot": "morning", "text": "没顾上吃早饭，第二节课就开始饿", "effect": "有点饿"},
            {
                "slot": "noon",
                "text": "中午吃得特别急，下午一直有点撑",
                "effect": "有点不舒服",
                "pending": "中午吃太急，晚饭想清淡一点",
            },
        ],
    },
    {
        "id": "exam",
        "day": "weekday",
        "steps": [
            {"slot": "noon", "text": "数学小测发下来了，比估的分低了几分", "effect": "有点闷"},
            {
                "slot": "afternoon",
                "text": "把错的题重新算了一遍，发现是抄错数",
                "effect": "有点懊恼",
                "pending": "错题还没整理到本子上",
            },
        ],
    },
    {
        "id": "class",
        "day": "weekday",
        "steps": [
            {"slot": "afternoon", "text": "体育课跑了两圈，腿有点软", "effect": "有点累"},
            {
                "slot": "evening",
                "text": "晚上写作业的时候一直犯困",
                "effect": "有点困",
                "pending": "作业还差两页没写完",
            },
        ],
    },
    {
        "id": "paint",
        "day": "weekend",
        "steps": [
            {"slot": "morning", "text": "周末早起，把阳台的花都浇了一遍", "effect": "心情不错"},
            {
                "slot": "afternoon",
                "text": "在阳台画了半张速写，光一直变",
                "effect": "很专注",
                "pending": "那张速写还没画完，想明天接着画",
            },
        ],
    },
    {
        "id": "game",
        "day": "weekend",
        "steps": [
            {"slot": "afternoon", "text": "打了会儿游戏，连着输了两把", "effect": "有点上头"},
            {"slot": "evening", "text": "不服气又打了一把，赢了，心情好回来", "effect": "心情不错"},
        ],
    },
    {
        "id": "rain",
        "day": "any",
        "steps": [
            {"slot": "any", "text": "下了一天雨，窗户一直是湿的", "effect": "有点懒"},
            {"slot": "evening", "text": "雨停了，空气里有那种湿土的味道", "effect": "很安静"},
        ],
    },
]

# ---------------- 单件事 ----------------

POOLS: list[dict] = [
    {"day": "weekday", "slot": "morning", "text": "早读一直在打哈欠", "effect": "有点困"},
    {"day": "weekday", "slot": "morning", "text": "今天穿少了，出门就打哆嗦", "effect": "有点冷"},
    {"day": "weekday", "slot": "noon", "text": "食堂排了很久的队，最后吃的还是那几样", "effect": "有点无奈"},
    {"day": "weekday", "slot": "noon", "text": "同桌把耳机借走了，到现在还没还", "effect": "有点介意"},
    {"day": "weekday", "slot": "afternoon", "text": "老师拖堂拖到下课铃响完", "effect": "有点烦"},
    {"day": "weekday", "slot": "afternoon", "text": "自习课把作业写完了一半", "effect": "有点轻松"},
    {"day": "weekday", "slot": "evening", "text": "晚自习后走回家，路上没什么人", "effect": "有点困"},
    {"day": "weekend", "slot": "morning", "text": "早饭煮了面，汤有点咸", "effect": "心情不错"},
    {"day": "weekend", "slot": "morning", "text": "睡到自然醒，太阳已经照到床上了", "effect": "很放松"},
    {"day": "weekend", "slot": "afternoon", "text": "阳台的土有点干，浇了水", "effect": "很安静"},
    {"day": "weekend", "slot": "afternoon", "text": "看了两集番，剧情有点拖", "effect": "有点走神"},
    {"day": "weekend", "slot": "evening", "text": "晚上在阳台坐了一会儿，风挺凉", "effect": "很安静"},
    {"day": "weekend", "slot": "evening", "text": "把书架上落灰的一本翻出来了", "effect": "有点好奇"},
    {"day": "any", "slot": "any", "text": "今天降温了，手指有点僵", "effect": "有点冷"},
    {"day": "any", "slot": "any", "text": "路上遇到隔壁的猫，蹭了我一下", "effect": "心情不错"},
    {"day": "any", "slot": "any", "text": "楼道里的灯坏了一盏，走的时候有点怕", "effect": "有点怕"},
    {"day": "any", "slot": "night", "text": "有点困了，但还不想睡", "effect": "有点困"},
    {"day": "any", "slot": "night", "text": "翻了几页书，看着看着走神了", "effect": "很安静"},
    {"day": "any", "slot": "night", "text": "在床上躺着，脑子里在想一些没用的", "effect": "有点放空"},
]

MAX_DAYS = 14
MAX_EVENTS = 4


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


def day_kind(now: float | None = None) -> str:
    wd = time.localtime(now or time.time()).tm_wday
    return "weekend" if wd >= 5 else "weekday"


def day_key(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now or time.time()))


class TodayStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.data: dict = {"days": {}, "threads": {}}
        self.load()

    # ---------------- 持久化 ----------------

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        days = raw.get("days")
        threads = raw.get("threads")
        self.data = {
            "days": days if isinstance(days, dict) else {},
            "threads": threads if isinstance(threads, dict) else {},
        }

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

    def _day(self, now: float | None = None) -> dict:
        key = day_key(now)
        days = self.data.setdefault("days", {})
        day = days.get(key)
        if not isinstance(day, dict):
            day = {
                "events": [],
                "pending": [],
                "created_at": time.time(),
                "last_inject": 0,
                "kind": day_kind(now),
            }
            days[key] = day
        day.setdefault("events", [])
        day.setdefault("pending", [])
        day.setdefault("last_inject", 0)
        return day

    def _yesterday(self, now: float | None = None) -> dict | None:
        today = day_key(now)
        earlier = [k for k in sorted(self.data.get("days", {})) if k < today]
        if not earlier:
            return None
        return self.data["days"].get(earlier[-1])

    def _advance_threads(self, now: float | None = None) -> list[dict]:
        """跨天的长线：月季会开，月考会近。"""
        today = day_key(now)
        made = []
        for spec in THREADS:
            state = self.data.setdefault("threads", {}).setdefault(
                spec["key"], {"stage": 0, "day": ""}
            )
            if state.get("day") == today:
                continue
            last = state.get("day") or ""
            advance = not last
            if not advance:
                try:
                    gap = time.mktime(time.strptime(today, "%Y-%m-%d")) - time.mktime(
                        time.strptime(last, "%Y-%m-%d")
                    )
                except Exception:
                    gap = 86400
                if spec["key"] == "rose":
                    advance = gap >= 2 * 86400
                elif spec["key"] == "exam":
                    advance = gap >= 5 * 86400
            if advance:
                stage = min(int(state.get("stage") or 0) + 1, len(spec["stages"]) - 1)
                state["stage"] = stage
                state["day"] = today
                made.append(
                    {
                        "text": spec["text"].format(
                            name=spec["name"], stage=spec["stages"][stage]
                        ),
                        "kind": spec["key"],
                        "effect": spec.get("effect", ""),
                        "slot": "any",
                    }
                )
        return made

    def ensure(self, now: float | None = None) -> dict:
        now = now or time.time()
        day = self._day(now)
        if day["events"]:
            return day

        kind = day_kind(now)
        current = SLOTS.index(slot_of(now))
        events: list[dict] = []

        events.extend(self._advance_threads(now))

        chains = [c for c in CHAINS if c["day"] in (kind, "any")]
        if chains:
            chain = random.choice(chains)
            for step in chain["steps"]:
                slot = step.get("slot", "any")
                if slot != "any" and SLOTS.index(slot) > current:
                    continue
                events.append(
                    {
                        "text": step["text"],
                        "kind": "chain",
                        "effect": step.get("effect", ""),
                        "slot": slot,
                    }
                )
                if step.get("pending"):
                    day["pending"].append(
                        {
                            "id": "%d" % int(now * 1000) + str(len(day["pending"])),
                            "text": step["pending"],
                            "done": False,
                            "carried": False,
                        }
                    )

        pool = [p for p in POOLS if p["day"] in (kind, "any")]
        random.shuffle(pool)
        for item in pool:
            if len(events) >= MAX_EVENTS:
                break
            slot = item.get("slot", "any")
            if slot != "any" and SLOTS.index(slot) > current:
                continue
            if any(e["text"] == item["text"] for e in events):
                continue
            events.append(
                {
                    "text": item["text"],
                    "kind": item.get("kind", "life"),
                    "effect": item.get("effect", ""),
                    "slot": slot,
                }
            )

        y = self._yesterday(now)
        if y:
            for item in y.get("pending") or []:
                if item.get("done"):
                    continue
                day["pending"].append(
                    {
                        "id": "%d" % int(now * 1000) + "c" + str(len(day["pending"])),
                        "text": item.get("text", ""),
                        "done": False,
                        "carried": True,
                    }
                )

        for idx, item in enumerate(events):
            item["id"] = "%d" % int(now * 1000) + str(idx)
            item["said"] = False
            item["said_at"] = 0

        day["events"] = events[:MAX_EVENTS]
        day["created_at"] = now
        day["kind"] = kind
        self.save()
        return day

    def events(self) -> list[dict]:
        return list(self._day().get("events") or [])

    def pending(self) -> list[dict]:
        return list(self._day().get("pending") or [])

    def done_pending(self, item_id: str) -> bool:
        for item in self._day().get("pending") or []:
            if item.get("id") == item_id:
                item["done"] = True
                self.save()
                return True
        return False

    def reroll(self) -> list[dict]:
        key = day_key()
        days = self.data.setdefault("days", {})
        day = days.get(key) or {}
        day["events"] = []
        day["pending"] = [p for p in (day.get("pending") or []) if p.get("carried")]
        day["last_inject"] = 0
        days[key] = day
        self.save()
        return self.ensure()["events"]

    def add(self, text: str, slot: str | None = None) -> dict:
        day = self._day()
        item = {
            "id": "%d" % int(time.time() * 1000) + str(len(day["events"])),
            "text": str(text or "").strip()[:120],
            "kind": "custom",
            "effect": "",
            "slot": slot if slot in SLOT_LABEL else slot_of(),
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

    # ---------------- 该说的话 ----------------

    def due(
        self,
        probability: float = 0.15,
        cooldown_minutes: int = 60,
        force: bool = False,
    ) -> dict | None:
        now = time.time()
        day = self.ensure(now)
        if now - float(day.get("last_inject") or 0) < cooldown_minutes * 60 and not force:
            return None
        current = SLOTS.index(slot_of(now))
        waiting = [
            item
            for item in day.get("events") or []
            if not item.get("said")
            and (item.get("slot") == "any" or SLOTS.index(item.get("slot", "morning")) <= current)
        ]
        if not waiting:
            return None
        if not force and random.random() > probability:
            return None
        day["last_inject"] = now
        self.save()
        return waiting[0]

    def open_pending(self) -> dict | None:
        for item in self._day().get("pending") or []:
            if not item.get("done"):
                return item
        return None

    # ---------------- 面板 ----------------

    def history(self, days: int = 7) -> list[dict]:
        out = []
        for key in sorted(self.data.get("days", {}))[-days:]:
            day = self.data["days"][key]
            out.append(
                {
                    "date": key,
                    "kind": day.get("kind", ""),
                    "events": [
                        {"text": e.get("text"), "said": bool(e.get("said")), "slot": e.get("slot")}
                        for e in day.get("events") or []
                    ],
                    "pending": [
                        {"text": p.get("text"), "done": bool(p.get("done"))}
                        for p in day.get("pending") or []
                    ],
                }
            )
        return out

    def threads_view(self) -> list[dict]:
        out = []
        for spec in THREADS:
            state = self.data.get("threads", {}).get(spec["key"]) or {}
            stage = int(state.get("stage") or 0)
            out.append(
                {
                    "key": spec["key"],
                    "name": spec["name"],
                    "stage": spec["stages"][min(stage, len(spec["stages"]) - 1)],
                    "index": stage,
                    "total": len(spec["stages"]) - 1,
                }
            )
        return out

    def snapshot(self) -> dict:
        day = self.ensure()
        return {
            "date": day_key(),
            "kind": day.get("kind", ""),
            "kind_label": "周末" if day.get("kind") == "weekend" else "工作日",
            "slot": slot_of(),
            "slot_label": SLOT_LABEL.get(slot_of(), ""),
            "events": [
                {
                    "id": e.get("id"),
                    "text": e.get("text"),
                    "kind": e.get("kind"),
                    "effect": e.get("effect", ""),
                    "slot": e.get("slot"),
                    "slot_label": SLOT_LABEL.get(e.get("slot", ""), "全天"),
                    "said": bool(e.get("said")),
                }
                for e in day.get("events") or []
            ],
            "pending": [
                {
                    "id": p.get("id"),
                    "text": p.get("text"),
                    "done": bool(p.get("done")),
                    "carried": bool(p.get("carried")),
                }
                for p in day.get("pending") or []
            ],
            "threads": self.threads_view(),
            "history": self.history(7),
        }
