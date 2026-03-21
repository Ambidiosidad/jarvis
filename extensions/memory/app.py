"""
J.A.R.V.I.S. Memory Service v2
================================
Memoria persistente + estado emocional + auto-resumen.
SQLite almacenado en NVMe. 100% offline.
"""
import json, time, aiosqlite
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Jarvis Memory v2")
DB = Path("/app/data/memory.db")


# ─── Modelos ───

class Message(BaseModel):
    role: str
    content: str
    topic: Optional[str] = None
    importance: int = 5


class Summary(BaseModel):
    summary: str
    topics: list[str]


class EmotionalState(BaseModel):
    mood: str          # curious, happy, cautious, empathetic, neutral, excited
    energy: float      # 0.0 (calm) to 1.0 (very active)
    patience: float    # 0.0 (frustrated) to 1.0 (very patient)
    bond: float        # 0.0 (stranger) to 1.0 (close friend)
    reason: str        # why the state changed


# ─── Startup ───

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
        """)
        # Ensure there's at least one emotional state
        count = await db.execute_fetchall(
            "SELECT COUNT(*) FROM emotional_state"
        )
        if count[0][0] == 0:
            await db.execute(
                "INSERT INTO emotional_state (ts,mood,energy,patience,bond,reason) "
                "VALUES (?,?,?,?,?,?)",
                (time.time(), "curious", 0.6, 0.8, 0.1, "Jarvis acaba de despertar")
            )
            await db.commit()


# ─── Messages ───

@app.post("/messages")
async def add_message(msg: Message, session: str = "default"):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO messages (ts,role,content,topic,importance,session) "
            "VALUES (?,?,?,?,?,?)",
            (time.time(), msg.role, msg.content, msg.topic,
             msg.importance, session))
        await db.commit()
    return {"ok": True}


@app.get("/messages/recent")
async def get_recent_messages(limit: int = 10, session: str = "default"):
    async with aiosqlite.connect(str(DB)) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT role, content FROM messages "
            "WHERE session=? ORDER BY ts DESC LIMIT ?",
            (session, limit))
    return {"messages": [{"role": r[0], "content": r[1]} for r in reversed(rows)]}


# ─── Facts ───

@app.post("/facts")
async def add_fact(fact: str, source: str = "conversation"):
    async with aiosqlite.connect(str(DB)) as db:
        try:
            await db.execute(
                "INSERT INTO facts (fact,source,created) VALUES (?,?,?)",
                (fact, source, time.time()))
            await db.commit()
        except aiosqlite.IntegrityError:
            pass
    return {"ok": True}


# ─── Summaries ───

@app.post("/summaries")
async def add_summary(s: Summary, session: str = "default"):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO summaries (ts,summary,topics,session) VALUES (?,?,?,?)",
            (time.time(), s.summary, json.dumps(s.topics), session))
        await db.commit()
    return {"ok": True}


# ─── Emotional State ───

@app.post("/emotions")
async def update_emotion(state: EmotionalState):
    """Update Jarvis's current emotional state."""
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO emotional_state (ts,mood,energy,patience,bond,reason) "
            "VALUES (?,?,?,?,?,?)",
            (time.time(), state.mood, state.energy, state.patience,
             state.bond, state.reason))
        await db.commit()
    return {"ok": True}


@app.get("/emotions/current")
async def get_current_emotion():
    """Get Jarvis's current emotional state."""
    async with aiosqlite.connect(str(DB)) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchall(
            "SELECT mood, energy, patience, bond, reason "
            "FROM emotional_state ORDER BY ts DESC LIMIT 1")
    if row:
        return {
            "mood": row[0][0], "energy": row[0][1],
            "patience": row[0][2], "bond": row[0][3],
            "reason": row[0][4]
        }
    return {"mood": "neutral", "energy": 0.5, "patience": 0.8,
            "bond": 0.1, "reason": "default"}


# ─── Learned Patterns ───

@app.post("/patterns")
async def add_pattern(pattern_type: str, description: str,
                      confidence: float = 0.5):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO learned_patterns (ts,pattern_type,description,confidence) "
            "VALUES (?,?,?,?)",
            (time.time(), pattern_type, description, confidence))
        await db.commit()
    return {"ok": True}


# ─── Context (injected into system prompt) ───

@app.get("/context")
async def get_context(max_summaries: int = 5, max_facts: int = 20):
    """Generate full context block for system prompt injection."""
    async with aiosqlite.connect(str(DB)) as db:
        db.row_factory = aiosqlite.Row
        facts = await db.execute_fetchall(
            "SELECT fact FROM facts ORDER BY created DESC LIMIT ?",
            (max_facts,))
        sums = await db.execute_fetchall(
            "SELECT summary, topics FROM summaries ORDER BY ts DESC LIMIT ?",
            (max_summaries,))
        emotion = await db.execute_fetchall(
            "SELECT mood, energy, patience, bond, reason "
            "FROM emotional_state ORDER BY ts DESC LIMIT 1")
        patterns = await db.execute_fetchall(
            "SELECT pattern_type, description FROM learned_patterns "
            "ORDER BY ts DESC LIMIT 10")

    parts = []

    # Emotional state
    if emotion:
        e = emotion[0]
        parts.append("## Tu estado emocional actual:")
        parts.append(
            f"- Humor: {e[0]} | Energía: {e[1]:.1f}/1.0 | "
            f"Paciencia: {e[2]:.1f}/1.0 | Vínculo con usuario: {e[3]:.1f}/1.0"
        )
        parts.append(f"- Razón: {e[4]}")
        parts.append(
            "- Adapta tu tono según tu estado: si estás 'curious', "
            "haz preguntas; si 'empathetic', sé más cálido; "
            "si 'excited', muestra entusiasmo."
        )

    # Facts
    if facts:
        parts.append("\n## Lo que recuerdo del usuario:")
        parts.extend(f"- {f[0]}" for f in facts)

    # Learned patterns
    if patterns:
        parts.append("\n## Patrones que he aprendido:")
        parts.extend(
            f"- [{p[0]}] {p[1]}" for p in patterns)

    # Summaries
    if sums:
        parts.append("\n## Conversaciones anteriores:")
        for s in sums:
            topics = json.loads(s[1]) if isinstance(s[1], str) else s[1]
            parts.append(f"- [{', '.join(topics)}]: {s[0]}")

    return {
        "context": "\n".join(parts),
        "facts": len(facts),
        "summaries": len(sums),
        "mood": emotion[0][0] if emotion else "neutral"
    }


# ─── Stats ───

@app.get("/stats")
async def stats():
    async with aiosqlite.connect(str(DB)) as db:
        m = (await db.execute_fetchall("SELECT COUNT(*) FROM messages"))[0][0]
        s = (await db.execute_fetchall("SELECT COUNT(*) FROM summaries"))[0][0]
        f = (await db.execute_fetchall("SELECT COUNT(*) FROM facts"))[0][0]
        e = (await db.execute_fetchall("SELECT COUNT(*) FROM emotional_state"))[0][0]
        p = (await db.execute_fetchall("SELECT COUNT(*) FROM learned_patterns"))[0][0]
    return {"messages": m, "summaries": s, "facts": f,
            "emotional_updates": e, "patterns": p}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "jarvis-memory", "version": "2.0"}
