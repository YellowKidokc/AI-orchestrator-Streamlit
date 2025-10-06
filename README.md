# Logos Multi-Agent Console (Streamlit)

Logos Multi-Agent Console is a Streamlit workspace for orchestrating structured conversations between multiple large language models (LLMs), an administrator agent, and a human facilitator. The prior discussion log has now been translated into a working scaffold so contributors can iterate on the experience directly.

## Vision

The console is designed to let researchers coordinate "rounds" of dialogue among different AI providers (OpenAI GPT, Anthropic Claude, Google Gemini, DeepSeek, etc.) while the administrator guides the session and a human can interject at any time. The UI should be a full-width workspace with side panels for configuration, a central transcript, and utilities for logging, costs, and document uploads.

## Core Features

- **Agent management sidebar**
  - Enable/disable individual agents and configure their model/provider.
  - Select an "active" persona to focus the conversation view and direct facilitator prompts.
  - Set per-agent privileges (compose, read_docs, web, code, etc.).
  - Reference credentials stored in `st.secrets` or environment variables instead of hard-coding keys.
- **Admin controls**
  - Define the number of dialogue rounds and the structure of each round (kickoff → task turns → self-eval → review).
  - Configure intro/outro turns for the administrator agent.
  - Manage global system prompt and dedicated admin prompt.
- **Main conversation pane**
  - Full-height transcript showing each turn with `[phase] agent_id — tokens/cost` labels.
  - Support for deterministic dry-run output so the app works without live API keys.
  - Ability for the human facilitator to inject messages that are clearly flagged as manual contributions.
- **Context and uploads**
  - Drawer or panel to upload PDF/Markdown/Text documents, stored under `uploads/` and appended to session context.
  - Planned citation display that references uploaded documents.
- **Logging and persistence**
  - Persist every turn to `data/session_transcript.jsonl`.
  - Save complete sessions as timestamped JSON + Markdown bundles under `data/conversations/` for later review.
  - Surface per-session metrics (tokens, estimated spend) in a right-hand panel.
- **Adaptable orchestration layer**
  - `scripts/orchestrator_adapter.py` exposes `dry_run_compose(...)` for deterministic behavior and `call_provider(...)` for future integration with production orchestration (e.g., `AI_Team_Framework.Coordinator`).

## Repository Structure

```
AI-orchestrator-Streamlit/
├── streamlit_app.py                # Streamlit UI, layout, and round orchestration
├── scripts/
│   └── orchestrator_adapter.py     # Dry-run turn generator + provider hook stub
├── config/
│   └── agents.yaml                 # Default agent roster and privileges
├── prompts/
│   ├── system_prompt.md            # Global ruleset (“Clarity and Integrity First”)
│   └── admin_prompt.md             # Administrator coordination prompt
├── uploads/
│   └── .gitignore                  # Runtime uploads stored here
├── data/
│   └── .gitignore                  # JSONL transcripts are appended here at runtime
├── tests/
│   └── test_smoke.py               # Basic smoke tests
├── requirements.txt
├── .env.example
└── README.md
```

The Streamlit app can run entirely in deterministic dry-run mode, making it safe to explore without API keys.

## Credentials

For production use, never hard-code provider API keys in the repository. Instead, supply credentials via Streamlit secrets or environment variables and reference them from `config/agents.yaml`:

```yaml
agents:
  - id: gpt_researcher
    provider: openai
    model: gpt-4o-mini
    secret_key: OPENAI_API_KEY  # looks for st.secrets["OPENAI_API_KEY"]
    env_key: OPENAI_API_KEY     # fallback to os.environ["OPENAI_API_KEY"]
```

Only the boolean `has_credentials` flag is surfaced in the UI so that sensitive values never appear in logs or the interface. If neither source is defined the app stays in deterministic dry-run mode.

## Conversation archives

Each session can be saved from the sidebar. The console writes a timestamped JSON payload (for re-loading later) and a human-readable Markdown transcript to `data/conversations/`. Saved threads can be reloaded into the app at any time, allowing facilitators to maintain separate workstreams per agent persona or project.

## Implementation Roadmap

1. **Enhanced session logic**
   - Allow facilitators to customise round structures and selectively assign agents per phase.
   - Capture richer metadata for each turn (citations, tool outputs, attachments).
2. **Provider integrations**
   - Implement `call_provider` in `scripts/orchestrator_adapter.py` and gate behaviour behind environment variables.
   - Surface provider-level health checks and rate-limit feedback in the metrics panel.
3. **Context intelligence**
   - Extract snippets from uploaded documents and encourage agents to cite them automatically.
   - Implement semantic deduplication for the “may skip if redundant” flow.
4. **Persistence and export**
   - Add download buttons for JSONL/Markdown exports of the transcript and prompts/configuration bundles.
5. **Testing and CI**
   - Expand beyond smoke tests with unit coverage for round orchestration and upload handling.
   - Set up continuous integration (GitHub Actions) that runs `pytest` and linting on every PR.

## Usage

1. Clone the repository and create a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy environment variables:
   ```bash
   cp .env.example .env
   ```
   Add provider API keys as needed. Without keys the app will stay in dry-run mode.
4. Launch Streamlit:
   ```bash
   streamlit run streamlit_app.py
   ```
5. Configure agents in the sidebar, optionally upload documents, and start the orchestrated session.

While running locally, uploaded files are written to `uploads/` and the transcript log is appended to `data/session_transcript.jsonl`.

## Contributing

1. Discuss planned changes via issue or discussion thread to keep alignment with the product vision above.
2. When adding new modules, update this README and the Streamlit UI so the roadmap stays accurate.
3. Include automated tests for new behaviour; `pytest` currently runs the smoke suite under `tests/`.

## License

The project license has not been specified. Add a license file before distribution.

## Status

Active prototyping stage — a functional dry-run console is available for exploration while provider integrations remain stubbed.
