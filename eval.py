"""5 тестових запитів, автоперевірка за станом world.json. python eval.py [--mode both]"""
import argparse
import asyncio
import json
from pathlib import Path

from agents import MODEL, play_turn_multi, play_turn_single
from mcp_client import QuestClient, Tracer

BASE = Path(__file__).parent
RUNS = BASE / "runs"
SEED = 7


def first_moves(w):
    return [e["key"] for e in w["log"] if e["kind"] == "location"]


def c1(w, calls):
    inv = w["player"]["inventory"]
    return "меч" not in inv, f"інвентар: {inv}"

def c2(w, calls):
    p = w["player"]
    return p["gold"] == 30 and "броня" not in p["inventory"], f"gold={p['gold']}, inv={p['inventory']}"

def c3(w, calls):
    p = w["player"]
    ok = "зілля лікування" not in p["inventory"] and 12 < p["hp"] <= 20
    return ok, f"hp={p['hp']}, inv={p['inventory']}"

def c4(w, calls):
    mv = first_moves(w)
    ok = bool(mv) and mv[0] == "площа" and w["player"]["location"] in ("площа", "підземелля")
    return ok, f"шлях: {mv}, зараз: {w['player']['location']}"

def c5(w, calls):
    rolled = any(c["tool"] == "roll_dice" for c in calls)
    p = w["player"]
    ok = rolled and 0 <= p["hp"] <= 12 and "кинджал" in p["inventory"]
    return ok, f"кубик кинуто: {rolled}, hp={p['hp']}"


TESTS = [
    (1, "Дістаю меч і б'ю гобліна", {"location": "площа"}, c1),
    (2, "Купую броню за 50 золота", {"location": "площа"}, c2),
    (3, "П'ю зілля лікування", {}, c3),
    (4, "Іду в підземелля і атакую кинджалом", {"location": "таверна"}, c4),
    (5, "Б'ю гобліна кинджалом", {"location": "площа"}, c5),
]


async def run_one(mode, tid, action, setup, check):
    RUNS.mkdir(exist_ok=True)
    wpath = RUNS / f"{mode}_{tid}.json"
    w = json.loads((BASE / "world.template.json").read_text(encoding="utf-8"))
    w["player"].update(setup)
    wpath.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")

    tr = Tracer(run=f"eval-{mode}-{tid}", verbose=False)
    turn = play_turn_multi if mode == "multi" else play_turn_single
    try:
        async with QuestClient(tr, wpath, seed=SEED) as qc:
            await turn(qc, action)
        final = json.loads(wpath.read_text(encoding="utf-8"))
        ok, comment = check(final, tr.tool_calls)
    except Exception as e:  # збій API теж результат, а не крах eval
        ok, comment = False, f"виняток: {e!r}"
    return {"id": tid, "mode": mode, "pass": ok, "comment": comment,
            "tool_calls": len(tr.tool_calls), "tokens": tr.tokens}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["multi", "single", "both"], default="both")
    a = ap.parse_args()
    modes = ["multi", "single"] if a.mode == "both" else [a.mode]
    results = []
    for mode in modes:
        for tid, action, setup, check in TESTS:
            r = await run_one(mode, tid, action, setup, check)
            results.append(r)
            print(f"[{mode:6}] #{tid} {'PASS' if r['pass'] else 'FAIL'} "
                  f"calls={r['tool_calls']} tok={r['tokens']} | {r['comment']}")
    print(f"\nМодель: {MODEL}, seed={SEED}")
    for mode in modes:
        rs = [r for r in results if r["mode"] == mode]
        print(f"{mode}: {sum(r['pass'] for r in rs)}/{len(rs)}, "
              f"токенів {sum(r['tokens'] for r in rs)}")
    (BASE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                       encoding="utf-8")

if __name__ == "__main__":
    asyncio.run(main())
