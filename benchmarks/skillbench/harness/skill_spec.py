from __future__ import annotations

import pathlib
import re
import shutil
from dataclasses import dataclass
from typing import Dict, Tuple

import yaml


_FRONTMATTER_RE = re.compile(r"^---\s*$", re.MULTILINE)


@dataclass
class SkillSpec:
    name: str
    description: str
    frontmatter: Dict
    body: str
    path: pathlib.Path

    @property
    def slug(self) -> str:
        base = self.name.strip().lower().replace(" ", "-")
        base = re.sub(r"[^a-z0-9_-]+", "", base)
        return base or self.path.name


def _split_frontmatter(text: str) -> Tuple[Dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md missing YAML frontmatter (expected leading '---').")

    try:
        end_index = lines[1:].index("---") + 1
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter not closed with '---'.") from exc

    frontmatter_text = "\n".join(lines[1:end_index])
    body_text = "\n".join(lines[end_index + 1 :]).strip()
    frontmatter = yaml.safe_load(frontmatter_text) or {}
    return frontmatter, body_text


def load_skill(skill_dir: pathlib.Path) -> SkillSpec:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"Missing SKILL.md in {skill_dir}")

    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    if not name or not description:
        raise ValueError("SKILL.md frontmatter must include 'name' and 'description'.")

    return SkillSpec(
        name=name,
        description=description,
        frontmatter=frontmatter,
        body=body,
        path=skill_dir,
    )


def install_skill(skill: SkillSpec, dest_root: pathlib.Path) -> pathlib.Path:
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / skill.slug
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(skill.path, dest)
    return dest
