"""Owner-only server operations; uses system root context by approved policy.

These helpers do not impose directory or command allowlists.
Transport output is bounded to avoid overwhelming the MCP response.
"""
import os
import signal
import subprocess
import tempfile
from pathlib import Path


def execute(command: str, cwd: str | None = None, timeout: int = 30) -> dict:
    if not command.strip():
        raise ValueError("Command cannot be empty")
    timeout=max(1,min(300,int(timeout)))
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        proc=subprocess.Popen(command,shell=True,executable="/bin/bash",cwd=cwd,
                              stdout=stdout,stderr=stderr,start_new_session=True)
        timed_out=False
        try:
            exit_code=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            os.killpg(proc.pid,signal.SIGKILL)
            exit_code=proc.wait(timeout=10)
        stdout.seek(0)
        stderr.seek(0)
        out=stdout.read(16384).decode("utf-8",errors="replace")
        err=stderr.read(8192).decode("utf-8",errors="replace")
        return {"exit_code":exit_code,"timed_out":timed_out,
                "stdout":out,"stderr":err}


def read_text(path: str, max_chars: int = 32768) -> dict:
    max_chars=max(1,min(250000,max_chars))
    with open(path,"r",encoding="utf-8") as f:
        content=f.read(max_chars+1)
    return {"path":path,"content":content[:max_chars],"truncated":len(content)>max_chars}


def write_text(path: str, content: str) -> dict:
    target=Path(path)
    if not target.is_absolute():
        raise ValueError("Absolute path required")
    # Preserve existing file permissions, but never follow a dangling symlink
    old_mode=target.stat().st_mode & 0o777 if target.exists() else 0o600
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",
                                     dir=target.parent,delete=False) as f:
        temp=f.name
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(temp,old_mode)
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {"path":path,"bytes":len(content.encode("utf-8"))}
