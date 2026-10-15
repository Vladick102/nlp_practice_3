"""Генератор випадкового старту. Детермінований за seed. python worldgen.py --seed 5"""
import argparse
import json
import random

WEAPONS = ["кинджал", "меч", "лук", "посох"]
GEAR = ["зілля лікування", "мотузка", "факел", "карта", "амулет"]
# локація -> з чим може з'єднатися (беремо першу, яка вже існує)
EXTRAS = {"ринок": ["площа"], "ліс": ["площа", "ринок"],
          "печера": ["підземелля", "ліс"], "міст": ["ліс", "ринок"]}
SAFE_START = ["таверна", "площа", "ринок", "ліс"]
ARTIFACTS = ["втрачений амулет", "старий ключ", "скриню з картою", "книгу заклять"]


def generate_world(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    edges = {("таверна", "площа"), ("площа", "підземелля")}
    nodes = {"таверна", "площа", "підземелля"}
    for loc, anchors in EXTRAS.items():
        if rng.random() < 0.6:
            present = [a for a in anchors if a in nodes]
            if present:
                nodes.add(loc)
                edges.add((rng.choice(present), loc))
    if len(nodes) == 3:  # хоча б одна нова локація
        nodes.add("ринок")
        edges.add(("площа", "ринок"))
    # зайве ребро для петель на мапі
    if len(nodes) > 4 and rng.random() < 0.5:
        a, b = rng.sample(sorted(nodes - {"таверна"}), 2)
        edges.add((a, b))

    graph = {n: [] for n in sorted(nodes)}
    for a, b in edges:
        if b not in graph[a]:
            graph[a].append(b)
        if a not in graph[b]:
            graph[b].append(a)

    start = rng.choice([n for n in SAFE_START if n in nodes])
    targets = [n for n in ("підземелля", "печера") if n in nodes]
    target = rng.choice(targets)
    inventory = [rng.choice(WEAPONS)] + rng.sample(GEAR, rng.randint(1, 2))
    max_hp = 20
    return {
        "seed": seed,
        "quest": f"Знайти {rng.choice(ARTIFACTS)} у локації «{target}»",
        "player": {"hp": rng.randint(8, max_hp), "max_hp": max_hp,
                   "gold": rng.randint(10, 60), "inventory": inventory,
                   "location": start},
        "map": graph,
        "log": [],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    print(json.dumps(generate_world(ap.parse_args().seed), ensure_ascii=False, indent=2))
