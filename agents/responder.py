"""Utilities for generating deterministic agent responses."""
from __future__ import annotations

from textwrap import dedent
from typing import Dict, Iterable, List, Tuple

from .persona import AgentPersona


def search_vault_notes(query: str, notes: Dict[str, str]) -> List[Tuple[str, str]]:
    """Return note snippets that roughly match the query text."""

    if not query.strip():
        return []

    lower_query = query.lower()
    results: List[Tuple[str, str]] = []
    for name, content in notes.items():
        lower_content = content.lower()
        if lower_query in lower_content:
            index = lower_content.index(lower_query)
            start = max(0, index - 120)
            end = min(len(content), index + 120)
            snippet = content[start:end].replace("\n", " ")
            results.append((name, snippet))
    return results[:3]


def build_response(
    persona: AgentPersona,
    user_message: str,
    notes: Dict[str, str],
    history: Iterable[Dict[str, str]] | None = None,
) -> str:
    """Create a deterministic response grounded in the vault notes."""

    matches = search_vault_notes(user_message, notes)
    context_lines: List[str] = [
        f"**Persona**: {persona.name}",
        f"**Focus**: {persona.description}",
    ]
    if history:
        last_user_inputs = [msg["content"] for msg in history if msg.get("role") == "user"]
        if last_user_inputs:
            context_lines.append(
                "**Recent asks**: " + "; ".join(last_user_inputs[-2:])
            )

    if matches:
        context_lines.append("**Vault evidence:**")
        for note, snippet in matches:
            context_lines.append(f"- `{note}` → {snippet.strip()}...")
        synthesis = dedent(
            f"""
            Synthesising from the {persona.vault_key} vault, I recommend we incorporate these
            references into the next coalition actions. The snippets above illustrate why the
            topic you raised connects directly to our stored knowledge. I can draft a follow-up
            plan or expand on any of the cited notes.
            """
        ).strip()
    else:
        synthesis = dedent(
            f"""
            I didn't find a direct match in the {persona.vault_key} vault, but I can still outline
            exploratory directions drawing on our stored knowledge. Consider adding new notes if
            this will be a recurring theme so the coalition can build shared context.
            """
        ).strip()

    context_lines.append("")
    context_lines.append(synthesis)

    return "\n".join(context_lines)
