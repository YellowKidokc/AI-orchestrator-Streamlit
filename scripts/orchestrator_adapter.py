"""Deterministic orchestration adapter used by the Streamlit console."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class AgentTurn:
    """Structured representation of a single turn in the transcript."""

    agent_id: str
    display_name: str
    phase: str
    content: str
    tokens: int
    cost_estimate: float


def _estimate_cost(tokens: int, cost_per_1k_tokens: float) -> float:
    """Compute a naive cost estimate based on the configured rate."""

    if cost_per_1k_tokens <= 0:
        return 0.0
    return round((tokens / 1000.0) * cost_per_1k_tokens, 6)


def dry_run_compose(
    agent_config: Dict[str, object],
    session_settings: Dict[str, object],
    round_index: int,
    turn_index: int,
    phase: str,
) -> AgentTurn:
    """Return a deterministic turn for display when running without live providers."""

    display_name = str(agent_config.get("display_name", agent_config.get("id", "agent")))
    agent_id = str(agent_config.get("id", display_name.lower().replace(" ", "_")))
    role = agent_config.get("role", "participant")
    goal = session_settings.get("goal", "Explore the problem space")
    may_skip = session_settings.get("may_skip", True)

    phase_templates = {
        "kickoff": (
            f"{display_name} opens round {round_index + 1} by restating the session goal: {goal}."
        ),
        "task": (
            f"{display_name} contributes actionable insights for round {round_index + 1}, "
            f"focusing on concrete next steps that advance the goal."
        ),
        "self-eval": (
            f"{display_name} reflects on their previous contribution, checking alignment with the goal "
            f"and flagging any assumptions that need validation."
        ),
        "review": (
            f"{display_name} summarises the round outcomes and highlights unresolved questions for the "
            f"team before proceeding."
        ),
        "user_input": (
            "Human facilitator provides direct guidance to the agent cohort, ensuring clarity and momentum."
        ),
    }

    content = phase_templates.get(
        phase,
        f"{display_name} shares an update for phase '{phase}' in round {round_index + 1}.",
    )
    content += f" (turn {turn_index + 1})"

    if may_skip and phase == "task" and role == "participant":
        content += " The agent confirms there is novel value in speaking during this round."

    cost_per_1k = float(agent_config.get("cost_per_1k_tokens", 0.0) or 0.0)
    tokens = len(content.split())
    cost = _estimate_cost(tokens, cost_per_1k)

    return AgentTurn(
        agent_id=agent_id,
        display_name=display_name,
        phase=phase,
        content=content,
        tokens=tokens,
        cost_estimate=cost,
    )


def call_provider(
    agent_config: Dict[str, object],
    session_settings: Dict[str, object],
    round_index: int,
    turn_index: int,
    phase: str,
    *,
    api_key: str | None = None,
) -> AgentTurn:
    """Dispatch to a live provider when credentials are present, else dry-run."""

    if not api_key:
        return dry_run_compose(agent_config, session_settings, round_index, turn_index, phase)

    raise NotImplementedError(
        "Live provider integration is not implemented. Supply an api_key to replace this stub."
    )
