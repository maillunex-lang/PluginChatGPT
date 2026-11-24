"""Project-isolated durable state in a dedicated PostgreSQL database."""
from dataclasses import dataclass
from uuid import UUID
import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class DevCoreStore:
    dsn: str

    def connection(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def migrate(self):
        with self.connection() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS devcore_projects (
                    project_id TEXT PRIMARY KEY,
                    root TEXT NOT NULL,
                    repository TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS devcore_memories (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id TEXT NOT NULL REFERENCES devcore_projects(project_id),
                    category TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    priority SMALLINT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 0 AND 5),
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','superseded','archived')),
                    supersedes UUID REFERENCES devcore_memories(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS devcore_memory_project_active
                    ON devcore_memories(project_id,priority,created_at DESC)
                    WHERE status='active'
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS devcore_tasks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id TEXT NOT NULL REFERENCES devcore_projects(project_id),
                    goal TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued'
                        CHECK (state IN ('queued','running','completed','failed','paused')),
                    evidence TEXT NOT NULL DEFAULT '',
                    checkpoint TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS devcore_task_project_state
                    ON devcore_tasks(project_id,state,created_at)
            """)

    def add_project(self, project_id: str, root: str, repository: str = ""):
        if not project_id.strip() or not root.startswith("/"):
            raise ValueError("Nonempty project_id and absolute root required")
        with self.connection() as c:
            c.execute(
                "INSERT INTO devcore_projects(project_id,root,repository) VALUES(%s,%s,%s)",
                (project_id,root,repository)
            )
        return project_id

    def list_projects(self):
        with self.connection() as c:
            return list(c.execute(
                "SELECT project_id,root,repository FROM devcore_projects ORDER BY project_id"
            ).fetchall())

    def save_memory(self, project_id: str, category: str, body: str,
                    source: str = "", priority: int = 3,
                    supersedes: str | None = None) -> str:
        if not category.strip() or not body.strip():
            raise ValueError("Memory category and body required")
        if not 0 <= priority <= 5:
            raise ValueError("Memory priority must be 0..5")
        with self.connection() as c:
            if supersedes:
                old = c.execute("""
                    SELECT id FROM devcore_memories
                    WHERE id=%s AND project_id=%s AND status='active' FOR UPDATE
                """,(supersedes,project_id)).fetchone()
                if not old:
                    raise ValueError("Cannot supersede another project's or inactive memory")
                c.execute("UPDATE devcore_memories SET status='superseded' WHERE id=%s",
                          (supersedes,))
            new = c.execute("""
                INSERT INTO devcore_memories(project_id,category,body,source,priority,supersedes)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING id
            """,(project_id,category,body,source,priority,supersedes)).fetchone()
        return str(new["id"])

    def search_memory(self, project_id: str, query: str = "", limit: int = 20):
        limit = max(1,min(100,limit))
        with self.connection() as c:
            return list(c.execute("""
                SELECT id,category,body,source,priority,created_at
                FROM devcore_memories
                WHERE project_id=%s AND status='active'
                AND (%s='' OR body ILIKE %s OR category ILIKE %s)
                ORDER BY priority ASC,created_at DESC LIMIT %s
            """,(project_id,query,"%"+query+"%","%"+query+"%",limit)).fetchall())

    def context_load(self, project_id: str, budget_chars: int = 15000):
        budget_chars=max(256,min(100000,budget_chars))
        items=self.search_memory(project_id,limit=100)
        lines=[]; used=0
        for item in items:
            line=f"[{item['category']},P{item['priority']}] {item['body']}"
            if used+len(line)+1>budget_chars:
                continue
            lines.append(line)
            used+=len(line)+1
        return {"project_id":project_id,"context":"\n".join(lines),
                "selected":len(lines),"total":len(items),"budget_chars":budget_chars}

    def create_task(self, project_id: str, goal: str) -> str:
        if not goal.strip():
            raise ValueError("Task goal required")
        with self.connection() as c:
            row=c.execute("""
                INSERT INTO devcore_tasks(project_id,goal)
                VALUES(%s,%s) RETURNING id
            """,(project_id,goal)).fetchone()
        return str(row["id"])

    def claim_task(self, project_id: str):
        with self.connection() as c:
            row=c.execute("""
                SELECT id,goal FROM devcore_tasks
                WHERE project_id=%s AND state='queued'
                ORDER BY created_at,id LIMIT 1
                FOR UPDATE SKIP LOCKED
            """,(project_id,)).fetchone()
            if row:
                c.execute("""
                    UPDATE devcore_tasks SET state='running',updated_at=now()
                    WHERE id=%s
                """,(row["id"],))
                return dict(row)
        return None

    def checkpoint_task(self, project_id: str, task_id: str, note: str):
        if not note.strip():
            raise ValueError("Checkpoint cannot be empty")
        with self.connection() as c:
            n=c.execute("""
                UPDATE devcore_tasks SET checkpoint=%s,updated_at=now()
                WHERE project_id=%s AND id=%s AND state='running'
            """,(note,project_id,task_id)).rowcount
            if n!=1:
                raise ValueError("Task not running in project")

    def complete_task(self, project_id: str, task_id: str, evidence: str):
        if not evidence.strip():
            raise ValueError("Completion requires evidence")
        with self.connection() as c:
            n=c.execute("""
                UPDATE devcore_tasks SET state='completed',evidence=%s,updated_at=now()
                WHERE project_id=%s AND id=%s AND state='running'
            """,(evidence,project_id,task_id)).rowcount
            if n!=1:
                raise ValueError("Task not running in project")

    def task_status(self, project_id: str, limit: int = 50):
        with self.connection() as c:
            return list(c.execute("""
                SELECT id,goal,state,evidence,checkpoint,created_at,updated_at
                FROM devcore_tasks WHERE project_id=%s
                ORDER BY created_at DESC LIMIT %s
            """,(project_id,max(1,min(100,limit)))).fetchall())

    def pause_task(self, project_id: str, task_id: str):
        with self.connection() as c:
            n=c.execute("""
                UPDATE devcore_tasks SET state='paused',updated_at=now()
                WHERE project_id=%s AND id=%s AND state='running'
            """,(project_id,task_id)).rowcount
            if n!=1:
                raise ValueError("Task not running in project")

    def resume_task(self, project_id: str, task_id: str):
        with self.connection() as c:
            n=c.execute("""
                UPDATE devcore_tasks SET state='queued',updated_at=now()
                WHERE project_id=%s AND id=%s AND state='paused'
            """,(project_id,task_id)).rowcount
            if n!=1:
                raise ValueError("Task not paused in project")
