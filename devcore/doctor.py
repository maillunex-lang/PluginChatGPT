"""Read-only DevCore diagnostics with no secret values in responses."""
import os
import shutil
import socket
import subprocess
from pathlib import Path

def doctor(root: str = "/opt/lunex-devcore", database_url: str | None = None):
    checks=[]
    root=Path(root)
    checks.append({"name":"project_directory","ok":root.is_dir()})
    checks.append({"name":"python_environment","ok":(root/".venv/bin/python").is_file()})
    checks.append({"name":"github_checkout","ok":(root/".git").is_dir()})
    free=shutil.disk_usage(root if root.is_dir() else "/").free
    checks.append({"name":"disk_free_2gb","ok":free>2*1024**3,"free_bytes":free})
    for port,label in ((18791,"mcp_loopback"),(15465,"postgres_loopback")):
        try:
            with socket.create_connection(("127.0.0.1",port),timeout=0.5):
                available=True
        except OSError:
            available=False
        checks.append({"name":label,"ok":available})
    if database_url:
        try:
            import psycopg
            with psycopg.connect(database_url,connect_timeout=2) as connection:
                value=connection.execute("SELECT 1").fetchone()[0]
                checks.append({"name":"postgres_query","ok":value==1})
        except Exception:
            checks.append({"name":"postgres_query","ok":False})
    return {"status":"ok" if all(x["ok"] for x in checks) else "degraded","checks":checks}
