import sqlite3
import uuid

class TaskQueue:
    def __init__(self, db):
        self.db=db
        with sqlite3.connect(db) as c:
            c.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, project TEXT NOT NULL, goal TEXT NOT NULL, state TEXT NOT NULL, evidence TEXT)")
    def create(self, project, goal):
        if not project.strip() or not goal.strip():
            raise ValueError("project and goal required")
        task=uuid.uuid4().hex
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO tasks VALUES (?,?,?,'queued',NULL)",(task,project,goal))
        return task
    def claim(self, project):
        with sqlite3.connect(self.db) as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT id,goal FROM tasks WHERE project=? AND state='queued' ORDER BY rowid LIMIT 1",(project,)).fetchone()
            if row:
                c.execute("UPDATE tasks SET state='running' WHERE id=?",(row[0],))
            return row
    def complete(self, project, task, evidence):
        if not evidence.strip():
            raise ValueError("evidence required")
        with sqlite3.connect(self.db) as c:
            result=c.execute("UPDATE tasks SET state='completed',evidence=? WHERE id=? AND project=? AND state='running'",(evidence,task,project))
            if result.rowcount!=1:
                raise ValueError("task not running in project")
    def running(self, project):
        with sqlite3.connect(self.db) as c:
            return c.execute("SELECT id,goal FROM tasks WHERE project=? AND state='running'",(project,)).fetchall()
