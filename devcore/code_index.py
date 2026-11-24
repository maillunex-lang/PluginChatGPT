"""Incremental source-symbol index for Python, GDScript and JS/TS."""
import ast
import hashlib
import os
import re
from pathlib import Path

import psycopg
from devcore.state_postgres import DevCoreStore

SUFFIXES={".py",".gd",".js",".jsx",".ts",".tsx"}
EXCLUDED={".git",".venv","venv","node_modules",".godot","build","dist",".next","__pycache__","target"}
GD=re.compile(r"^\s*(class_name|func|signal)\s+([A-Za-z_][A-Za-z_0-9]*)",re.M)
JS=re.compile(r"\b(?:export\s+)?(?:(?:default|async|declare)\s+)*(function|class|interface|type)\s+([A-Za-z_$][A-Za-z_$0-9]*)")

def extract(path: Path, body: str):
    if path.suffix==".py":
        try:
            module=ast.parse(body)
        except SyntaxError as e:
            return [],f"SyntaxError line {e.lineno}: {e.msg}"
        symbols=[]
        for node in ast.walk(module):
            if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                kind="class" if isinstance(node,ast.ClassDef) else "function"
                symbols.append((node.name,kind,node.lineno))
        return symbols,None
    if path.suffix==".gd":
        return [(m.group(2),m.group(1),body[:m.start()].count("\n")+1)
                for m in GD.finditer(body)],None
    return [(m.group(2),m.group(1),body[:m.start()].count("\n")+1)
            for m in JS.finditer(body)],None


class CodeIndex:
    def __init__(self, dsn: str):
        self.store=DevCoreStore(dsn)
        self.migrate()

    def migrate(self):
        with self.store.connection() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS devcore_index_files (
                    project_id TEXT NOT NULL REFERENCES devcore_projects(project_id),
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    mtime_ns BIGINT NOT NULL,
                    error TEXT,
                    PRIMARY KEY(project_id,path)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS devcore_index_symbols (
                    project_id TEXT NOT NULL REFERENCES devcore_projects(project_id),
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    PRIMARY KEY(project_id,path,name,kind,line)
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS devcore_symbols_project_name
                ON devcore_index_symbols(project_id,name)
            """)

    def index(self, project_id: str, max_files: int = 10000):
        projects=self.store.list_projects()
        project=next((p for p in projects if p["project_id"]==project_id),None)
        if not project:
            raise ValueError("Project must be registered")
        root=Path(project["root"]).resolve(strict=True)
        max_files=max(1,min(max_files,30000))
        found=set(); scanned=0; changed=0; errors=[]
        with self.store.connection() as c:
            for folder,dirs,files in os.walk(root):
                dirs[:]=[d for d in dirs if d not in EXCLUDED
                         and not (Path(folder)/d).is_symlink()]
                for filename in files:
                    p=Path(folder)/filename
                    if p.suffix.lower() not in SUFFIXES or p.is_symlink():
                        continue
                    if scanned>=max_files:
                        break
                    try:
                        rel=p.relative_to(root).as_posix()
                        stat=p.stat()
                    except (OSError,ValueError):
                        continue
                    found.add(rel);scanned+=1
                    old=c.execute("""
                        SELECT size,mtime_ns FROM devcore_index_files
                        WHERE project_id=%s AND path=%s
                    """,(project_id,rel)).fetchone()
                    if old and old["size"]==stat.st_size and old["mtime_ns"]==stat.st_mtime_ns:
                        continue
                    if stat.st_size>512_000:
                        errors.append(rel+": skipped oversized file")
                        continue
                    try:
                        blob=p.read_bytes()
                        body=blob.decode("utf-8")
                    except (OSError,UnicodeError):
                        errors.append(rel+": unreadable")
                        continue
                    symbols,error=extract(p,body)
                    if error:
                        errors.append(rel+": "+error)
                    c.execute("""
                        INSERT INTO devcore_index_files(project_id,path,sha256,size,mtime_ns,error)
                        VALUES(%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(project_id,path)
                        DO UPDATE SET sha256=excluded.sha256,size=excluded.size,
                            mtime_ns=excluded.mtime_ns,error=excluded.error
                    """,(project_id,rel,hashlib.sha256(blob).hexdigest(),
                         len(blob),stat.st_mtime_ns,error))
                    c.execute("DELETE FROM devcore_index_symbols WHERE project_id=%s AND path=%s",
                              (project_id,rel))
                    for name,kind,line in symbols:
                        c.execute("""
                            INSERT INTO devcore_index_symbols(project_id,path,name,kind,line)
                            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                        """,(project_id,rel,name,kind,line))
                    changed+=1
                if scanned>=max_files:
                    break
            if scanned<max_files:
                c.execute("""
                    DELETE FROM devcore_index_symbols WHERE project_id=%s
                    AND path != ALL(%s)
                """,(project_id,list(found)))
                c.execute("""
                    DELETE FROM devcore_index_files WHERE project_id=%s
                    AND path != ALL(%s)
                """,(project_id,list(found)))
        return {"project_id":project_id,"scanned":scanned,"updated":changed,
                "truncated":scanned>=max_files,"errors":errors[:30]}

    def search(self, project_id: str, query: str, limit: int = 30):
        if not query.strip():
            return []
        with self.store.connection() as c:
            return list(c.execute("""
                SELECT path,name,kind,line FROM devcore_index_symbols
                WHERE project_id=%s AND name ILIKE %s
                ORDER BY name,path,line LIMIT %s
            """,(project_id,"%"+query+"%",max(1,min(limit,100)))).fetchall())
