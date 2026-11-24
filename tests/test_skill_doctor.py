import json
from devcore.skills_engine import SkillEngine
from devcore.doctor import doctor

def test_approved_skills():
    skills=SkillEngine()
    assert len(skills.list())==20
    assert "godot-expert" in skills.route("Fix Godot 4 gdscript scene")
    assert "database-expert" in skills.route("Оптимизация PostgreSQL базы данных")
    assert skills.route("Новая неизвестная задача")==["project-director"]
    assert skills.load("qa-engineer")["version"]=="0.1"

def test_doctor_readonly(tmp_path):
    state=doctor(str(tmp_path))
    assert state["status"]=="degraded"
    assert next(c for c in state["checks"] if c["name"]=="project_directory")["ok"]
    assert not next(c for c in state["checks"] if c["name"]=="github_checkout")["ok"]
