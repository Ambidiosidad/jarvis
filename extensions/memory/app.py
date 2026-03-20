"""
J.A.R.V.I.S. Memory Service — Memoria persistente entre sesiones.
SQLite almacenado en NVMe. 100% offline.
"""
import json, time, aiosqlite
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Jarvis Memory")
DB = Path("/app/data/memory.db")


class Message(BaseModel):
    role: str
    content: str
    topic: Optional[str] = None
    importance: int = 5


class Summary(BaseModel):
    summary: str
    topics: list[str]


@app.on_event("startup")
async def init_db():
    async with aiosqlite.connect(str(DB)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, role TEXT, content TEXT,
                topic TEXT, importance INT DEFAULT 5,
                session TEXT DEFAULT 'default'
            );
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, summary TEXT, topics TEXT,
                session TEXT DEFAULT 'default'
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT UNIQUE, source TEXT, created REAL
            );
        """)


@app.post("/messages")
async def add_message(msg: Message, session: str = "default"):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO messages (ts,role,content,topic,importance,session) VALUES (?,?,?,?,?,?)",
            (time.time(), msg.role, msg.content, msg.topic, msg.importance, session))
        await db.commit()
    return {"ok": True}


@app.post("/summaries")
async def add_summary(s: Summary, session: str = "default"):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO summaries (ts,summary,topics,session) VALUES (?,?,?,?)",
            (time.time(), s.summary, json.dumps(s.topics), session))
        await db.commit()
    return {"ok": True}


@app.post("/facts")
async def add_fact(fact: str, source: str = "conversation"):
    async with aiosqlite.connect(str(DB)) as db:
        try:
            await db.execute("INSERT INTO facts (fact,source,created) VALUES (?,?,?)",
                             (fact, source, time.time()))
            await db.commit()
        except aiosqlite.IntegrityError:
            pass
    return {"ok": True}


@app.get("/context")
async def get_context(max_summaries: int = 5, max_facts: int = 20):
    async with aiosqlite.connect(str(DB)) as db:
        db.row_factory = aiosqlite.Row
        facts = await db.execute_fetchall(
            "SELECT fact FROM facts ORDER BY created DESC LIMIT ?", (max_facts,))
        sums = await db.execute_fetchall(
            "SELECT summary,topics FROM summaries ORDER BY ts DESC LIMIT ?", (max_summaries,))
    parts = []
    if facts:
        parts.append("## Lo que recuerdo de ti:")
        parts.extend(f"- {f[0]}" for f in facts)
    if sums:
        parts.append("\n## Conversaciones anteriores:")
        for s in sums:
            topics = json.loads(s[1]) if isinstance(s[1], str) else s[1]
            parts.append(f"- [{', '.join(topics)}]: {s[0]}")
    return {"context": "\n".join(parts), "facts": len(facts), "summaries": len(sums)}


@app.get("/stats")
async def stats():
    async with aiosqlite.connect(str(DB)) as db:
        m = (await db.execute_fetchall("SELECT COUNT(*) FROM messages"))[0][0]
        s = (await db.execute_fetchall("SELECT COUNT(*) FROM summaries"))[0][0]
        f = (await db.execute_fetchall("SELECT COUNT(*) FROM facts"))[0][0]
    return {"messages": m, "summaries": s, "facts": f}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "jarvis-memory"}
