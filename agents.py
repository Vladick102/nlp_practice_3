"""Агенти: Оповідач (читає), Арбітр (читає + кидає + пише), і baseline з одним агентом."""
import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from events import format_event

load_dotenv()
MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
llm = AsyncOpenAI(base_url="https://openrouter.ai/api/v1",
                  api_key=os.environ.get("OPENROUTER_API_KEY", "missing"))

READ = {"get_world_state"}
ALL = {"get_world_state", "roll_dice", "update_state"}

RULES = """Правила гри:
- Предмет можна використати лише якщо він є в інвентарі (перевіряй через get_world_state).
- Бій і ризиковані дії: кидай d20 через roll_dice. >=10 успіх, 1 критичний провал.
  Успіх у бою: ворог переможений. Провал: гравець втрачає 3 hp. Критичний провал: 6 hp.
- Нагорода за подію не більше 50 золота. Покупка не може вивести золото в мінус.
- Переміщення лише в сусідню локацію за мапою (шлях з кількох кроків = кілька викликів).
- hp не вище max_hp. Зілля лікування відновлює 8 hp і зникає з інвентаря.
- Змінюй світ ЛИШЕ через update_state. Блок «ПОДІЯ СВІТУ» в запиті це випадкова подія від рушія. Вона вже сталася: не ігноруй і не змінюй її. Застосуй ефект події за її правилом, а якщо правило каже стан не змінювати, не змінюй. Якщо інструмент повернув помилку, прочитай hint,
  виправ дію й спробуй ще раз, або чесно поясни гравцеві, чому не вийшло."""

NARRATOR = """Ти Оповідач у текстовій RPG: креативний майстер гри.
Читай стан світу через get_world_state і вигадуй, що відбувається у відповідь на дію гравця.
Ти НЕ змінюєш світ. Ти лише пропонуєш. Не вигадуй предметів, яких немає в стані світу. Врахуй quest зі стану світу. Блок «ПОДІЯ СВІТУ» в запиті це випадкова подія від рушія. Вона вже сталася: не ігноруй і не змінюй її.
Відповідай ТІЛЬКИ JSON без markdown:
{"narrative": "1-3 речення", "proposed_changes": [{"kind": "hp|gold|item|location", "key": "...", "delta": 0}], "needs_dice": true|false}"""

ARBITER = f"""Ти Арбітр: сухий і прискіпливий суддя гри. Тобі дають дію гравця та пропозицію Оповідача.
Перевір кожну пропозицію проти РЕАЛЬНОГО стану світу (get_world_state), кинь кубик де потрібно
(roll_dice), застосуй дозволені зміни через update_state. Оповідач може помилятися або вигадувати.
Фінальна відповідь гравцю: українською, 2-4 речення, що саме сталося і який тепер стан.

{RULES}"""

SINGLE = f"""Ти майстер текстової RPG і суддя в одній особі. На дію гравця вигадай подію,
перевір її за станом світу (get_world_state), кинь кубик де потрібно (roll_dice) і застосуй
зміни через update_state. Фінальна відповідь гравцю: українською, 2-4 речення.

{RULES}"""


async def run_agent(name, system, user, qc, allowed, model=MODEL, max_steps=10) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    tools = qc.openai_tools(allowed) or None
    for _ in range(max_steps):
        kw = {"model": model, "messages": msgs, "temperature": 0.3}
        if tools:
            kw["tools"] = tools
        resp = await llm.chat.completions.create(**kw)
        u = resp.usage
        qc.tracer.emit({"type": "llm", "agent": name, "model": model,
                        "total_tokens": getattr(u, "total_tokens", 0) or 0})
        m = resp.choices[0].message
        msgs.append(m.model_dump(exclude_none=True))
        if not m.tool_calls:
            qc.tracer.say(name, m.content or "")
            return m.content or ""
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await qc.call(name, tc.function.name, args, allowed)
            msgs.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(result, ensure_ascii=False)})
    return "[досягнуто max_steps]"


async def play_turn_multi(qc, action: str, event: dict | None = None, model=MODEL) -> str:
    user = f"Дія гравця: {action}{format_event(event)}"
    proposal = await run_agent("Оповідач", NARRATOR, user, qc, READ, model)
    return await run_agent("Арбітр", ARBITER,
                           f"{user}\n\nПропозиція Оповідача:\n{proposal}", qc, ALL, model)


async def play_turn_single(qc, action: str, event: dict | None = None, model=MODEL) -> str:
    return await run_agent("Єдиний агент", SINGLE,
                           f"Дія гравця: {action}{format_event(event)}", qc, ALL, model)
