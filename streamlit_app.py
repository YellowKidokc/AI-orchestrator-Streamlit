"""Streamlit entrypoint for the Logos Multi-Agent Console."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

import streamlit as st
import yaml

from scripts.orchestrator_adapter import AgentTurn, dry_run_compose

CONFIG_PATH = Path("config/agents.yaml")
UPLOADS_DIR = Path("uploads")
TRANSCRIPT_LOG_PATH = Path("data/session_transcript.jsonl")
DEFAULT_ROUND_STRUCTURE = (
    ("kickoff", "admin"),
    ("task", "all"),
    ("self-eval", "all"),
    ("review", "admin"),
)


@dataclass
class SessionSettings:
    """Settings that influence dry-run responses."""

    goal: str
    max_rounds: int
    may_skip_redundant: bool


def load_agent_configs() -> List[Dict[str, object]]:
    """Return the list of configured agents from the YAML file."""

    if not CONFIG_PATH.exists():
        st.error(
            "Missing config/agents.yaml. Create the file using config/agents.example.yaml as a template."
        )
        return []

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    agents = payload.get("agents", [])
    if not isinstance(agents, list):
        st.error("Invalid agents configuration; expected a list of agents under 'agents'.")
        return []

    return agents


def ensure_runtime_directories() -> None:
    """Ensure directories required for uploads and transcript logs exist."""

    for directory in (UPLOADS_DIR, TRANSCRIPT_LOG_PATH.parent):
        directory.mkdir(parents=True, exist_ok=True)


def append_turn(turn: AgentTurn) -> None:
    """Persist a turn to session state and append it to the JSONL transcript log."""

    st.session_state.transcript.append(asdict(turn))
    log_record = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        **asdict(turn),
    }
    with TRANSCRIPT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_record) + "\n")


def initialise_state(agents: Iterable[Dict[str, object]]) -> None:
    """Populate Streamlit session state with defaults."""

    if "transcript" not in st.session_state:
        st.session_state.transcript = []
    if "completed_rounds" not in st.session_state:
        st.session_state.completed_rounds = 0
    if "agent_enabled" not in st.session_state:
        st.session_state.agent_enabled = {
            agent["id"]: bool(agent.get("enabled_by_default", True)) for agent in agents
        }
    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = {}
    if "session_settings" not in st.session_state:
        st.session_state.session_settings = SessionSettings(
            goal="Explore the problem space",
            max_rounds=3,
            may_skip_redundant=True,
        )


def reset_session(agents: Iterable[Dict[str, object]]) -> None:
    """Clear transcript and reset counters while preserving agent toggles."""

    st.session_state.transcript = []
    st.session_state.completed_rounds = 0
    st.session_state.session_settings = SessionSettings(
        goal="Explore the problem space",
        max_rounds=3,
        may_skip_redundant=True,
    )
    st.session_state.agent_enabled = {
        agent["id"]: bool(agent.get("enabled_by_default", True)) for agent in agents
    }


def compute_metrics(transcript: List[Dict[str, object]]) -> Dict[str, float]:
    """Aggregate lightweight metrics for the session."""

    total_tokens = sum(turn.get("tokens", 0) for turn in transcript)
    total_cost = sum(turn.get("cost_estimate", 0.0) for turn in transcript)
    return {
        "total_turns": len(transcript),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
    }


def run_round(
    agents: List[Dict[str, object]],
    session_settings: SessionSettings,
    round_index: int,
) -> None:
    """Generate deterministic dry-run turns for the configured round."""

    enabled_agents = [agent for agent in agents if st.session_state.agent_enabled.get(agent["id"], False)]
    if not enabled_agents:
        st.warning("Enable at least one agent to run a round.")
        return

    for phase, audience in DEFAULT_ROUND_STRUCTURE:
        for agent in enabled_agents:
            role = agent.get("role", "participant")
            if audience == "admin" and role != "admin":
                continue
            if audience == "non-admin" and role == "admin":
                continue

            turn = dry_run_compose(
                agent_config=agent,
                session_settings={
                    "goal": session_settings.goal,
                    "round_index": round_index,
                    "phase": phase,
                    "may_skip": session_settings.may_skip_redundant,
                },
                round_index=round_index,
                turn_index=len(st.session_state.transcript),
                phase=phase,
            )
            append_turn(turn)

    st.session_state.completed_rounds += 1


def render_transcript(transcript: List[Dict[str, object]]) -> None:
    """Render transcript turns with phase badges."""

    if not transcript:
        st.info("No turns generated yet. Use the controls to run a round or add a manual message.")
        return

    for turn in transcript:
        phase = turn.get("phase", "")
        badge = f"`[{phase}]` " if phase else ""
        header = f"{badge}**{turn['agent_id']}**"
        st.markdown(header)
        st.write(turn.get("content", ""))
        metrics = f"Tokens: {turn.get('tokens', 0)} · Cost: ${turn.get('cost_estimate', 0.0):.4f}"
        st.caption(metrics)
        st.divider()


def handle_manual_message(text: str) -> None:
    """Append a manual facilitator message to the transcript."""

    content = text.strip()
    if not content:
        return

    manual_turn = AgentTurn(
        agent_id="user",
        display_name="Human Facilitator",
        phase="user_input",
        content=content,
        tokens=len(content.split()),
        cost_estimate=0.0,
    )
    append_turn(manual_turn)


def handle_uploads(uploaded_files: List["UploadedFile"]) -> None:
    """Persist uploaded documents to the uploads directory."""

    if not uploaded_files:
        return

    new_files = False
    for uploaded in uploaded_files:
        if not uploaded.name:
            continue
        if uploaded.name in st.session_state.uploaded_files:
            # Prevent repeated writes when Streamlit reruns the script.
            continue
        destination = UPLOADS_DIR / uploaded.name
        destination.write_bytes(uploaded.getbuffer())
        st.session_state.uploaded_files[uploaded.name] = str(destination)
        new_files = True

    if new_files:
        st.success("Uploaded documents added to session context.")


def main() -> None:
    """Entrypoint for the Streamlit application."""

    st.set_page_config(page_title="Logos Multi-Agent Console", layout="wide")
    ensure_runtime_directories()

    agents = load_agent_configs()
    initialise_state(agents)

    st.sidebar.title("Session Controls")
    st.sidebar.text_input(
        "Session goal",
        value=st.session_state.session_settings.goal,
        key="session_goal",
        help="Guidance that agents receive in the dry-run transcript.",
    )
    st.session_state.session_settings.goal = st.session_state.session_goal

    st.sidebar.number_input(
        "Target rounds",
        min_value=1,
        max_value=20,
        value=st.session_state.session_settings.max_rounds,
        key="target_rounds",
    )
    st.session_state.session_settings.max_rounds = int(st.session_state.target_rounds)

    st.sidebar.checkbox(
        "Allow agents to skip redundant turns",
        value=st.session_state.session_settings.may_skip_redundant,
        key="skip_redundant",
    )
    st.session_state.session_settings.may_skip_redundant = st.session_state.skip_redundant

    st.sidebar.subheader("Agent roster")
    for agent in agents:
        enabled = st.sidebar.checkbox(
            f"{agent.get('display_name', agent['id'])}",
            value=st.session_state.agent_enabled.get(agent["id"], True),
            key=f"enable_{agent['id']}",
        )
        st.session_state.agent_enabled[agent["id"]] = enabled
        st.sidebar.caption(agent.get("description", ""))

    if st.sidebar.button("Start new session"):
        reset_session(agents)
        st.experimental_rerun()

    if st.sidebar.button("Run next round"):
        if st.session_state.completed_rounds >= st.session_state.session_settings.max_rounds:
            st.warning("Maximum configured rounds reached. Increase the limit to continue.")
        else:
            run_round(agents, st.session_state.session_settings, st.session_state.completed_rounds)

    col_context, col_transcript, col_metrics = st.columns([1.2, 2.4, 1.0])

    with col_context:
        st.header("Context & Uploads")
        uploaded = st.file_uploader(
            "Upload reference documents",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
            help="Uploaded files are stored under uploads/ and referenced in the session context.",
        )
        handle_uploads(uploaded)
        if st.session_state.uploaded_files:
            st.subheader("Attached")
            for name, path in st.session_state.uploaded_files.items():
                st.write(f"• {name}")
                st.caption(path)
        else:
            st.caption("No documents attached yet.")

    with col_transcript:
        st.header("Transcript")
        with st.form("user_injection"):
            manual_message = st.text_area(
                "Inject manual facilitator message",
                height=120,
                placeholder="Add clarifications or follow-up instructions here...",
            )
            submitted = st.form_submit_button("Add message")
            if submitted:
                handle_manual_message(manual_message)
                st.experimental_rerun()
        render_transcript(st.session_state.transcript)

    with col_metrics:
        st.header("Session Metrics")
        metrics = compute_metrics(st.session_state.transcript)
        st.metric("Completed rounds", st.session_state.completed_rounds)
        st.metric("Total turns", metrics["total_turns"])
        st.metric("Total tokens", metrics["total_tokens"])
        st.metric("Est. cost (USD)", f"${metrics['total_cost']:.4f}")

        st.subheader("Active agents")
        active = [agent for agent in agents if st.session_state.agent_enabled.get(agent["id"], False)]
        if not active:
            st.caption("No agents enabled.")
        else:
            for agent in active:
                provider = agent.get("provider", "n/a")
                model = agent.get("model", "dry-run")
                st.write(f"**{agent.get('display_name', agent['id'])}**")
                st.caption(f"{provider} · {model}")

        st.subheader("Transcript log")
        st.caption(str(TRANSCRIPT_LOG_PATH.resolve()))


if __name__ == "__main__":
    main()
