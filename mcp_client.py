"""MCP-клієнт + трейсер. Агенти ходять до сервера ТІЛЬКИ тут.
Права інструментів примусово перевіряються в коді, а не лише в промпті."""
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE = Path(__file__).parent


class Tracer:
    def __init__(self, run: str = "", path: str = "trace.jsonl", verbose: bool = True):
        self.run, self.path, self.verbose = run, path, verbose
        self.events: list[dict] = []

    def emit(self, ev: dict) -> None:
        ev = {"run": self.run, "t": round(time.time(), 3), **ev}
        self.events.append(ev)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def say(self, agent: str, text: str) -> None:
        if self.verbose:
            print(f"\n[{agent}] {text}")

    @property
    def tool_calls(self) -> list[dict]:
        return [e for e in self.events if e["type"] == "tool"]

    @property
    def llm_calls(self) -> list[dict]:
        return [e for e in self.events if e["type"] == "llm"]

    @property
    def tokens(self) -> int:
        return sum(e.get("total_tokens", 0) for e in self.llm_calls)


class QuestClient:
    def __init__(self, tracer: Tracer, world_path: str, seed: int | None = None):
        self.tracer, self.world_path, self.seed = tracer, world_path, seed
        self._stack = AsyncExitStack()
        self.tools = []

    async def __aenter__(self):
        env = {**os.environ, "QUEST_WORLD": str(self.world_path)}
        if self.seed is not None:
            env["QUEST_SEED"] = str(self.seed)
        params = StdioServerParameters(
            command=sys.executable, args=[str(BASE / "server.py")], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        self.tools = (await self.session.list_tools()).tools
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    def openai_tools(self, allowed: set[str]) -> list[dict]:
        """MCP-схеми -> формат tools для OpenAI-сумісного API (OpenRouter)."""
        return [{"type": "function",
                 "function": {"name": t.name, "description": t.description or "",
                              "parameters": t.inputSchema}}
                for t in self.tools if t.name in allowed]

    async def call(self, agent: str, name: str, args: dict, allowed: set[str]) -> dict:
        t0 = time.time()
        if name not in allowed:
            result = {"error": "forbidden",
                      "message": f"Агент '{agent}' не має права викликати '{name}'.",
                      "hint": "Передайте зміну тому, хто має право писати.",
                      "retryable": False}
        else:
            res = await self.session.call_tool(name, args)
            if res.isError:  # напр. помилка валідації аргументів
                text = res.content[0].text if res.content else "unknown"
                result = {"error": "invalid_input", "message": text,
                          "hint": "Перевірте типи аргументів", "retryable": True}
            elif res.structuredContent:
                result = res.structuredContent
            else:
                result = json.loads(res.content[0].text)
        self.tracer.emit({"type": "tool", "agent": agent, "tool": name, "args": args,
                          "result": result, "ms": int((time.time() - t0) * 1000)})
        if self.tracer.verbose:
            print(f"  [tool:{name}] {agent} {json.dumps(args, ensure_ascii=False)}"
                  f" -> {json.dumps(result, ensure_ascii=False)}")
        return result
