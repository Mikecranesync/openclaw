"""Skill discovery and registration."""

from __future__ import annotations

import logging

from openclaw.skills.base import Skill
from openclaw.types import Intent

logger = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[Intent, Skill] = {}
        self._all: list[Skill] = []

    def register(self, skill: Skill) -> None:
        self._all.append(skill)
        for intent in skill.intents():
            self._skills[intent] = skill
            logger.info("Registered skill %s for intent %s", skill.name(), intent.value)

    def get(self, intent: Intent) -> Skill | None:
        return self._skills.get(intent)

    def all_skills(self) -> list[Skill]:
        return list(self._all)

    def register_builtins(self) -> None:
        """Register all built-in skills."""
        from openclaw.skills.builtin.admin import AdminSkill
        from openclaw.skills.builtin.chat import ChatSkill
        from openclaw.skills.builtin.diagram import DiagramSkill
        from openclaw.skills.builtin.diagnose import DiagnoseSkill
        from openclaw.skills.builtin.photo import PhotoSkill
        from openclaw.skills.builtin.search import SearchSkill
        from openclaw.skills.builtin.shell import ShellSkill
        from openclaw.skills.builtin.status import StatusSkill
        from openclaw.skills.builtin.work_order import WorkOrderSkill

        for skill_cls in [DiagnoseSkill, StatusSkill, PhotoSkill, WorkOrderSkill, AdminSkill, SearchSkill, ShellSkill, DiagramSkill, ChatSkill]:
            self.register(skill_cls())
