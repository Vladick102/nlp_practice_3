"""Директор подій: випадкові події у випадкові моменти.
Кидає рушій (seeded rng), а не LLM, тому події відтворювані й тестуються без моделі.
Директор лише ЧИТАЄ стан. Ефекти події застосовує Арбітр через update_state."""
import random

# id, вага, де можлива (None = будь-де), roll(rng)->параметри, text, rule
EVENTS = [
    dict(id="ambush", w=3, where=["площа", "ліс", "міст", "підземелля", "печера"],
         text="З тіні вистрибує гоблін-розбійник і нападає!",
         rule="Арбітр: кинь d20 за гравця. >=10: напад відбито, змін немає. "
              "<10: -3 hp. Критичний провал (1): -6 hp."),
    dict(id="lucky_find", w=2, where=None,
         roll=lambda r: {"gold": 5 * r.randint(1, 6)},
         text="Під ногами лежить загублений гаманець.",
         rule="Арбітр: додай рівно {gold} золота (update_state, kind=gold)."),
    dict(id="trap", w=2, where=["підземелля", "печера", "ліс", "міст"],
         text="Ви наступаєте на прихований механізм!",
         rule="Арбітр: кинь d20. >=12: гравець ухилився, змін немає. <12: -4 hp."),
    dict(id="healer", w=2, where=["таверна", "площа", "ринок"],
         text="Повз іде мандрівний цілитель і пригощає вас відваром.",
         rule="Арбітр: відновити 4 hp (не вище max_hp)."),
    dict(id="find_item", w=2, where=None,
         roll=lambda r: {"item": r.choice(["факел", "мотузка", "карта", "амулет"])},
         text="У кишені мертвого щура ви знаходите щось корисне.",
         rule="Арбітр: додай предмет '{item}' в інвентар (update_state, kind=item, delta=+1)."),
    dict(id="storm", w=2, where=["ліс", "міст", "площа"],
         text="Починається злива, дорога стає слизькою.",
         rule="Без механічних наслідків: лише опис. Стан світу НЕ змінювати."),
    dict(id="thief", w=2, where=["ринок", "площа", "таверна"],
         roll=lambda r: {"loss": r.randint(3, 10)},
         text="Кишеньковий злодій тягнеться до вашого гаманця.",
         rule="Арбітр: кинь d20. >=10: злодія спіймано, без втрат. "
              "<10: втрата {loss} золота (але не більше, ніж є у гравця)."),
]


def format_event(ev: dict | None) -> str:
    if not ev:
        return ""
    return (f"\n\nПОДІЯ СВІТУ (випадкова, ВЖЕ сталася, ігнорувати не можна): {ev['text']}"
            f"\nПравило ефекту: {ev['rule']}")


class EventDirector:
    """Шанс події росте з кожним «тихим» ходом (pity timer), після події скидається.
    Тому моменти випадкові, але довгих пауз і спаму подіями немає."""

    def __init__(self, seed: int | None = None, base_p: float = 0.15,
                 step: float = 0.15, verbose: bool = True):
        self.rng = random.Random(seed)
        self.base_p, self.step, self.p = base_p, step, base_p
        self.verbose, self.turn = verbose, 0

    async def roll(self, qc) -> dict | None:
        self.turn += 1
        state = await qc.call("Директор", "get_world_state", {}, {"get_world_state"})
        if "player" not in state or state["player"]["hp"] <= 0:
            return None
        if self.rng.random() >= self.p:
            self.p = min(0.9, self.p + self.step)
            return None
        loc = state["player"]["location"]
        pool = [e for e in EVENTS if e["where"] is None or loc in e["where"]]
        ev = self.rng.choices(pool, weights=[e["w"] for e in pool])[0]
        params = ev["roll"](self.rng) if "roll" in ev else {}
        self.p = self.base_p
        event = {"id": ev["id"], "turn": self.turn, "location": loc,
                 "text": ev["text"].format(**params), "rule": ev["rule"].format(**params)}
        qc.tracer.emit({"type": "event", **event})
        if self.verbose:
            print(f"\n[Директор] ⚡ подія '{event['id']}' (хід {self.turn}, {loc}): {event['text']}")
        return event
