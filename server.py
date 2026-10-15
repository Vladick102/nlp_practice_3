"""MCP-сервер `quest`: 3 інструменти. Єдине місце, де змінюється стан світу.
Увага: stdout зайнятий stdio-транспортом MCP, тому тут жодних print()."""
import json
import os
import random
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE = Path(__file__).parent
WORLD = Path(os.environ.get("QUEST_WORLD", BASE / "world.json"))
TEMPLATE = BASE / "world.template.json"
_seed = os.environ.get("QUEST_SEED")
rng = random.Random(int(_seed)) if _seed else random.Random()

mcp = FastMCP("quest")


def _load() -> dict:
    if not WORLD.exists():
        shutil.copy(TEMPLATE, WORLD)
    return json.loads(WORLD.read_text(encoding="utf-8"))


def _save(w: dict) -> None:
    WORLD.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")


def _err(code: str, message: str, hint: str = "", retryable: bool = True) -> dict:
    return {"error": code, "message": message, "hint": hint, "retryable": retryable}


@mcp.tool()
def get_world_state() -> dict:
    """Повертає поточний стан світу: hp, золото, інвентар, локацію та мапу переходів."""
    w = _load()
    return {"player": w["player"], "map": w["map"], "quest": w.get("quest")}


@mcp.tool()
def roll_dice(sides: int, count: int = 1) -> dict:
    """Кидає `count` кубиків з `sides` гранями (d20 -> sides=20). Повертає rolls і total."""
    if sides < 2 or sides > 100:
        return _err("invalid_input", f"sides={sides} недопустимо.", "Дозволено 2..100")
    if count < 1 or count > 20:
        return _err("invalid_input", f"count={count} недопустимо.", "Дозволено 1..20")
    rolls = [rng.randint(1, sides) for _ in range(count)]
    return {"rolls": rolls, "total": sum(rolls)}


@mcp.tool()
def update_state(kind: str, key: str, delta: int, reason: str) -> dict:
    """ЄДИНИЙ інструмент, що змінює світ.
    kind='hp'       -> key='hp', delta=±N (hp не вище max_hp)
    kind='gold'     -> key='gold', delta=±N (не нижче 0)
    kind='item'     -> key=<назва предмета>, delta=+N додати / -N прибрати
    kind='location' -> key=<назва нової локації>, delta=0 (тільки сусідня локація)
    reason: коротке пояснення, чому змінюємо."""
    w = _load()
    p = w["player"]
    if p["hp"] <= 0:
        return _err("player_dead", "Гравець мертвий, дії заблоковано.", "Почніть нову гру", False)

    if kind == "hp":
        new = min(p["max_hp"], p["hp"] + delta)
        p["hp"] = max(0, new)
        result = {"ok": True, "hp": p["hp"], "dead": p["hp"] == 0}

    elif kind == "gold":
        if p["gold"] + delta < 0:
            return _err("insufficient_gold",
                        f"Золота {p['gold']}, а потрібно {-delta}.",
                        f"Максимум можна витратити {p['gold']}")
        p["gold"] += delta
        result = {"ok": True, "gold": p["gold"]}

    elif kind == "item":
        item = key.strip().lower()
        have = p["inventory"].count(item)
        if delta < 0 and have < -delta:
            return _err("item_not_found", f"В інвентарі немає '{key}' (х{-delta}).",
                        "Є: " + (", ".join(p["inventory"]) or "порожньо"))
        if delta > 0:
            p["inventory"] += [item] * delta
        else:
            for _ in range(-delta):
                p["inventory"].remove(item)
        result = {"ok": True, "inventory": p["inventory"]}

    elif kind == "location":
        options = w["map"].get(p["location"], [])
        if key not in options:
            return _err("invalid_location",
                        f"З '{p['location']}' немає прямого шляху в '{key}'.",
                        "Можна піти в: " + ", ".join(options))
        p["location"] = key
        result = {"ok": True, "location": key}

    else:
        return _err("invalid_input", f"Невідомий kind='{kind}'.", "hp | gold | item | location")

    w["log"].append({"kind": kind, "key": key, "delta": delta, "reason": reason})
    _save(w)
    return result


if __name__ == "__main__":
    mcp.run()  # stdio
