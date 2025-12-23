"""
Vault integration steps.

Steps for:
- Searching vault notes
- Reading vault content
- Cross-vault queries
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
import yaml

from core.step import Step, StepResult
from core.context import ExecutionContext
from core.step_factory import register_step


def load_vault_registry() -> Dict[str, Dict]:
    """Load vault registry from config."""
    vault_config_path = Path("config/vaults.yaml")
    if vault_config_path.exists():
        with open(vault_config_path) as f:
            return yaml.safe_load(f).get("vaults", {})
    return {}


@register_step("vault_search")
class VaultSearchStep(Step):
    """
    Search across vault notes.

    Supports:
    - Keyword search
    - Multi-vault queries
    - Snippet extraction
    """

    name = "vault_search"
    description = "Search vault notes for keywords or patterns"

    config_schema = {
        "query": {"type": "string", "required": True, "description": "Search query"},
        "vaults": {"type": "array", "description": "Vault names to search (empty = all)"},
        "output_key": {"type": "string", "default": "search_results"},
        "max_results": {"type": "number", "default": 10},
        "snippet_length": {"type": "number", "default": 200},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        query = context.interpolate(self.config["query"])
        vault_names = self.config.get("vaults", [])
        output_key = self.config.get("output_key", "search_results")
        max_results = self.config.get("max_results", 10)
        snippet_length = self.config.get("snippet_length", 200)

        vaults = load_vault_registry()

        # Determine which vaults to search
        if not vault_names:
            vault_names = list(vaults.keys())

        results = []
        query_lower = query.lower()

        for vault_name in vault_names:
            if vault_name not in vaults:
                continue

            vault_path = Path(vaults[vault_name]["path"])
            if not vault_path.exists():
                continue

            for note_path in vault_path.glob("**/*.md"):
                try:
                    content = note_path.read_text(encoding="utf-8")
                    if query_lower in content.lower():
                        # Extract snippet
                        idx = content.lower().find(query_lower)
                        start = max(0, idx - snippet_length // 2)
                        end = min(len(content), idx + len(query) + snippet_length // 2)
                        snippet = content[start:end]
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(content):
                            snippet = snippet + "..."

                        results.append({
                            "vault": vault_name,
                            "note": note_path.stem,
                            "path": str(note_path),
                            "snippet": snippet.strip(),
                        })

                        if len(results) >= max_results:
                            break
                except Exception:
                    continue

            if len(results) >= max_results:
                break

        context.set(output_key, results)
        context.set(f"{output_key}_count", len(results))
        return context


@register_step("vault_read")
class VaultReadStep(Step):
    """
    Read content from vault notes.

    Supports:
    - Single note reading
    - Multiple notes
    - Content parsing
    """

    name = "vault_read"
    description = "Read content from vault notes"

    config_schema = {
        "vault": {"type": "string", "required": True, "description": "Vault name"},
        "notes": {"type": "array", "description": "Note names to read (empty = all)"},
        "output_key": {"type": "string", "default": "vault_content"},
        "include_frontmatter": {"type": "boolean", "default": False},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        vault_name = context.interpolate(self.config["vault"])
        note_names = self.config.get("notes", [])
        output_key = self.config.get("output_key", "vault_content")
        include_frontmatter = self.config.get("include_frontmatter", False)

        vaults = load_vault_registry()

        if vault_name not in vaults:
            raise ValueError(f"Unknown vault: {vault_name}")

        vault_path = Path(vaults[vault_name]["path"])
        if not vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        result = {}

        # Get notes to read
        if note_names:
            note_paths = [vault_path / f"{name}.md" for name in note_names]
        else:
            note_paths = list(vault_path.glob("**/*.md"))

        for note_path in note_paths:
            if not note_path.exists():
                continue

            try:
                content = note_path.read_text(encoding="utf-8")

                # Parse frontmatter
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = yaml.safe_load(parts[1]) if include_frontmatter else None
                        body = parts[2].strip()
                    else:
                        frontmatter = None
                        body = content
                else:
                    frontmatter = None
                    body = content

                result[note_path.stem] = {
                    "content": body,
                    "path": str(note_path),
                }
                if frontmatter:
                    result[note_path.stem]["frontmatter"] = frontmatter

            except Exception:
                continue

        context.set(output_key, result)
        return context


@register_step("vault_list")
class VaultListStep(Step):
    """
    List available vaults and their notes.
    """

    name = "vault_list"
    description = "List available vaults and their contents"

    config_schema = {
        "output_key": {"type": "string", "default": "vaults"},
        "include_notes": {"type": "boolean", "default": True},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        output_key = self.config.get("output_key", "vaults")
        include_notes = self.config.get("include_notes", True)

        vaults = load_vault_registry()
        result = {}

        for vault_name, vault_info in vaults.items():
            vault_path = Path(vault_info["path"])
            entry = {
                "name": vault_info.get("name", vault_name),
                "path": vault_info["path"],
                "description": vault_info.get("description", ""),
                "exists": vault_path.exists(),
            }

            if include_notes and vault_path.exists():
                notes = list(vault_path.glob("**/*.md"))
                entry["notes"] = [n.stem for n in notes]
                entry["note_count"] = len(notes)

            result[vault_name] = entry

        context.set(output_key, result)
        return context
