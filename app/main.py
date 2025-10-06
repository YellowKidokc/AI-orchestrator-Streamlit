"""Streamlit app entrypoint for the multi-agent Obsidian console."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

try:  # pragma: no cover - optional dependency during tests
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_, **__):
        return False

from agents.persona import AgentPersona, list_personas
from agents.responder import build_response

HISTORY_DIR = Path("history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

VAULT_ROOT = Path("vaults")
VAULT_CONFIG = {
    "physics": VAULT_ROOT / "physics",
    "theology": VAULT_ROOT / "theology",
    "integration": VAULT_ROOT / "integration",
}


@st.cache_data(show_spinner=False)
def load_vault_documents(vault_key: str) -> Dict[str, str]:
    """Return the Markdown documents for the requested vault."""

    vault_path = VAULT_CONFIG.get(vault_key)
    if not vault_path or not vault_path.exists():
        return {}

    documents: Dict[str, str] = {}
    for path in vault_path.glob("*.md"):
        documents[path.name] = path.read_text(encoding="utf-8")
    return documents


def ensure_state(personas: List[AgentPersona]) -> None:
    """Initialise session state on first load."""

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_histories" not in st.session_state:
        st.session_state.agent_histories = {persona.identifier: [] for persona in personas}
    if "active_agent" not in st.session_state and personas:
        st.session_state.active_agent = personas[0].identifier
    if "conversation_title" not in st.session_state:
        st.session_state.conversation_title = "Coalition Session"
    if "response_mode" not in st.session_state:
        st.session_state.response_mode = "Active agent"
    if "cross_vault_results" not in st.session_state:
        st.session_state.cross_vault_results = []
    if "openai_api_key" not in st.session_state:
        st.session_state.openai_api_key = ""


def append_message(
    role: str, agent_id: str, content: str, target_personas: List[str] | None = None
) -> None:
    """Persist a chat message and update per-agent histories."""

    record = {"role": role, "agent_id": agent_id, "content": content}
    if role == "user" and target_personas:
        record["target_personas"] = target_personas
    st.session_state.messages.append(record)
    if role == "assistant":
        st.session_state.agent_histories.setdefault(agent_id, []).append(record)
    elif role == "user" and target_personas:
        for persona_id in target_personas:
            history = st.session_state.agent_histories.setdefault(persona_id, [])
            history.append({"role": "user", "agent_id": agent_id, "content": content})


def save_conversation() -> Path:
    """Write the current conversation to disk."""

    if not st.session_state.messages:
        raise ValueError("Nothing to save yet — start a conversation first.")

    slug = st.session_state.conversation_title.strip().lower().replace(" ", "-") or "session"
    from datetime import datetime

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    st.session_state._last_saved_timestamp = timestamp
    filename = f"{timestamp}_{slug}.json"
    destination = HISTORY_DIR / filename
    payload = {
        "title": st.session_state.conversation_title,
        "messages": st.session_state.messages,
        "active_agent": st.session_state.active_agent,
        "response_mode": st.session_state.response_mode,
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def load_conversation(path: Path, personas: List[AgentPersona]) -> None:
    """Load a saved conversation into session state."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    st.session_state.messages = payload.get("messages", [])
    st.session_state.conversation_title = payload.get("title", "Coalition Session")
    active = payload.get("active_agent")
    if active:
        st.session_state.active_agent = active
    mode = payload.get("response_mode")
    if mode:
        st.session_state.response_mode = mode

    st.session_state.agent_histories = {persona.identifier: [] for persona in personas}
    for record in st.session_state.messages:
        if record.get("role") == "assistant":
            agent_id = record.get("agent_id", "")
            st.session_state.agent_histories.setdefault(agent_id, []).append(record)
        elif record.get("role") == "user":
            targets = record.get("target_personas", [])
            for persona_id in targets:
                history = st.session_state.agent_histories.setdefault(persona_id, [])
                history.append(record)


def render_sidebar(personas: List[AgentPersona]) -> None:
    """Sidebar layout for agent controls and persistence."""

    st.sidebar.title("Coalition Controls")
    api_key_input = st.sidebar.text_input(
        "OpenAI API Key", value=st.session_state.openai_api_key, type="password"
    )
    st.session_state.openai_api_key = api_key_input
    if api_key_input:
        st.sidebar.caption("Key stored in memory for this session.")
    else:
        st.sidebar.caption("Running in dry-run mode without an API key.")

    options = [persona.identifier for persona in personas]
    if options:
        if st.session_state.active_agent not in options:
            st.session_state.active_agent = options[0]
        index = options.index(st.session_state.active_agent)
        selected = st.sidebar.selectbox(
            "Active persona",
            options=options,
            index=index,
            format_func=lambda identifier: next(
                (
                    persona.to_sidebar_label()
                    for persona in personas
                    if persona.identifier == identifier
                ),
                identifier,
            ),
        )
        st.session_state.active_agent = selected

    mode = st.sidebar.radio("Response mode", ["Active agent", "Consult all"], index=0)
    st.session_state.response_mode = mode

    st.sidebar.text_input(
        "Conversation title", value=st.session_state.conversation_title, key="conversation_title"
    )

    if st.sidebar.button("Save conversation"):
        try:
            saved_path = save_conversation()
        except ValueError as error:
            st.sidebar.warning(str(error))
        else:
            st.sidebar.success(f"Saved transcript to {saved_path.relative_to(HISTORY_DIR.parent)}")

    saved_files = sorted(HISTORY_DIR.glob("*.json"))
    labels = ["Load saved conversation"] + [path.name for path in saved_files]
    selected_label = st.sidebar.selectbox("History", labels, index=0)
    if selected_label != labels[0]:
        load_conversation(HISTORY_DIR / selected_label, personas)
        st.sidebar.success(f"Loaded {selected_label}")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Cross-vault search")
    query = st.sidebar.text_input("Query vaults", key="cross_vault_query")
    search_clicked = st.sidebar.button("Search all vaults")
    clear_clicked = st.sidebar.button("Clear search results")
    if search_clicked and query.strip():
        results = []
        for persona in personas:
            documents = load_vault_documents(persona.vault_key)
            matches = [
                (persona.name, note, snippet)
                for note, snippet in build_cross_vault_results(query, documents)
            ]
            results.extend(matches)
        st.session_state.cross_vault_results = results
    if clear_clicked:
        st.session_state.cross_vault_results = []


def build_cross_vault_results(query: str, documents: Dict[str, str]) -> List[tuple[str, str]]:
    """Helper that reuses the responder search routine for cross-vault UI."""

    from agents.responder import search_vault_notes

    return search_vault_notes(query, documents)


def render_cross_vault_results() -> None:
    """Display cached cross-vault search results."""

    if not st.session_state.cross_vault_results:
        return

    st.subheader("Cross-vault insights")
    for persona_name, note, snippet in st.session_state.cross_vault_results:
        st.markdown(f"**{persona_name}** — `{note}`")
        st.caption(snippet.strip())


def render_vault_editor(persona: AgentPersona) -> None:
    """Show editable notes for the active persona's vault."""

    documents = load_vault_documents(persona.vault_key)
    st.subheader("Vault notes")
    if not documents:
        st.info("No Markdown documents found for this vault yet.")
        return

    names = sorted(documents.keys())
    default_index = 0
    selected_name = st.selectbox("Select note", names, index=default_index)
    content_key = f"note_{persona.vault_key}_{selected_name}"
    st.session_state.setdefault(content_key, documents[selected_name])
    updated_content = st.text_area(
        "Edit note", value=st.session_state[content_key], height=240, key=content_key
    )
    if st.button("Save note", key=f"save_{persona.vault_key}_{selected_name}"):
        note_path = VAULT_CONFIG[persona.vault_key] / selected_name
        note_path.write_text(updated_content, encoding="utf-8")
        st.success(f"Saved {selected_name} to {persona.vault_key} vault.")
        load_vault_documents.clear()


def render_messages(personas: List[AgentPersona]) -> None:
    """Display the chat transcript."""

    for message in st.session_state.messages:
        role = message["role"]
        agent_id = message.get("agent_id", "user")
        name = "Facilitator" if role == "user" else agent_id
        for persona in personas:
            if persona.identifier == agent_id:
                name = persona.name
                break
        with st.chat_message("assistant" if role == "assistant" else "user", avatar=name[:2]):
            st.markdown(message["content"])


def handle_user_message(personas: List[AgentPersona], user_message: str) -> None:
    """Route a user message to one or more personas."""

    if st.session_state.response_mode == "Consult all":
        targets = [persona.identifier for persona in personas]
        append_message("user", "user", user_message, target_personas=targets)
        for persona in personas:
            respond_with_persona(persona, user_message)
    else:
        persona = next(
            persona for persona in personas if persona.identifier == st.session_state.active_agent
        )
        append_message("user", "user", user_message, target_personas=[persona.identifier])
        respond_with_persona(persona, user_message)


def respond_with_persona(persona: AgentPersona, user_message: str) -> None:
    """Generate and store a response for a persona."""

    notes = load_vault_documents(persona.vault_key)
    history = st.session_state.agent_histories.get(persona.identifier, [])
    response = build_response(persona, user_message, notes, history)
    append_message("assistant", persona.identifier, response)


def main() -> None:
    """Streamlit entrypoint."""

    load_dotenv()
    personas = list_personas()
    ensure_state(personas)

    st.set_page_config(page_title="Coalition Multi-Agent Console", layout="wide")
    render_sidebar(personas)

    st.title("Coalition Multi-Agent Workspace")
    st.caption(
        "Coordinate specialised AI personas tied to discrete Obsidian vaults."
    )

    columns = st.columns([2, 1])
    with columns[0]:
        render_messages(personas)
        user_message = st.chat_input("Ask the coalition or share an update")
        if user_message:
            handle_user_message(personas, user_message)
            st.experimental_rerun()
    with columns[1]:
        active = next(
            persona for persona in personas if persona.identifier == st.session_state.active_agent
        )
        render_vault_editor(active)
        render_cross_vault_results()


__all__ = ["main"]
