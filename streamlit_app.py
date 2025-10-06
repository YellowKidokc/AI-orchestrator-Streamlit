"""Streamlit entrypoint for the Logos Multi-Agent Console."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import streamlit as st
import yaml

from scripts.orchestrator_adapter import AgentTurn, dry_run_compose

CONFIG_PATH = Path("config/agents.yaml")
UPLOADS_DIR = Path("uploads")
TRANSCRIPT_LOG_PATH = Path("data/session_transcript.jsonl")
CONVERSATIONS_DIR = Path("data/conversations")
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
    """Return the list of configured agents from the YAML file.

    Any credential references are resolved from Streamlit secrets or
    environment variables so that API keys are not hard-coded in the
    repository.
    """

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

    resolved: List[Dict[str, object]] = []
    for agent in agents:
        resolved.append({**agent, **_resolve_agent_credentials(agent)})

    return resolved


def _resolve_agent_credentials(agent: Dict[str, object]) -> Dict[str, object]:
    """Return credential metadata for an agent without exposing secrets."""

    # Agents can specify either a Streamlit secret key (preferred) or an
    # environment variable name from which to pull credentials.
    secret_key = str(agent.get("secret_key", "")) or None
    env_key = str(agent.get("env_key", "")) or None

    credential = None
    if secret_key:
        if secret_key in st.secrets:
            credential = st.secrets[secret_key]
        else:
            st.warning(
                f"Secret '{secret_key}' for agent {agent.get('id', 'unknown')} is not defined in st.secrets."
            )
    if credential is None and env_key:
        credential = os.getenv(env_key)
        if credential is None:
            st.warning(
                f"Environment variable '{env_key}' for agent {agent.get('id', 'unknown')} is not set."
            )

    if credential:
        # We never display the credential value, but we expose a flag so the
        # UI can confirm whether credentials are configured.
        return {"has_credentials": True}

    return {"has_credentials": False}


def ensure_runtime_directories() -> None:
    """Ensure directories required for uploads and transcript logs exist."""

    for directory in (UPLOADS_DIR, TRANSCRIPT_LOG_PATH.parent, CONVERSATIONS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def append_turn(turn: AgentTurn, target_agent_id: str | None = None) -> None:
    """Persist a turn and update derived transcript state."""

    record = asdict(turn)
    if target_agent_id:
        record["target_agent_id"] = target_agent_id

    st.session_state.transcript.append(record)
    log_record = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        **record,
    }
    with TRANSCRIPT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_record) + "\n")

    if "agent_conversations" not in st.session_state:
        st.session_state.agent_conversations = {}

    st.session_state.agent_conversations.setdefault(turn.agent_id, []).append(record)
    if target_agent_id:
        st.session_state.agent_conversations.setdefault(target_agent_id, []).append(record)
    if turn.agent_id == "user":
        st.session_state.agent_conversations.setdefault("user", []).append(record)


def initialise_state(agents: Iterable[Dict[str, object]]) -> None:
    """Populate Streamlit session state with defaults."""

    if "transcript" not in st.session_state:
        st.session_state.transcript = []
    if "agent_conversations" not in st.session_state:
        st.session_state.agent_conversations = {agent["id"]: [] for agent in agents}
        st.session_state.agent_conversations.setdefault("user", [])
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
    if "active_agent_id" not in st.session_state and agents:
        st.session_state.active_agent_id = agents[0]["id"]


def reset_session(agents: Iterable[Dict[str, object]]) -> None:
    """Clear transcript and reset counters while preserving agent toggles."""

    st.session_state.transcript = []
    st.session_state.agent_conversations = {agent["id"]: [] for agent in agents}
    st.session_state.agent_conversations.setdefault("user", [])
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
        if target := turn.get("target_agent_id"):
            metrics += f" · → {target}"
        st.caption(metrics)
        st.divider()


def handle_manual_message(text: str, target_agent_id: str | None = None) -> None:
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
    append_turn(manual_turn, target_agent_id=target_agent_id)


def rebuild_agent_conversations(transcript: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    """Return a mapping of agent ids to their specific conversation turns."""

    conversations: Dict[str, List[Dict[str, object]]] = {}
    for turn in transcript:
        agent_id = str(turn.get("agent_id", ""))
        conversations.setdefault(agent_id, []).append(turn)
        if target := turn.get("target_agent_id"):
            conversations.setdefault(str(target), []).append(turn)
        if agent_id == "user":
            conversations.setdefault("user", []).append(turn)
    return conversations


def _slugify(value: str) -> str:
    """Return a filesystem-friendly slug for conversation titles."""

    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "session"


def save_conversation(
    transcript: List[Dict[str, object]], title: str, completed_rounds: int = 0
) -> Tuple[Path, Path]:
    """Persist the transcript as both JSON and Markdown for later retrieval."""

    if not transcript:
        raise ValueError("Cannot save an empty transcript.")

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(title)
    base_name = f"{timestamp}_{slug}"

    json_path = CONVERSATIONS_DIR / f"{base_name}.json"
    markdown_path = CONVERSATIONS_DIR / f"{base_name}.md"

    payload = {
        "title": title,
        "saved_at": datetime.utcnow().isoformat(timespec="seconds"),
        "completed_rounds": completed_rounds,
        "transcript": transcript,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    markdown_lines = [f"# {title}", ""]
    for turn in transcript:
        speaker = turn.get("display_name") or turn.get("agent_id", "agent")
        phase = turn.get("phase", "")
        header = f"## {speaker}"
        if phase:
            header += f" · {phase}"
        markdown_lines.append(header)
        markdown_lines.append("")
        markdown_lines.append(turn.get("content", ""))
        markdown_lines.append("")
    markdown_path.write_text("\n".join(markdown_lines).strip() + "\n", encoding="utf-8")

    return json_path, markdown_path


def load_saved_conversation(path: Path) -> Dict[str, object]:
    """Load a saved conversation payload from disk."""

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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

    rebuilt_conversations = rebuild_agent_conversations(st.session_state.transcript)
    for agent in agents:
        rebuilt_conversations.setdefault(agent["id"], [])
    rebuilt_conversations.setdefault("user", rebuilt_conversations.get("user", []))
    st.session_state.agent_conversations = rebuilt_conversations

    if agents and (
        "active_agent_id" not in st.session_state
        or st.session_state.active_agent_id not in {agent["id"] for agent in agents}
    ):
        st.session_state.active_agent_id = agents[0]["id"]

    st.sidebar.title("Session Controls")
    if agents:
        agent_ids = [agent["id"] for agent in agents]
        selected_agent = st.sidebar.selectbox(
            "Active agent persona",
            options=agent_ids,
            index=agent_ids.index(st.session_state.active_agent_id),
            format_func=lambda agent_id: next(
                (agent.get("display_name", agent_id) for agent in agents if agent["id"] == agent_id),
                agent_id,
            ),
        )
        st.session_state.active_agent_id = selected_agent

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
        credentials_status = (
            "Credentials configured" if agent.get("has_credentials") else "Credentials missing"
        )
        description = agent.get("description", "")
        caption = description if not description else f"{description}\n{credentials_status}"
        if not description:
            caption = credentials_status
        st.sidebar.caption(caption)

    if st.sidebar.button("Start new session"):
        reset_session(agents)
        st.experimental_rerun()

    if st.sidebar.button("Run next round"):
        if st.session_state.completed_rounds >= st.session_state.session_settings.max_rounds:
            st.warning("Maximum configured rounds reached. Increase the limit to continue.")
        else:
            run_round(agents, st.session_state.session_settings, st.session_state.completed_rounds)

    st.sidebar.subheader("Conversation threads")
    st.sidebar.text_input(
        "Conversation title",
        value=st.session_state.get("conversation_title", "Coalition Session"),
        key="conversation_title",
    )
    if st.sidebar.button("Save transcript"):
        try:
            json_path, markdown_path = save_conversation(
                st.session_state.transcript,
                st.session_state.conversation_title,
                st.session_state.completed_rounds,
            )
        except ValueError as error:
            st.sidebar.warning(str(error))
        else:
            st.sidebar.success(
                f"Saved to {json_path.name} (JSON) and {markdown_path.name} (Markdown)."
            )

    saved_conversations = sorted(CONVERSATIONS_DIR.glob("*.json"), reverse=True)
    saved_labels = ["Select a saved conversation"] + [path.name for path in saved_conversations]
    selected_saved = st.sidebar.selectbox("Load conversation", saved_labels, key="saved_selector")
    if selected_saved and selected_saved != saved_labels[0]:
        payload = load_saved_conversation(CONVERSATIONS_DIR / selected_saved)
        st.session_state.transcript = payload.get("transcript", [])
        st.session_state.agent_conversations = rebuild_agent_conversations(st.session_state.transcript)
        st.session_state.conversation_title = payload.get("title", st.session_state.conversation_title)
        st.session_state.completed_rounds = payload.get("completed_rounds", 0)
        st.experimental_rerun()

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
            agent_options = [agent["id"] for agent in agents]
            if agent_options:
                target_agent = st.selectbox(
                    "Send to agent",
                    options=agent_options,
                    index=agent_options.index(st.session_state.active_agent_id)
                    if st.session_state.active_agent_id in agent_options
                    else 0,
                    format_func=lambda agent_id: next(
                        (agent.get("display_name", agent_id) for agent in agents if agent["id"] == agent_id),
                        agent_id,
                    ),
                )
            else:
                target_agent = None
            manual_message = st.text_area(
                "Inject manual facilitator message",
                height=120,
                placeholder="Add clarifications or follow-up instructions here...",
            )
            submitted = st.form_submit_button("Add message")
            if submitted:
                handle_manual_message(manual_message, target_agent_id=target_agent if agent_options else None)
                st.experimental_rerun()
        transcript_tabs = st.tabs(["Unified view", "Active persona thread"])
        with transcript_tabs[0]:
            render_transcript(st.session_state.transcript)
        with transcript_tabs[1]:
            active_transcript = st.session_state.agent_conversations.get(
                st.session_state.get("active_agent_id", ""), []
            )
            render_transcript(active_transcript)

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
                credentials_status = (
                    "Credentials configured" if agent.get("has_credentials") else "Credentials missing"
                )
                st.caption(f"{provider} · {model}\n{credentials_status}")

        st.subheader("Transcript log")
        st.caption(str(TRANSCRIPT_LOG_PATH.resolve()))


if __name__ == "__main__":
    main()
