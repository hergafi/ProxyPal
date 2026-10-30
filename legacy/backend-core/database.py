"""
Database module for quota tracking and persistence
"""
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager
from backend.core.config import DB_PATH

@contextmanager
def get_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize database schema"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quota (
                qkey TEXT PRIMARY KEY,
                requests INTEGER DEFAULT 0,
                tokens INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0,
                healthy INTEGER DEFAULT 1,
                latency_ms INTEGER,
                last_used REAL,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT,
                provider TEXT,
                tokens_used INTEGER,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                preferences TEXT,
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

def quota_load(qkey: str) -> Dict[str, Any]:
    """Load quota data for a specific key"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT requests, tokens, errors, healthy, latency_ms, last_used FROM quota WHERE qkey=?",
            (qkey,)
        ).fetchone()
        
        if row:
            return {
                "requests": row[0],
                "tokens": row[1],
                "errors": row[2],
                "healthy": bool(row[3]),
                "latency_ms": row[4],
                "last_used": row[5]
            }
        
        return {
            "requests": 0,
            "tokens": 0,
            "errors": 0,
            "healthy": True,
            "latency_ms": None,
            "last_used": None
        }

def quota_save(qkey: str, quota_data: Dict[str, Any]) -> None:
    """Save quota data for a specific key"""
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO quota 
               (qkey, requests, tokens, errors, healthy, latency_ms, last_used, updated_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))""",
            (
                qkey,
                quota_data["requests"],
                quota_data["tokens"],
                quota_data["errors"],
                int(quota_data["healthy"]),
                quota_data.get("latency_ms"),
                quota_data.get("last_used")
            )
        )

def save_conversation(session_id: str, role: str, content: str, 
                     model: Optional[str] = None, provider: Optional[str] = None,
                     tokens_used: Optional[int] = None) -> None:
    """Save conversation message to history"""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO conversation_history 
               (session_id, role, content, model, provider, tokens_used) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, model, provider, tokens_used)
        )

def get_conversation_history(session_id: str, limit: int = 50) -> list:
    """Retrieve conversation history"""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT role, content, model, provider, tokens_used, created_at 
               FROM conversation_history 
               WHERE session_id=? 
               ORDER BY created_at ASC 
               LIMIT ?""",
            (session_id, limit)
        ).fetchall()
        
        return [
            {
                "role": row[0],
                "content": row[1],
                "model": row[2],
                "provider": row[3],
                "tokens_used": row[4],
                "timestamp": row[5]
            }
            for row in rows
        ]

def reset_quota(qkey: str) -> None:
    """Reset quota counters for a specific key"""
    with get_connection() as conn:
        conn.execute(
            """UPDATE quota 
               SET requests=0, tokens=0, errors=0, updated_at=strftime('%s', 'now') 
               WHERE qkey=?""",
            (qkey,)
        )

def get_all_quotas() -> Dict[str, Dict[str, Any]]:
    """Get all quota data"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT qkey, requests, tokens, errors, healthy, latency_ms, last_used FROM quota"
        ).fetchall()
        
        return {
            row[0]: {
                "requests": row[1],
                "tokens": row[2],
                "errors": row[3],
                "healthy": bool(row[4]),
                "latency_ms": row[5],
                "last_used": row[6]
            }
            for row in rows
        }
