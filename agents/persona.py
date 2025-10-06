"""Agent persona models used by the multi-agent console."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AgentPersona:
    """Simple representation of an agent persona."""

    identifier: str
    name: str
    description: str
    vault_key: str
    specialties: List[str] = field(default_factory=list)

    def to_sidebar_label(self) -> str:
        """Return a friendly label for sidebar dropdowns."""

        if self.specialties:
            return f"{self.name} — {', '.join(self.specialties)}"
        return self.name


DEFAULT_PERSONAS: Dict[str, AgentPersona] = {
    "physics": AgentPersona(
        identifier="gpt_researcher",
        name="Physics Researcher",
        description=(
            "Explores experimental physics ideas and surfaces evidence from the physics vault."
        ),
        vault_key="physics",
        specialties=["fusion", "plasma", "reactors"],
    ),
    "theology": AgentPersona(
        identifier="claude_ethicist",
        name="Theology Ethicist",
        description=(
            "Connects spiritual frameworks with actionable guidance, citing theology vault notes."
        ),
        vault_key="theology",
        specialties=["ethics", "liberation", "interfaith"],
    ),
    "integration": AgentPersona(
        identifier="gemini_integrator",
        name="Integration Strategist",
        description=(
            "Synthesises scientific insight with coalition strategy from the integration vault."
        ),
        vault_key="integration",
        specialties=["roadmaps", "alignment", "coalitions"],
    ),
}


def list_personas() -> List[AgentPersona]:
    """Return the ordered list of default personas."""

    return [DEFAULT_PERSONAS[key] for key in ("physics", "theology", "integration")]


def persona_by_id(identifier: str) -> AgentPersona | None:
    """Look up a persona by identifier."""

    for persona in list_personas():
        if persona.identifier == identifier:
            return persona
    return None
