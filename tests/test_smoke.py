"""Basic smoke tests for the Logos Multi-Agent Console scaffolding."""
from importlib import import_module
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

_streamlit = pytest.importorskip("streamlit")

from scripts.orchestrator_adapter import AgentTurn, dry_run_compose


def test_streamlit_app_imports() -> None:
    """The Streamlit app should be importable for smoke testing."""

    module = import_module("streamlit_app")
    assert hasattr(module, "main")


def test_dry_run_compose_produces_turn() -> None:
    """Dry-run compose should generate a deterministic AgentTurn."""

    agent = {
        "id": "tester",
        "display_name": "Test Agent",
        "role": "participant",
        "cost_per_1k_tokens": 1.0,
    }
    settings = {"goal": "Validate smoke test", "may_skip": False, "phase": "task"}
    turn = dry_run_compose(agent, settings, round_index=0, turn_index=0, phase="task")

    assert isinstance(turn, AgentTurn)
    assert turn.agent_id == "tester"
    assert "round 1" in turn.content
    assert turn.tokens > 0
