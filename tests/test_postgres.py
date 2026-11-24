"""Integration tests run only when DEVCORE_DATABASE_URL is configured."""
import os
from uuid import uuid4

import psycopg
import pytest
from devcore.state_postgres import DevCoreStore

pytestmark=pytest.mark.skipif(
    not os.getenv("DEVCORE_DATABASE_URL"),reason="PostgreSQL integration DB not configured"
)


def test_project_memory_and_tasks():
    dsn=os.environ["DEVCORE_DATABASE_URL"]
    store=DevCoreStore(dsn)
    store.migrate()
    prefix="devcore-pytest-"+uuid4().hex
    first=prefix+"-a"
    second=prefix+"-b"
    try:
        store.add_project(first,"/tmp/"+first,"")
        store.add_project(second,"/tmp/"+second,"")
        a=store.save_memory(first,"decision","Use Godot",priority=1,source="approved")
        b=store.save_memory(second,"decision","Use Cocos",priority=1)
        assert len(store.search_memory(first))==1
        assert not store.search_memory(first,"Cocos")
        assert "Godot" in store.context_load(first)["context"]
        with pytest.raises(ValueError):
            store.save_memory(first,"decision","Other",supersedes=b)
        new=store.save_memory(first,"decision","Use Godot 4.7",supersedes=a)
        assert len(store.search_memory(first))==1
        assert store.search_memory(first)[0]["id"]==__import__("uuid").UUID(new)
        task=store.create_task(first,"Build APK")
        assert store.claim_task(second) is None
        claimed=store.claim_task(first)
        assert str(claimed["id"])==task
        store.checkpoint_task(first,task,"Analyzed dependencies")
        with pytest.raises(ValueError):
            store.complete_task(second,task,"passed")
        with pytest.raises(ValueError):
            store.complete_task(first,task,"")
        store.pause_task(first,task)
        store.resume_task(first,task)
        assert str(store.claim_task(first)["id"])==task
        store.complete_task(first,task,"pytest passed")
        assert store.task_status(first)[0]["state"]=="completed"
        assert store.task_status(first)[0]["checkpoint"]=="Analyzed dependencies"
    finally:
        with psycopg.connect(dsn) as c:
            c.execute("DELETE FROM devcore_tasks WHERE project_id IN (%s,%s)",(first,second))
            c.execute("DELETE FROM devcore_memories WHERE project_id IN (%s,%s)",(first,second))
            c.execute("DELETE FROM devcore_projects WHERE project_id IN (%s,%s)",(first,second))


def test_duplicate_project_is_rejected():
    dsn=os.environ["DEVCORE_DATABASE_URL"]
    store=DevCoreStore(dsn)
    project="devcore-pytest-"+uuid4().hex
    try:
        store.add_project(project,"/tmp/"+project,"")
        with pytest.raises(psycopg.errors.UniqueViolation):
            store.add_project(project,"/tmp/"+project,"")
    finally:
        with psycopg.connect(dsn) as c:
            c.execute("DELETE FROM devcore_projects WHERE project_id=%s",(project,))
