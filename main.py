"""Інтерактивна гра.
  python main.py --random --seed 5        випадковий старт + випадкові події
  python main.py --reset                  фіксований старт з шаблону
  python main.py --reset --no-events      без випадкових подій
  python main.py --mode single            baseline з одним агентом"""
import argparse
import asyncio
import json
import random
import shutil
from pathlib import Path

from agents import play_turn_multi, play_turn_single
from events import EventDirector
from mcp_client import QuestClient, Tracer
from worldgen import generate_world

BASE = Path(__file__).parent


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["multi", "single"], default="multi")
    ap.add_argument("--reset", action="store_true", help="свіжий world.json з шаблону")
    ap.add_argument("--random", action="store_true", help="випадково згенерований старт")
    ap.add_argument("--no-events", action="store_true", help="вимкнути випадкові події")
    ap.add_argument("--seed", type=int, default=None, help="seed для світу, подій і кубика")
    a = ap.parse_args()

    seed = a.seed if a.seed is not None else random.randrange(10_000)
    world = BASE / "world.json"
    if a.random:
        world.write_text(json.dumps(generate_world(seed), ensure_ascii=False, indent=2),
                         encoding="utf-8")
    elif a.reset or not world.exists():
        shutil.copy(BASE / "world.template.json", world)

    w = json.loads(world.read_text(encoding="utf-8"))
    p = w["player"]
    print(f"Режим: {a.mode} | seed={seed} | події: {'ні' if a.no_events else 'так'}")
    print(f"Квест: {w.get('quest')}\nСтарт: {p['location']}, hp {p['hp']}/{p['max_hp']}, "
          f"золото {p['gold']}, інвентар {p['inventory']}")
    print(f"Мапа: {w['map']}")

    director = None if a.no_events else EventDirector(seed)
    turn = play_turn_multi if a.mode == "multi" else play_turn_single
    async with QuestClient(Tracer(run=f"play-{a.mode}"), world, seed) as qc:
        print("\\nПорожній рядок або 'exit' для виходу.".replace("\\n", "\n"))
        while (action := input("\nТи: ").strip()) and action != "exit":
            event = await director.roll(qc) if director else None
            await turn(qc, action, event)


if __name__ == "__main__":
    asyncio.run(main())
