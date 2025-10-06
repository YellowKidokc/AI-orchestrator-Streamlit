# Coalition Multi-Agent Workspace

A Streamlit application for coordinating conversations between specialised AI personas and
curating shared Obsidian-style knowledge vaults. The workspace stitches together domain-
specific notes, deterministic agent replies, and session persistence so facilitators can run
multi-perspective planning sprints without exposing API keys.

## Features

- **Secure credential handling** – Load environment variables from `.env` via `python-dotenv`
and optionally capture the OpenAI API key inside the Streamlit session (never written to disk).
- **Multi-agent personas** – Three pre-configured personas (Physics Researcher, Theology
  Ethicist, Integration Strategist) each grounded in a dedicated vault. Switch personas or
  broadcast prompts to the full cohort.
- **Vault-aware responses** – Deterministic responses pull snippets from Markdown notes stored
  under `vaults/`, highlighting relevant evidence for the conversation.
- **Note browsing and editing** – Inspect and update vault Markdown files directly inside the UI
  to keep the knowledge base fresh.
- **Conversation history** – Save transcripts to timestamped JSON files under `history/`
  (tagged with the active vault) and reload them at any time to continue workstreams.
- **Cross-vault search** – Run quick searches across all vaults to surface contextual snippets
  even if you are focused on a single persona.

## Project layout

```
AI-orchestrator-Streamlit/
├── app/
│   └── main.py                # Streamlit UI and application logic
├── agents/
│   ├── __init__.py
│   ├── persona.py             # Persona models and registry
│   └── responder.py           # Deterministic response helpers
├── vaults/                    # Obsidian-style Markdown vaults (sample content included)
├── history/                   # Saved conversation transcripts
├── streamlit_app.py           # Thin wrapper that imports `app.main`
├── requirements.txt
├── README.md
└── tests/
    └── test_smoke.py
```

## Getting started

1. Create and activate a virtual environment (Python 3.10+).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Copy `.env.example` to `.env` and populate with API keys or other secrets. The
   app loads environment variables automatically via `python-dotenv` when it starts. You can
   also paste an API key into the sidebar; it remains in memory for the active session only.
4. Adjust vault configuration if needed by editing `config/vaults.yaml`. Paths may be
   absolute or relative to the project root and are created on demand.
5. Launch Streamlit:
   ```bash
   streamlit run app/main.py
   ```
6. Use the sidebar to pick an active persona, choose which vault to browse, toggle between
   single- or multi-agent replies, run cross-vault searches, and manage saved conversations.

## Conversation persistence

Saved conversations are written to `history/<timestamp>_<slug>.json`. These include the
conversation title, routing mode, and all chat messages. Reloading a history file restores the
transcript and agent settings so facilitators can jump back into ongoing efforts.

## Testing

A lightweight smoke test ensures the Streamlit module imports successfully:

```bash
pytest
```

## License

A license has not been provided. Add one before distributing the application.
