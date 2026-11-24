import os
import pytest
from devcore.system_ops import execute, read_text, write_text

def test_owner_shell(tmp_path):
    response=execute("printf 'devcore-verified\\n'",cwd=str(tmp_path))
    assert response["exit_code"]==0
    assert response["stdout"]=="devcore-verified\n"
    response=execute("exit 11")
    assert response["exit_code"]==11
    assert response["timed_out"] is False

def test_owner_file_io(tmp_path):
    path=str(tmp_path/"file.txt")
    assert write_text(path,"hello")["bytes"]==5
    assert read_text(path)["content"]=="hello"
    assert read_text(path,max_chars=2)["truncated"] is True
    with pytest.raises(ValueError):
        write_text("relative.txt","data")
