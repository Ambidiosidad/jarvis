"""
J.A.R.V.I.S. Memory Service
Persistent SQLite memory: messages, facts, summaries,
emotional state, learned patterns, and visual observations.
"""

import json
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import FastAPI
from pydantic import BaseModel

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


class EmotionalState(BaseModel):
    mood: str
    energy: float
    patience: float
    bond: float
    reason: str


class Observation(BaseModel):
    source: str = "vision"
    summary: str
    labels: list[str] = []
    confidence: float = 0.5


@app.on_event("startup")
async def init_db() -> None:
    async with aiosqlite.connect(str(DB)) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                role TEXT,
                content TEXT,
                topic TEXT,
                importance INT DEFAULT 5,
                session TEXT DEFAULT 'default'
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                summary TEXT,
                topics TEXT,
                session TEXT DEFAULT 'default'
            );

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT UNIQUE,
                source TEXT,
                created REAL
            );

            CREATE TABLE IF NOT EXISTS emotional_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                mood TEXT DEFAULT 'neutral',
                energy REAL DEFAULT 0.5,
                patience REAL DEFAULT 0.8,
                bond REAL DEFAULT 0.1,
                reason TEXT DEFAULT 'initial state'
            );

            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                pattern_type TEXT,
                description TEXT,
                confidence REAL DEFAULT 0.5
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                source TEXT DEFAULT 'vision',
                summary TEXT,
                labels TEXT DEFAULT '[]',
                confidence REAL DEFAULT 0.5
            );
            """
        )

        count_row = await db.execute_fetchall("SELECT COUNT(*) FROM emotional_state")
        if count_row[0][0] == 0:
            await db.execute(
                "INSERT INTO emotional_state (ts,mood,energy,patience,bond,reason) VALUES (?,?,?,?,?,?)",
                (time.time(), "curious", 0.6, 0.8, 0.1, "Jarvis is online"),
            )
            await db.commit()


@app.post("/messages")
async def add_message(msg: Message, session: str = "default") -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO messages (ts,role,content,topic,importance,session) VALUES (?,?,?,?,?,?)",
            (time.time(), msg.role, msg.content, msg.topic, msg.importance, session),
        )
        await db.commit()
    return {"ok": True}


@app.get("/messages/recent")
async def get_recent_messages(limit: int = 10, session: str = "default") -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT role, content FROM messages WHERE session=? ORDER BY ts DESC LIMIT ?",
            (session, limit),
        )
    return {
        "messages": [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    }


@app.post("/facts")
async def add_fact(fact: str, source: str = "conversation") -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        try:
            await db.execute(
                "INSERT INTO facts (fact,source,created) VALUES (?,?,?)",
                (fact, source, time.time()),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            pass
    return {"ok": True}


@app.post("/summaries")
async def add_summary(summary_obj: Summary, session: str = "default") -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO summaries (ts,summary,topics,session) VALUES (?,?,?,?)",
            (
                time.time(),
                summary_obj.summary,
                json.dumps(summary_obj.topics),
                session,
            ),
        )
        await db.commit()
    return {"ok": True}


@app.post("/emotions")
async def update_emotion(state: EmotionalState) -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO emotional_state (ts,mood,energy,patience,bond,reason) VALUES (?,?,?,?,?,?)",
            (
                time.time(),
                state.mood,
                state.energy,
                state.patience,
                state.bond,
                state.reason,
            ),
        )
        await db.commit()
    return {"ok": True}


@app.get("/emotions/current")
async def get_current_emotion() -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        rows = await db.execute_fetchall(
            "SELECT mood, energy, patience, bond, reason FROM emotional_state ORDER BY ts DESC LIMIT 1"
        )

    if rows:
        row = rows[0]
        return {
            "mood": row[0],
            "energy": row[1],
            "patience": row[2],
            "bond": row[3],
            "reason": row[4],
        }

    return {
        "mood": "neutral",
        "energy": 0.5,
        "patience": 0.8,
        "bond": 0.1,
        "reason": "default",
    }


@app.post("/patterns")
async def add_pattern(
    pattern_type: str,
    description: str,
    confidence: float = 0.5,
) -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO learned_patterns (ts,pattern_type,description,confidence) VALUES (?,?,?,?)",
            (time.time(), pattern_type, description, confidence),
        )
        await db.commit()
    return {"ok": True}


@app.post("/observations")
async def add_observation(obs: Observation) -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO observations (ts,source,summary,labels,confidence) VALUES (?,?,?,?,?)",
            (
                time.time(),
                obs.source,
                obs.summary,
                json.dumps(obs.labels),
                obs.confidence,
            ),
        )
        await db.commit()
    return {"ok": True}


@app.get("/observations/recent")
async def get_recent_observations(limit: int = 10) -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        rows = await db.execute_fetchall(
            "SELECT ts, source, summary, labels, confidence FROM observations ORDER BY ts DESC LIMIT ?",
            (limit,),
        )

    observations = []
    for row in rows:
        labels = json.loads(row[3]) if isinstance(row[3], str) else row[3]
        observations.append(
            {
                "ts": row[0],
                "source": row[1],
                "summary": row[2],
                "labels": labels,
                "confidence": row[4],
            }
        )

    return {"observations": observations}


@app.get("/context")
async def get_context(max_summaries: int = 5, max_facts: int = 20) -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        facts = await db.execute_fetchall(
            "SELECT fact FROM facts ORDER BY created DESC LIMIT ?",
            (max_facts,),
        )
        summaries = await db.execute_fetchall(
            "SELECT summary, topics FROM summaries ORDER BY ts DESC LIMIT ?",
            (max_summaries,),
        )
        emotion = await db.execute_fetchall(
            "SELECT mood, energy, patience, bond, reason FROM emotional_state ORDER BY ts DESC LIMIT 1"
        )
        patterns = await db.execute_fetchall(
            "SELECT pattern_type, description FROM learned_patterns ORDER BY ts DESC LIMIT 10"
        )
        observations = await db.execute_fetchall(
            "SELECT source, summary, labels, confidence FROM observations ORDER BY ts DESC LIMIT 5"
        )

    parts: list[str] = []

    if emotion:
        e = emotion[0]
        parts.append("## Current emotional state")
        parts.append(
            f"- Mood: {e[0]} | Energy: {e[1]:.1f}/1.0 | Patience: {e[2]:.1f}/1.0 | Bond: {e[3]:.1f}/1.0"
        )
        parts.append(f"- Reason: {e[4]}")

    if facts:
        parts.append("\n## Known user facts")
        parts.extend(f"- {row[0]}" for row in facts)

    if patterns:
        parts.append("\n## Learned patterns")
        parts.extend(f"- [{row[0]}] {row[1]}" for row in patterns)

    if summaries:
        parts.append("\n## Conversation summaries")
        for row in summaries:
            topics = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            parts.append(f"- [{', '.join(topics)}]: {row[0]}")

    if observations:
        parts.append("\n## Recent visual observations")
        for row in observations:
            labels = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            labels_text = ", ".join(labels) if labels else "none"
            parts.append(
                f"- ({row[0]}, conf {row[3]:.2f}) {row[1]} [labels: {labels_text}]"
            )

    return {
        "context": "\n".join(parts),
        "facts": len(facts),
        "summaries": len(summaries),
        "mood": emotion[0][0] if emotion else "neutral",
        "observations": len(observations),
    }


@app.get("/stats")
async def stats() -> dict:
    async with aiosqlite.connect(str(DB)) as db:
        messages = (await db.execute_fetchall("SELECT COUNT(*) FROM messages"))[0][0]
        summaries = (await db.execute_fetchall("SELECT COUNT(*) FROM summaries"))[0][0]
        facts = (await db.execute_fetchall("SELECT COUNT(*) FROM facts"))[0][0]
        emotions = (await db.execute_fetchall("SELECT COUNT(*) FROM emotional_state"))[0][0]
        patterns = (await db.execute_fetchall("SELECT COUNT(*) FROM learned_patterns"))[0][0]
        observations = (await db.execute_fetchall("SELECT COUNT(*) FROM observations"))[0][0]

    return {
        "messages": messages,
        "summaries": summaries,
        "facts": facts,
        "emotional_updates": emotions,
        "patterns": patterns,
        "observations": observations,
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "jarvis-memory", "version": "2.1"}
