import os
from uuid import uuid4
import pytest
import psycopg
from devcore.code_index import CodeIndex
from devcore.state_postgres import DevCoreStore

pytestmark=pytest.mark.skipif(not os.getenv("DEVCORE_DATABASE_URL"),
                              reason="PostgreSQL integration DB not configured")

def test_index_and_incremental_search(tmp_path):
    dsn=os.environ["DEVCORE_DATABASE_URL"]
    project="code-index-pytest-"+uuid4().hex
    store=DevCoreStore(dsn)
    store.add_project(project,str(tmp_path))
    (tmp_path/"a.py").write_text("class Sample:\n    def hello(self): pass\n")
    (tmp_path/"b.gd").write_text("class_name GameWorld\nfunc attack():\n    pass\n")
    (tmp_path/"c.ts").write_text("export function createGame() {}")
    (tmp_path/".venv").mkdir()
    (tmp_path/".venv"/"ignored.py").write_text("def hidden(): pass")
    try:
        index=CodeIndex(dsn)
        first=index.index(project)
        assert first["scanned"]==3
        assert first["updated"]==3
        assert index.search(project,"GameWorld")[0]["path"]=="b.gd"
        assert index.search(project,"hello")[0]["line"]==2
        assert index.search(project,"createGame")[0]["kind"]=="function"
        assert index.search(project,"hidden")==[]
        assert index.index(project)["updated"]==0
        (tmp_path/"a.py").write_text("def changed(): pass")
        assert index.index(project)["updated"]==1
        assert index.search(project,"hello")==[]
        assert len(index.search(project,"changed"))==1
        (tmp_path/"b.gd").unlink()
        index.index(project)
        assert index.search(project,"GameWorld")==[]
    finally:
        with psycopg.connect(dsn) as c:
            c.execute("DELETE FROM devcore_index_symbols WHERE project_id=%s",(project,))
            c.execute("DELETE FROM devcore_index_files WHERE project_id=%s",(project,))
            c.execute("DELETE FROM devcore_projects WHERE project_id=%s",(project,))
