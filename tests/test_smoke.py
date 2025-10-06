"""Smoke tests for the coalition multi-agent workspace."""
from importlib import import_module
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

_streamlit = pytest.importorskip("streamlit")


def test_streamlit_wrapper_exposes_main() -> None:
    """The compatibility wrapper should re-export the main entrypoint."""

    module = import_module("streamlit_app")
    assert hasattr(module, "main")


def test_persona_registry_round_trip() -> None:
    """Personas should be discoverable and have vaults configured."""

    persona_module = import_module("agents.persona")
    app_module = import_module("app.main")
    personas = persona_module.list_personas()
    assert len(personas) == 3
    for persona in personas:
        vault_entry = app_module.VAULT_REGISTRY.get(persona.vault_key)
        assert vault_entry is not None
        vault_path = Path(vault_entry["path"])
        assert vault_path.exists()
        assert vault_path.is_dir()


def test_responder_returns_text() -> None:
    """Responder should generate deterministic content for a persona."""

    persona_module = import_module("agents.persona")
    responder_module = import_module("agents.responder")
    persona = persona_module.list_personas()[0]
    documents = {
        "example.md": "Fusion energy remains a grand challenge with tokamak experiments."
    }
    output = responder_module.build_response(persona, "fusion", documents, [])
    assert "Persona" in output
    assert "fusion" in output.lower()


def test_vault_registry_reads_yaml() -> None:
    """Vault registry should prefer YAML overrides when present."""

    app_module = import_module("app.main")
    registry = app_module.load_vault_registry()
    assert set(registry.keys()) >= {"physics", "theology", "integration"}
    for entry in registry.values():
        path = Path(entry["path"])
        assert path.exists()
        assert path.is_dir()
