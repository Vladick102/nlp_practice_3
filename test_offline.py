"""Перевірки без LLM: python test_offline.py"""
import asyncio
from collections import Counter

from events import EVENTS, EventDirector, format_event
from worldgen import generate_world


def reachable(g, start):
    seen, stack = {start}, [start]
    while stack:
        for n in g[stack.pop()]:
            if n not in seen:
                seen.add(n); stack.append(n)
    return seen


def test_worldgen():
    assert generate_world(5) == generate_world(5), "детермінізм"
    starts, invs = Counter(), set()
    for s in range(300):
        w = generate_world(s); p = w["player"]
        assert set(w["map"]) == reachable(w["map"], p["location"]), f"seed {s}: мапа не зв'язна"
        assert all(a in w["map"][b] for a in w["map"] for b in w["map"][a]), "ребра двосторонні"
        assert 8 <= p["hp"] <= p["max_hp"] and p["gold"] >= 10 and p["inventory"]
        assert p["location"] not in ("підземелля", "печера")
        starts[p["location"]] += 1; invs.add(tuple(p["inventory"]))
    print("світи ок; старти:", dict(starts), "| унікальних інвентарів:", len(invs))


class FakeTracer:
    def __init__(self): self.events = []
    def emit(self, e): self.events.append(e)

class FakeQC:
    def __init__(self, loc): self.loc, self.tracer = loc, FakeTracer()
    async def call(self, agent, name, args, allowed):
        assert agent == "Директор" and allowed == {"get_world_state"}  # тільки читає
        return {"player": {"location": self.loc, "hp": 10}, "map": {}}


async def test_director():
    async def sim(seed, loc, n=2000):
        d, qc, evs = EventDirector(seed, verbose=False), FakeQC(loc), []
        for _ in range(n):
            e = await d.roll(qc)
            evs.append(e)
        return evs
    a, b = await sim(1, "площа"), await sim(1, "площа")
    assert a == b, "ті самі seed -> ті самі події"
    assert a != await sim(2, "площа")
    fired = [i for i, e in enumerate(a) if e]
    gaps = [j - i for i, j in zip(fired, fired[1:])]
    print(f"подій {len(fired)}/2000 ({len(fired)/20:.0f}%), найдовша пауза {max(gaps)} ходів, "
          f"розподіл: {dict(Counter(e['id'] for e in a if e))}")
    assert max(gaps) <= 8, "pity timer має обмежувати паузи"
    for loc in ("таверна", "підземелля", "ринок"):
        ids = {e["id"] for e in await sim(3, loc) if e}
        for ev in EVENTS:
            if ev["where"] is not None and loc not in ev["where"]:
                assert ev["id"] not in ids, f"{ev['id']} не може бути в {loc}"
    for e in a:
        if e: assert "{" not in e["text"] + e["rule"], "неформатований плейсхолдер"
    print(format_event(next(e for e in a if e and e["id"] == "lucky_find")).strip())


if __name__ == "__main__":
    test_worldgen()
    asyncio.run(test_director())
    print("OK")
