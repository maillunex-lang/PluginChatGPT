import sqlite3
from pathlib import Path

class Registry:
    def __init__(self, db):
        self.db=Path(db)
        with self.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, root TEXT NOT NULL, repo TEXT NOT NULL)")
    def connect(self):
        return sqlite3.connect(self.db)
    def add(self, project_id, root, repo):
        if not project_id or not Path(root).is_absolute():
            raise ValueError("project id and absolute root required")
        with self.connect() as c:
            c.execute("INSERT INTO projects VALUES (?,?,?)",(project_id,str(Path(root).resolve()),repo))
    def list(self):
        with self.connect() as c:
            return c.execute("SELECT id,root,repo FROM projects ORDER BY id").fetchall()
