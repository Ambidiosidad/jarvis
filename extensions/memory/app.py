"""
J.A.R.V.I.S. Memory Service v3
==================================
Arquitectura inspirada en Supermemory, 100% offline.

Conceptos clave:
- DOCUMENTS: input raw (mensajes, textos)
- MEMORIES: hechos extraídos con relaciones entre sí
- PROFILE: estático (hechos permanentes) + dinámico (contexto reciente)
- RELATIONSHIPS: updates (reemplaza), extends (enriquece), derives (infiere)
- CONTRADICTION RESOLUTION: "vivo en Madrid" reemplaza "vivo en Barcelona"
- TEMPORAL DECAY: el contexto dinámico caduca, los hechos estáticos no
- SEMANTIC SEARCH: búsqueda por significado vía embeddings locales
"""
import json, time, re, hashlib, aiosqlite
from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import semantic_search

app = FastAPI(title="Jarvis Memory v3 — Supermemory Offline")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
DB = Path("/app/data/memory.db")


# ═══════════════════════════════════════
#  Modelos
# ═══════════════════════════════════════

class Message(BaseModel):
    role: str
    content: str
    topic: Optional[str] = None
    importance: int = 5


class MemoryInput(BaseModel):
    content: str
    memory_type: str = "fact"  # fact, preference, context, project, relationship
    category: str = "general"  # identity, location, work, interests, etc.
    source: str = "conversation"
    ttl_hours: Optional[float] = None  # None = permanent, number = expires


class Summary(BaseModel):
    summary: str
    topics: list[str]


class EmotionalState(BaseModel):
    mood: str
    energy: float
    patience: float
    bond: float
    reason: str


class ProfileResponse(BaseModel):
    static: list[str]   # Permanent facts
    dynamic: list[str]  # Recent context (decays)
    mood: str
    bond: float


# ═══════════════════════════════════════
#  Database Init
# ═══════════════════════════════════════

@app.on_event("startup")
async def init_db():
    async with aiosqlite.connect(str(DB)) as db:
        await db.executescript("""
            -- Raw conversation messages
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, role TEXT, content TEXT,
                topic TEXT, importance INT DEFAULT 5,
                session TEXT DEFAULT 'default'
            );

            -- Intelligent memory units (like Supermemory memories)
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                content TEXT NOT NULL,
                memory_type TEXT DEFAULT 'fact',
                category TEXT DEFAULT 'general',
                source TEXT DEFAULT 'conversation',
                is_latest INTEGER DEFAULT 1,
                confidence REAL DEFAULT 0.8,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL,
                expires_at REAL,
                content_hash TEXT,
                UNIQUE(content_hash)
            );

            -- Relationships between memories (graph edges)
            CREATE TABLE IF NOT EXISTS memory_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                source_id INTEGER,
                target_id INTEGER,
                relation_type TEXT,
                reason TEXT,
                FOREIGN KEY (source_id) REFERENCES memories(id),
                FOREIGN KEY (target_id) REFERENCES memories(id)
            );

            -- User profile (static + dynamic, auto-maintained)
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                fact TEXT NOT NULL,
                profile_type TEXT DEFAULT 'static',
                category TEXT DEFAULT 'general',
                is_active INTEGER DEFAULT 1,
                superseded_by INTEGER,
                UNIQUE(fact)
            );

            -- Conversation summaries
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, summary TEXT, topics TEXT,
                session TEXT DEFAULT 'default'
            );

            -- Emotional state history
            CREATE TABLE IF NOT EXISTS emotional_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                mood TEXT DEFAULT 'neutral',
                energy REAL DEFAULT 0.5,
                patience REAL DEFAULT 0.8,
                bond REAL DEFAULT 0.1,
                reason TEXT DEFAULT 'initial state'
            );

            -- Learned behavior patterns
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                pattern_type TEXT,
                description TEXT,
                confidence REAL DEFAULT 0.5
            );
        """)

        # Ensure initial emotional state
        count = await db.execute_fetchall(
            "SELECT COUNT(*) FROM emotional_state")
        if count[0][0] == 0:
            await db.execute(
                "INSERT INTO emotional_state "
                "(ts,mood,energy,patience,bond,reason) VALUES (?,?,?,?,?,?)",
                (time.time(), "curious", 0.6, 0.8, 0.1,
                 "Jarvis acaba de despertar"))
            await db.commit()

    # Initialize Qdrant collection for semantic search
    await semantic_search.init_collection()


# ═══════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════

def _hash(text: str) -> str:
    """Generate content hash for deduplication."""
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()


# Categories for contradiction detection
_CATEGORY_PATTERNS = {
    "identity": [
        r"(?:se llama|nombre es|name is)\s+",
        r"(?:tiene)\s+\d+\s+años",
        r"(?:is|tiene)\s+\d+\s+(?:years|años)",
    ],
    "location": [
        r"(?:vive en|soy de|live[s]? in|from)\s+",
        r"(?:ciudad|city|país|country)\s+",
    ],
    "work": [
        r"(?:trabaja en|trabaja como|works? (?:at|as|for))\s+",
        r"(?:profesión|job|puesto|role)\s+",
    ],
    "relationship": [
        r"(?:pareja|partner|novia|novio|esposa|esposo|wife|husband)\s+",
    ],
    "project": [
        r"(?:proyecto|project|construyendo|building|working on)\s+",
    ],
}


def _detect_category(text: str) -> str:
    """Detect the category of a memory for contradiction resolution."""
    lower = text.lower()
    for category, patterns in _CATEGORY_PATTERNS.items():
        for p in patterns:
            if re.search(p, lower):
                return category
    return "general"


def _is_similar_topic(fact_a: str, fact_b: str, category: str) -> bool:
    """Check if two facts are about the same topic (potential contradiction)."""
    if category == "general":
        return False

    a_lower = fact_a.lower()
    b_lower = fact_b.lower()

    # Same category keywords present in both
    if category == "identity":
        return (("llama" in a_lower or "nombre" in a_lower or "name" in a_lower)
                and ("llama" in b_lower or "nombre" in b_lower or "name" in b_lower)) or \
               (("años" in a_lower or "years" in a_lower)
                and ("años" in b_lower or "years" in b_lower))
    elif category == "location":
        return ("vive" in a_lower or "live" in a_lower or "soy de" in a_lower) and \
               ("vive" in b_lower or "live" in b_lower or "soy de" in b_lower)
    elif category == "work":
        return ("trabaja" in a_lower or "work" in a_lower) and \
               ("trabaja" in b_lower or "work" in b_lower)
    elif category == "relationship":
        return ("pareja" in a_lower or "partner" in a_lower) and \
               ("pareja" in b_lower or "partner" in b_lower)
    elif category == "project":
        # Projects can coexist, only replace if same project name
        return a_lower[:30] == b_lower[:30]

    return False


# ═══════════════════════════════════════
#  Messages (raw conversation)
# ═══════════════════════════════════════

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
        rows = await db.execute_fetchall(
            "SELECT role, content FROM messages "
            "WHERE session=? ORDER BY ts DESC LIMIT ?",
            (session, limit))
    return {"messages": [{"role": r[0], "content": r[1]}
                         for r in reversed(rows)]}


# ═══════════════════════════════════════
#  Memories (intelligent knowledge units)
# ═══════════════════════════════════════

@app.post("/memories")
async def add_memory(mem: MemoryInput):
    """
    Add a memory with automatic contradiction resolution.
    If a conflicting memory exists in the same category,
    the old one is marked as superseded (is_latest=0)
    and a 'updates' relationship is created.
    """
    content_hash = _hash(mem.content)
    category = _detect_category(mem.content) or mem.category
    now = time.time()
    expires_at = (now + mem.ttl_hours * 3600) if mem.ttl_hours else None

    async with aiosqlite.connect(str(DB)) as db:
        # Check for exact duplicate
        existing = await db.execute_fetchall(
            "SELECT id FROM memories WHERE content_hash=?",
            (content_hash,))
        if existing:
            # Update access count
            await db.execute(
                "UPDATE memories SET access_count=access_count+1, "
                "last_accessed=? WHERE content_hash=?",
                (now, content_hash))
            await db.commit()
            return {"ok": True, "action": "deduplicated",
                    "id": existing[0][0]}

        # Check for contradictions in same category
        superseded_id = None
        if category != "general":
            candidates = await db.execute_fetchall(
                "SELECT id, content FROM memories "
                "WHERE category=? AND is_latest=1",
                (category,))
            for cand_id, cand_content in candidates:
                if _is_similar_topic(mem.content, cand_content, category):
                    # Mark old memory as superseded
                    await db.execute(
                        "UPDATE memories SET is_latest=0 WHERE id=?",
                        (cand_id,))
                    superseded_id = cand_id
                    break

        # Insert new memory
        cursor = await db.execute(
            "INSERT INTO memories "
            "(ts,content,memory_type,category,source,is_latest,"
            "confidence,last_accessed,expires_at,content_hash) "
            "VALUES (?,?,?,?,?,1,?,?,?,?)",
            (now, mem.content, mem.memory_type, category, mem.source,
             0.8, now, expires_at, content_hash))
        new_id = cursor.lastrowid

        # Create 'updates' relationship if superseded
        if superseded_id:
            await db.execute(
                "INSERT INTO memory_relations "
                "(ts,source_id,target_id,relation_type,reason) "
                "VALUES (?,?,?,?,?)",
                (now, new_id, superseded_id, "updates",
                 f"New info supersedes memory #{superseded_id}"))

        await db.commit()

    # Index in Qdrant for semantic search
    await semantic_search.index_memory(new_id, mem.content, {
        "category": category,
        "memory_type": mem.memory_type,
        "source": mem.source,
    })

    action = "updated" if superseded_id else "created"
    return {"ok": True, "action": action, "id": new_id,
            "superseded": superseded_id, "category": category}


@app.get("/memories/search")
async def search_memories(q: str, limit: int = 10):
    """
    Search memories by semantic similarity (Qdrant) with SQLite fallback.
    Like Supermemory's hybrid search.
    """
    # Try semantic search first
    if semantic_search.is_ready():
        results = await semantic_search.search_similar(q, limit)
        if results:
            return {"results": results, "search_type": "semantic"}

    # Fallback to SQLite text search
    now = time.time()
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL "
            "AND expires_at < ?", (now,))
        words = q.lower().split()
        if not words:
            return {"results": [], "search_type": "none"}
        conditions = " AND ".join(
            [f"LOWER(content) LIKE '%' || ? || '%'" for _ in words])
        query = (
            f"SELECT id, content, memory_type, category, confidence, ts "
            f"FROM memories WHERE is_latest=1 AND {conditions} "
            f"ORDER BY confidence DESC, ts DESC LIMIT ?"
        )
        rows = await db.execute_fetchall(query, (*words, limit))
        await db.commit()

    return {"results": [
        {"memory_id": r[0], "content": r[1], "memory_type": r[2],
         "category": r[3], "confidence": r[4], "score": r[4]}
        for r in rows
    ], "search_type": "text"}


@app.get("/memories/all")
async def get_all_memories(include_superseded: bool = False):
    """Get all active memories."""
    now = time.time()
    async with aiosqlite.connect(str(DB)) as db:
        # Clean expired
        await db.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL "
            "AND expires_at < ?", (now,))

        if include_superseded:
            rows = await db.execute_fetchall(
                "SELECT id, content, memory_type, category, "
                "is_latest, confidence, ts FROM memories ORDER BY ts DESC")
        else:
            rows = await db.execute_fetchall(
                "SELECT id, content, memory_type, category, "
                "is_latest, confidence, ts FROM memories "
                "WHERE is_latest=1 ORDER BY ts DESC")
        await db.commit()

    return {"memories": [
        {"id": r[0], "content": r[1], "type": r[2],
         "category": r[3], "is_latest": bool(r[4]),
         "confidence": r[5]}
        for r in rows
    ]}


# ═══════════════════════════════════════
#  Profile (static + dynamic)
# ═══════════════════════════════════════

@app.post("/profile")
async def add_profile_fact(fact: str, profile_type: str = "static",
                           category: str = "general"):
    """
    Add a fact to user profile with contradiction resolution.
    Static facts persist forever. Dynamic facts are recent context.
    If a contradicting fact exists in same category, it's superseded.
    """
    now = time.time()
    category = _detect_category(fact) or category

    async with aiosqlite.connect(str(DB)) as db:
        # Check for contradiction in same category
        if category != "general":
            existing = await db.execute_fetchall(
                "SELECT id, fact FROM profile "
                "WHERE category=? AND is_active=1 AND profile_type=?",
                (category, profile_type))
            for eid, efact in existing:
                if _is_similar_topic(fact, efact, category):
                    # Supersede old fact
                    await db.execute(
                        "UPDATE profile SET is_active=0, superseded_by=NULL "
                        "WHERE id=?", (eid,))

        # Insert new fact
        try:
            cursor = await db.execute(
                "INSERT INTO profile (ts,fact,profile_type,category,is_active) "
                "VALUES (?,?,?,?,1)",
                (now, fact, profile_type, category))
            new_id = cursor.lastrowid

            # Update superseded_by reference
            if category != "general":
                await db.execute(
                    "UPDATE profile SET superseded_by=? "
                    "WHERE category=? AND is_active=0 AND superseded_by IS NULL "
                    "AND id!=?",
                    (new_id, category, new_id))

            await db.commit()
            return {"ok": True, "id": new_id, "category": category}
        except aiosqlite.IntegrityError:
            return {"ok": True, "action": "duplicate"}


@app.get("/profile")
async def get_profile() -> dict:
    """
    Get complete user profile: static facts + dynamic context.
    Like Supermemory's profile endpoint.
    """
    now = time.time()
    # Dynamic facts older than 72 hours decay
    dynamic_cutoff = now - (72 * 3600)

    async with aiosqlite.connect(str(DB)) as db:
        static = await db.execute_fetchall(
            "SELECT fact FROM profile "
            "WHERE profile_type='static' AND is_active=1 "
            "ORDER BY ts DESC")

        dynamic = await db.execute_fetchall(
            "SELECT fact FROM profile "
            "WHERE profile_type='dynamic' AND is_active=1 "
            "AND ts > ? ORDER BY ts DESC",
            (dynamic_cutoff,))

        # Get current emotion
        emotion = await db.execute_fetchall(
            "SELECT mood, bond FROM emotional_state "
            "ORDER BY ts DESC LIMIT 1")

    mood = emotion[0][0] if emotion else "neutral"
    bond = emotion[0][1] if emotion else 0.1

    return {
        "static": [r[0] for r in static],
        "dynamic": [r[0] for r in dynamic],
        "mood": mood,
        "bond": bond,
    }


# ═══════════════════════════════════════
#  Legacy Facts endpoint (backward compat)
# ═══════════════════════════════════════

@app.post("/facts")
async def add_fact(fact: str, source: str = "conversation"):
    """Backward compatible — routes to memories + profile."""
    category = _detect_category(fact)
    mem = MemoryInput(
        content=fact, memory_type="fact",
        category=category, source=source)
    mem_result = await add_memory(mem)

    # Also add to profile as static fact
    await add_profile_fact(fact, "static", category)

    return {"ok": True, "memory": mem_result}


# ═══════════════════════════════════════
#  Memory Relations
# ═══════════════════════════════════════

@app.post("/memories/{memory_id}/relate")
async def add_relation(memory_id: int, target_id: int,
                       relation_type: str = "extends",
                       reason: str = ""):
    """
    Create a relationship between two memories.
    Types: updates, extends, derives
    """
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO memory_relations "
            "(ts,source_id,target_id,relation_type,reason) "
            "VALUES (?,?,?,?,?)",
            (time.time(), memory_id, target_id, relation_type, reason))
        await db.commit()
    return {"ok": True}


@app.get("/memories/{memory_id}/relations")
async def get_relations(memory_id: int):
    """Get all relationships for a memory."""
    async with aiosqlite.connect(str(DB)) as db:
        outgoing = await db.execute_fetchall(
            "SELECT r.relation_type, r.reason, m.content "
            "FROM memory_relations r JOIN memories m ON r.target_id=m.id "
            "WHERE r.source_id=?", (memory_id,))
        incoming = await db.execute_fetchall(
            "SELECT r.relation_type, r.reason, m.content "
            "FROM memory_relations r JOIN memories m ON r.source_id=m.id "
            "WHERE r.target_id=?", (memory_id,))

    return {
        "outgoing": [{"type": r[0], "reason": r[1], "content": r[2]}
                     for r in outgoing],
        "incoming": [{"type": r[0], "reason": r[1], "content": r[2]}
                     for r in incoming],
    }


# ═══════════════════════════════════════
#  Summaries
# ═══════════════════════════════════════

@app.post("/summaries")
async def add_summary(s: Summary, session: str = "default"):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO summaries (ts,summary,topics,session) "
            "VALUES (?,?,?,?)",
            (time.time(), s.summary, json.dumps(s.topics), session))
        await db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
#  Emotional State
# ═══════════════════════════════════════

@app.post("/emotions")
async def update_emotion(state: EmotionalState):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO emotional_state "
            "(ts,mood,energy,patience,bond,reason) VALUES (?,?,?,?,?,?)",
            (time.time(), state.mood, state.energy, state.patience,
             state.bond, state.reason))
        await db.commit()
    return {"ok": True}


@app.get("/emotions/current")
async def get_current_emotion():
    async with aiosqlite.connect(str(DB)) as db:
        row = await db.execute_fetchall(
            "SELECT mood, energy, patience, bond, reason "
            "FROM emotional_state ORDER BY ts DESC LIMIT 1")
    if row:
        return {"mood": row[0][0], "energy": row[0][1],
                "patience": row[0][2], "bond": row[0][3],
                "reason": row[0][4]}
    return {"mood": "neutral", "energy": 0.5, "patience": 0.8,
            "bond": 0.1, "reason": "default"}


# ═══════════════════════════════════════
#  Learned Patterns
# ═══════════════════════════════════════

@app.post("/patterns")
async def add_pattern(pattern_type: str, description: str,
                      confidence: float = 0.5):
    async with aiosqlite.connect(str(DB)) as db:
        await db.execute(
            "INSERT INTO learned_patterns "
            "(ts,pattern_type,description,confidence) VALUES (?,?,?,?)",
            (time.time(), pattern_type, description, confidence))
        await db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
#  Context (injected into system prompt)
# ═══════════════════════════════════════

@app.get("/context")
async def get_context():
    """
    Generate full context block for system prompt injection.
    Uses the Supermemory profile model: static + dynamic.
    """
    now = time.time()
    dynamic_cutoff = now - (72 * 3600)

    async with aiosqlite.connect(str(DB)) as db:
        # Profile: static facts
        static_facts = await db.execute_fetchall(
            "SELECT fact FROM profile "
            "WHERE profile_type='static' AND is_active=1 "
            "ORDER BY ts DESC LIMIT 20")

        # Profile: dynamic context (last 72h)
        dynamic_facts = await db.execute_fetchall(
            "SELECT fact FROM profile "
            "WHERE profile_type='dynamic' AND is_active=1 "
            "AND ts > ? ORDER BY ts DESC LIMIT 10",
            (dynamic_cutoff,))

        # Recent summaries
        sums = await db.execute_fetchall(
            "SELECT summary, topics FROM summaries "
            "ORDER BY ts DESC LIMIT 5")

        # Learned patterns
        patterns = await db.execute_fetchall(
            "SELECT pattern_type, description FROM learned_patterns "
            "ORDER BY ts DESC LIMIT 10")

        # Current emotion
        emotion = await db.execute_fetchall(
            "SELECT mood, energy, patience, bond, reason "
            "FROM emotional_state ORDER BY ts DESC LIMIT 1")

    parts = []

    # Profile section
    if static_facts:
        parts.append("## Lo que sé del usuario:")
        parts.extend(f"- {f[0]}" for f in static_facts)

    if dynamic_facts:
        parts.append("\n## Contexto reciente:")
        parts.extend(f"- {f[0]}" for f in dynamic_facts)

    # Patterns
    if patterns:
        parts.append("\n## Patrones observados:")
        parts.extend(f"- [{p[0]}] {p[1]}" for p in patterns)

    # Summaries
    if sums:
        parts.append("\n## Conversaciones anteriores:")
        for s in sums:
            topics = json.loads(s[1]) if isinstance(s[1], str) else s[1]
            parts.append(f"- [{', '.join(topics)}]: {s[0]}")

    mood = emotion[0][0] if emotion else "neutral"
    total_facts = len(static_facts) + len(dynamic_facts)

    return {
        "context": "\n".join(parts),
        "static_facts": len(static_facts),
        "dynamic_facts": len(dynamic_facts),
        "summaries": len(sums),
        "mood": mood,
    }


# ═══════════════════════════════════════
#  Stats
# ═══════════════════════════════════════

@app.get("/stats")
async def stats():
    now = time.time()
    async with aiosqlite.connect(str(DB)) as db:
        m = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM messages"))[0][0]
        mem_active = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM memories WHERE is_latest=1"))[0][0]
        mem_superseded = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM memories WHERE is_latest=0"))[0][0]
        relations = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM memory_relations"))[0][0]
        profile_static = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM profile "
            "WHERE profile_type='static' AND is_active=1"))[0][0]
        profile_dynamic = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM profile "
            "WHERE profile_type='dynamic' AND is_active=1 "
            "AND ts > ?", (now - 72*3600,)))[0][0]
        s = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM summaries"))[0][0]
        e = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM emotional_state"))[0][0]
        p = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM learned_patterns"))[0][0]

    return {
        "messages": m,
        "memories_active": mem_active,
        "memories_superseded": mem_superseded,
        "memory_relations": relations,
        "profile_static": profile_static,
        "profile_dynamic": profile_dynamic,
        "summaries": s,
        "emotional_updates": e,
        "patterns": p,
        "semantic_search": semantic_search.is_ready(),
    }


@app.get("/memories/semantic")
async def semantic_search_endpoint(q: str, limit: int = 5):
    """Direct semantic search endpoint."""
    if not semantic_search.is_ready():
        return {"error": "Semantic search not available. Is Qdrant running?"}
    results = await semantic_search.search_similar(q, limit)
    return {"results": results, "count": len(results)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "jarvis-memory",
            "version": "3.1", "engine": "supermemory-offline",
            "semantic_search": semantic_search.is_ready()}
