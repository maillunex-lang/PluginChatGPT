"""MCP tools backed by isolated DevCore PostgreSQL and owner system access."""
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from devcore.state_postgres import DevCoreStore
from devcore.system_ops import execute, read_text, write_text
from devcore.skills_engine import SkillEngine
from devcore.doctor import doctor


def register_owner_tools(server: FastMCP, dsn: str) -> None:
    store=DevCoreStore(dsn)
    store.migrate()
    skill_engine=SkillEngine()

    @server.tool()
    def devcore_skills_list() -> list[dict]:
        """List the twenty built-in versioned engineering specializations."""
        return skill_engine.list()

    @server.tool()
    def devcore_skill_route(task: str, max_skills: int = 3) -> list[str]:
        """Find applicable skills using transparent deterministic keyword routing."""
        return skill_engine.route(task,max_skills)

    @server.tool()
    def devcore_skill_load(identifier: str) -> dict:
        """Load the metadata and trigger keywords for a local skill."""
        return skill_engine.load(identifier)

    @server.tool()
    def devcore_doctor() -> dict:
        """Read-only inspection of runtime, disk, local services and database."""
        return doctor(database_url=dsn)

    @server.tool()
    def devcore_project_list() -> list[dict]:
        """List registered game and app projects."""
        return store.list_projects()

    @server.tool()
    def devcore_project_add(project_id: str, root: str, repository: str = "") -> dict:
        """Register an existing project by its absolute filesystem path."""
        store.add_project(project_id,root,repository)
        return {"project_id":project_id,"status":"registered"}

    @server.tool()
    def devcore_memory_save(project_id: str, category: str, body: str,
                            source: str = "", priority: int = 3,
                            supersedes: str | None = None) -> dict:
        """Remember an approved decision or other verified project fact."""
        id=store.save_memory(project_id,category,body,source,priority,supersedes)
        return {"memory_id":id,"status":"saved"}

    @server.tool()
    def devcore_memory_search(project_id: str, query: str = "", limit: int = 20) -> list[dict]:
        """Retrieve current project-isolated memory records."""
        return store.search_memory(project_id,query,limit)

    @server.tool()
    def devcore_context_load(project_id: str, budget_chars: int = 15000) -> dict:
        """Assemble task-relevant approved project memory with a size budget."""
        return store.context_load(project_id,budget_chars)

    @server.tool()
    def devcore_task_create(project_id: str, goal: str) -> dict:
        """Create an actionable task in the persistent queue."""
        return {"task_id":store.create_task(project_id,goal),"status":"queued"}

    @server.tool()
    def devcore_task_next(project_id: str) -> dict:
        """Atomically claim the next queued project task."""
        row=store.claim_task(project_id)
        return {"task":row,"status":"running" if row else "empty"}

    @server.tool()
    def devcore_task_checkpoint(project_id: str, task_id: str, note: str) -> dict:
        """Record a durable checkpoint before an interruption."""
        store.checkpoint_task(project_id,task_id,note)
        return {"task_id":task_id,"status":"checkpointed"}

    @server.tool()
    def devcore_task_complete(project_id: str, task_id: str, evidence: str) -> dict:
        """Finish a task only with verifiable completion evidence."""
        store.complete_task(project_id,task_id,evidence)
        return {"task_id":task_id,"status":"completed"}

    @server.tool()
    def devcore_task_status(project_id: str, limit: int = 50) -> list[dict]:
        """List project tasks and saved checkpoints."""
        return store.task_status(project_id,limit)

    @server.tool()
    def devcore_task_pause(project_id: str, task_id: str) -> dict:
        """Pause a running task while preserving its checkpoint."""
        store.pause_task(project_id,task_id)
        return {"task_id":task_id,"status":"paused"}

    @server.tool()
    def devcore_task_resume(project_id: str, task_id: str) -> dict:
        """Move a paused task back to the queue for explicit execution."""
        store.resume_task(project_id,task_id)
        return {"task_id":task_id,"status":"queued"}

    @server.tool()
    def devcore_owner_execute(command: str, cwd: str | None = None,
                              timeout: int = 30) -> dict:
        """Owner Full Access: execute an approved shell command on the VPS."""
        return execute(command,cwd,timeout)

    @server.tool()
    def devcore_owner_read(path: str, max_chars: int = 32768) -> dict:
        """Owner Full Access: read a UTF-8 file at an absolute path."""
        return read_text(path,max_chars)

    @server.tool()
    def devcore_owner_write(path: str, content: str) -> dict:
        """Owner Full Access: replace a UTF-8 file, using an atomic write."""
        return write_text(path,content)
