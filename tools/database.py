"""
Database layer for the AI Intelligence System.
SQLite-backed storage for sources, content, insights, ideas, and feedback.
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "intelligence.db")

DEFAULT_SOURCES = [
    ("r/AI_Agents", "reddit", "https://reddit.com/r/AI_Agents", 8.0),
    ("r/artificial", "reddit", "https://reddit.com/r/artificial", 7.0),
    ("r/automation", "reddit", "https://reddit.com/r/automation", 6.5),
    ("r/cofounder", "reddit", "https://reddit.com/r/cofounder", 6.0),
    ("r/founder", "reddit", "https://reddit.com/r/founder", 6.5),
    ("r/microsaas", "reddit", "https://reddit.com/r/microsaas", 8.5),
    ("r/SideProject", "reddit", "https://reddit.com/r/SideProject", 7.0),
    ("r/producthuntlaunches", "reddit", "https://reddit.com/r/producthuntlaunches", 6.5),
    ("r/smallbusiness", "reddit", "https://reddit.com/r/smallbusiness", 6.0),
    ("r/upwork", "reddit", "https://reddit.com/r/upwork", 5.5),
    ("r/entrepreneur", "reddit", "https://reddit.com/r/entrepreneur", 7.0),
    ("r/freelance", "reddit", "https://reddit.com/r/freelance", 5.5),
]


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'reddit',
                url TEXT,
                authority_score REAL DEFAULT 5.0,
                last_collected_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                external_id TEXT UNIQUE,
                title TEXT,
                body TEXT,
                url TEXT,
                author TEXT,
                score INTEGER DEFAULT 0,
                num_comments INTEGER DEFAULT 0,
                engagement_score REAL DEFAULT 0.0,
                collected_at TEXT DEFAULT (datetime('now')),
                posted_at TEXT,
                processed INTEGER DEFAULT 0,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id INTEGER NOT NULL,
                insight_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                entities TEXT,
                sentiment REAL DEFAULT 0.0,
                urgency_signals TEXT,
                confidence REAL DEFAULT 0.5,
                embedding TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (content_id) REFERENCES content(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                insight_ids TEXT,
                momentum_score REAL DEFAULT 0.0,
                buildability_score REAL DEFAULT 0.0,
                urgency_score REAL DEFAULT 0.0,
                combined_score REAL DEFAULT 0.0,
                effort_estimate TEXT DEFAULT 'unknown',
                gap_pattern INTEGER DEFAULT 0,
                source_subreddits TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_id INTEGER NOT NULL,
                feedback_type TEXT NOT NULL,
                rating INTEGER,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (idea_id) REFERENCES ideas(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_id INTEGER,
                prediction TEXT NOT NULL,
                predicted_at TEXT DEFAULT (datetime('now')),
                outcome TEXT,
                resolved_at TEXT,
                accurate INTEGER,
                FOREIGN KEY (idea_id) REFERENCES ideas(id)
            )
        """)

        # Indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_processed ON content(processed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_source ON content(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ideas_combined ON ideas(combined_score DESC)")

        self.conn.commit()

    # --- Sources ---

    def add_source(self, name, source_type="reddit", url=None, authority_score=5.0):
        try:
            self.conn.execute(
                "INSERT INTO sources (name, source_type, url, authority_score) VALUES (?, ?, ?, ?)",
                (name, source_type, url, authority_score),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_sources(self, source_type=None):
        if source_type:
            return self.conn.execute(
                "SELECT * FROM sources WHERE source_type = ?", (source_type,)
            ).fetchall()
        return self.conn.execute("SELECT * FROM sources").fetchall()

    def update_source_collected(self, source_id):
        self.conn.execute(
            "UPDATE sources SET last_collected_at = datetime('now') WHERE id = ?",
            (source_id,),
        )
        self.conn.commit()

    # --- Content ---

    def add_content(self, source_id, external_id, title, body, url, author,
                    score, num_comments, engagement_score, posted_at):
        try:
            self.conn.execute(
                """INSERT INTO content
                   (source_id, external_id, title, body, url, author, score,
                    num_comments, engagement_score, posted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_id, external_id, title, body, url, author, score,
                 num_comments, engagement_score, posted_at),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_unprocessed_content(self, limit=50):
        return self.conn.execute(
            """SELECT c.*, s.name as source_name, s.authority_score
               FROM content c JOIN sources s ON c.source_id = s.id
               WHERE c.processed = 0
               ORDER BY c.engagement_score DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    def mark_content_processed(self, content_id):
        self.conn.execute(
            "UPDATE content SET processed = 1 WHERE id = ?", (content_id,)
        )
        self.conn.commit()

    def content_exists(self, external_id):
        row = self.conn.execute(
            "SELECT 1 FROM content WHERE external_id = ?", (external_id,)
        ).fetchone()
        return row is not None

    # --- Insights ---

    def add_insight(self, content_id, insight_type, summary, entities=None,
                    sentiment=0.0, urgency_signals=None, confidence=0.5, embedding=None):
        entities_json = json.dumps(entities) if entities else None
        signals_json = json.dumps(urgency_signals) if urgency_signals else None
        cursor = self.conn.execute(
            """INSERT INTO insights
               (content_id, insight_type, summary, entities, sentiment,
                urgency_signals, confidence, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (content_id, insight_type, summary, entities_json, sentiment,
             signals_json, confidence, embedding),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_insights(self, insight_type=None, days=7):
        if insight_type:
            return self.conn.execute(
                """SELECT i.*, c.title as content_title, c.url as content_url,
                          c.score as post_score, c.num_comments, c.engagement_score,
                          s.name as source_name, s.authority_score
                   FROM insights i
                   JOIN content c ON i.content_id = c.id
                   JOIN sources s ON c.source_id = s.id
                   WHERE i.insight_type = ?
                     AND i.created_at >= datetime('now', ?)
                   ORDER BY i.confidence DESC""",
                (insight_type, f"-{days} days"),
            ).fetchall()
        return self.conn.execute(
            """SELECT i.*, c.title as content_title, c.url as content_url,
                      c.score as post_score, c.num_comments, c.engagement_score,
                      s.name as source_name, s.authority_score
               FROM insights i
               JOIN content c ON i.content_id = c.id
               JOIN sources s ON c.source_id = s.id
               WHERE i.created_at >= datetime('now', ?)
               ORDER BY i.confidence DESC""",
            (f"-{days} days",),
        ).fetchall()

    # --- Ideas ---

    def add_idea(self, title, description, insight_ids, momentum_score,
                 buildability_score, urgency_score, effort_estimate,
                 gap_pattern, source_subreddits):
        combined = (momentum_score * 0.3 + buildability_score * 0.3 +
                    urgency_score * 0.2 + (3.0 if gap_pattern else 0.0) * 0.2)
        ids_json = json.dumps(insight_ids) if insight_ids else None
        subs_json = json.dumps(source_subreddits) if source_subreddits else None
        cursor = self.conn.execute(
            """INSERT INTO ideas
               (title, description, insight_ids, momentum_score, buildability_score,
                urgency_score, combined_score, effort_estimate, gap_pattern, source_subreddits)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, description, ids_json, momentum_score, buildability_score,
             urgency_score, combined, effort_estimate, int(gap_pattern), subs_json),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_ideas(self, min_score=0.0, limit=50):
        return self.conn.execute(
            """SELECT * FROM ideas
               WHERE combined_score >= ?
               ORDER BY combined_score DESC
               LIMIT ?""",
            (min_score, limit),
        ).fetchall()

    def get_gap_patterns(self, limit=20):
        return self.conn.execute(
            """SELECT * FROM ideas
               WHERE gap_pattern = 1
               ORDER BY combined_score DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    # --- Feedback ---

    def add_feedback(self, idea_id, feedback_type, rating=None, notes=None):
        self.conn.execute(
            "INSERT INTO feedback (idea_id, feedback_type, rating, notes) VALUES (?, ?, ?, ?)",
            (idea_id, feedback_type, rating, notes),
        )
        self.conn.commit()

    # --- Predictions ---

    def add_prediction(self, idea_id, prediction):
        self.conn.execute(
            "INSERT INTO predictions (idea_id, prediction) VALUES (?, ?)",
            (idea_id, prediction),
        )
        self.conn.commit()

    def resolve_prediction(self, prediction_id, outcome, accurate):
        self.conn.execute(
            """UPDATE predictions
               SET outcome = ?, resolved_at = datetime('now'), accurate = ?
               WHERE id = ?""",
            (outcome, int(accurate), prediction_id),
        )
        self.conn.commit()

    # --- Stats ---

    def get_stats(self):
        stats = {}
        for table in ["sources", "content", "insights", "ideas", "feedback", "predictions"]:
            row = self.conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]
        unprocessed = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM content WHERE processed = 0"
        ).fetchone()
        stats["unprocessed_content"] = unprocessed["cnt"]
        return stats

    def seed_defaults(self):
        added = 0
        for name, stype, url, authority in DEFAULT_SOURCES:
            if self.add_source(name, stype, url, authority):
                added += 1
        return added

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    db = Database()
    added = db.seed_defaults()
    stats = db.get_stats()
    print(f"Database initialized at: {db.db_path}")
    print(f"Sources added: {added}")
    print(f"Total sources: {stats['sources']}")
    for src in db.get_sources():
        print(f"  - {src['name']} (authority: {src['authority_score']})")
    db.close()
