"""Versioned local skill catalog and deterministic task router."""
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / "skills" / "catalog.json"


class SkillEngine:
    def __init__(self, catalog: str | Path = CATALOG):
        raw=json.loads(Path(catalog).read_text(encoding="utf-8"))
        self.skills={s["id"]:s for s in raw["skills"]}
        if len(self.skills)!=len(raw["skills"]):
            raise ValueError("Duplicate skill ids")

    def list(self):
        return [{"id":s["id"],"description":s["description"],"version":s["version"]}
                for s in self.skills.values()]

    def load(self, identifier: str):
        if identifier not in self.skills:
            raise ValueError("Unknown skill")
        return self.skills[identifier]

    def route(self, task: str, max_skills: int = 3):
        query=task.casefold()
        matches=[]
        for entry in self.skills.values():
            hits=sum(1 for word in entry["keywords"] if word.casefold() in query)
            if hits:
                matches.append((hits,entry["id"]))
        matches.sort(key=lambda row:(-row[0],row[1]))
        return [identifier for _,identifier in matches[:max(1,min(5,max_skills))]] or ["project-director"]
