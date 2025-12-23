"""
File operation steps.

Steps for:
- Saving to various formats
- Loading from disk
- Managing output directories
"""

from typing import Any, Dict, Optional
from pathlib import Path
import json
import csv
import io
from datetime import datetime

from core.step import Step, StepResult
from core.context import ExecutionContext
from core.step_factory import register_step


@register_step("save_file")
class SaveFileStep(Step):
    """
    Save data to a file.

    Supports:
    - JSON, CSV, text formats
    - Automatic directory creation
    - Timestamped filenames
    """

    name = "save_file"
    description = "Save data to a file (JSON, CSV, or text)"

    config_schema = {
        "path": {"type": "string", "required": True, "description": "Output file path"},
        "input_key": {"type": "string", "default": "data", "description": "Context key containing data"},
        "format": {"type": "string", "enum": ["json", "csv", "text", "auto"], "default": "auto"},
        "append": {"type": "boolean", "default": False, "description": "Append to existing file"},
        "create_dirs": {"type": "boolean", "default": True, "description": "Create parent directories"},
        "timestamp": {"type": "boolean", "default": False, "description": "Add timestamp to filename"},
    }

    def _validate_config(self) -> None:
        if not self.config.get("path"):
            raise ValueError("SaveFileStep requires 'path' in config")

    def run(self, context: ExecutionContext) -> ExecutionContext:
        path = context.interpolate(self.config["path"])
        input_key = self.config.get("input_key", "data")
        fmt = self.config.get("format", "auto")
        append = self.config.get("append", False)
        create_dirs = self.config.get("create_dirs", True)
        timestamp = self.config.get("timestamp", False)

        data = context.get(input_key)
        if data is None:
            raise ValueError(f"No data found at key: {input_key}")

        # Add timestamp to filename if requested
        if timestamp:
            p = Path(path)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = str(p.parent / f"{p.stem}_{ts}{p.suffix}")

        file_path = Path(path)

        # Create directories if needed
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine format
        if fmt == "auto":
            suffix = file_path.suffix.lower()
            if suffix == ".json":
                fmt = "json"
            elif suffix == ".csv":
                fmt = "csv"
            else:
                fmt = "text"

        # Write data
        mode = "a" if append else "w"
        if fmt == "json":
            with open(file_path, mode) as f:
                json.dump(data, f, indent=2, default=str)
        elif fmt == "csv":
            self._write_csv(file_path, data, append)
        else:
            with open(file_path, mode) as f:
                if isinstance(data, (dict, list)):
                    f.write(json.dumps(data, indent=2, default=str))
                else:
                    f.write(str(data))

        # Store path in context
        context.set(f"{input_key}_saved_path", str(file_path))
        return context

    def _write_csv(self, path: Path, data: Any, append: bool) -> None:
        if not isinstance(data, list):
            data = [data]

        if not data:
            return

        mode = "a" if append else "w"
        write_header = not (append and path.exists())

        with open(path, mode, newline="") as f:
            if isinstance(data[0], dict):
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                if write_header:
                    writer.writeheader()
                writer.writerows(data)
            else:
                writer = csv.writer(f)
                for item in data:
                    writer.writerow([item] if not isinstance(item, (list, tuple)) else item)

    def dry_run(self, context: ExecutionContext) -> StepResult:
        path = context.interpolate(self.config.get("path", ""))
        return StepResult(
            success=True,
            metadata={
                "step": self.name,
                "action": f"Save to {path}",
                "format": self.config.get("format", "auto"),
            }
        )


@register_step("load_file")
class LoadFileStep(Step):
    """
    Load data from a file.

    Supports:
    - JSON, CSV, text formats
    - Glob patterns for multiple files
    """

    name = "load_file"
    description = "Load data from a file (JSON, CSV, or text)"

    config_schema = {
        "path": {"type": "string", "required": True, "description": "Input file path or glob pattern"},
        "output_key": {"type": "string", "default": "data", "description": "Context key for loaded data"},
        "format": {"type": "string", "enum": ["json", "csv", "text", "auto"], "default": "auto"},
        "encoding": {"type": "string", "default": "utf-8"},
    }

    def _validate_config(self) -> None:
        if not self.config.get("path"):
            raise ValueError("LoadFileStep requires 'path' in config")

    def run(self, context: ExecutionContext) -> ExecutionContext:
        path = context.interpolate(self.config["path"])
        output_key = self.config.get("output_key", "data")
        fmt = self.config.get("format", "auto")
        encoding = self.config.get("encoding", "utf-8")

        file_path = Path(path)

        # Check for glob pattern
        if "*" in path or "?" in path:
            files = list(Path(".").glob(path))
            data = [self._load_single(f, fmt, encoding) for f in files]
            context.set(f"{output_key}_files", [str(f) for f in files])
        else:
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            data = self._load_single(file_path, fmt, encoding)

        context.set(output_key, data)
        return context

    def _load_single(self, path: Path, fmt: str, encoding: str) -> Any:
        # Determine format
        if fmt == "auto":
            suffix = path.suffix.lower()
            if suffix == ".json":
                fmt = "json"
            elif suffix == ".csv":
                fmt = "csv"
            else:
                fmt = "text"

        with open(path, "r", encoding=encoding) as f:
            if fmt == "json":
                return json.load(f)
            elif fmt == "csv":
                reader = csv.DictReader(f)
                return list(reader)
            else:
                return f.read()


@register_step("save_to_vault")
class SaveToVaultStep(Step):
    """
    Save data as a markdown note in a vault.

    Integrates with the existing vault system.
    """

    name = "save_to_vault"
    description = "Save data as a markdown note in a vault"

    config_schema = {
        "vault": {"type": "string", "required": True, "description": "Vault name"},
        "note_name": {"type": "string", "required": True, "description": "Note filename (without .md)"},
        "input_key": {"type": "string", "default": "data", "description": "Context key containing data"},
        "template": {"type": "string", "description": "Markdown template with ${data} placeholder"},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        vault_name = context.interpolate(self.config["vault"])
        note_name = context.interpolate(self.config["note_name"])
        input_key = self.config.get("input_key", "data")
        template = self.config.get("template")

        data = context.get(input_key)

        # Load vault registry
        import yaml
        vault_config_path = Path("config/vaults.yaml")
        if vault_config_path.exists():
            with open(vault_config_path) as f:
                vaults = yaml.safe_load(f).get("vaults", {})
        else:
            vaults = {}

        if vault_name not in vaults:
            raise ValueError(f"Unknown vault: {vault_name}")

        vault_path = Path(vaults[vault_name]["path"])
        vault_path.mkdir(parents=True, exist_ok=True)

        # Format content
        if template:
            content = template.replace("${data}", self._format_data(data))
        else:
            content = self._format_data(data)

        # Add frontmatter
        timestamp = datetime.utcnow().isoformat()
        frontmatter = f"---\ncreated: {timestamp}\nsource: pipeline\n---\n\n"

        # Write note
        note_path = vault_path / f"{note_name}.md"
        with open(note_path, "w") as f:
            f.write(frontmatter + content)

        context.set(f"{input_key}_saved_note", str(note_path))
        return context

    def _format_data(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            lines = []
            for k, v in data.items():
                lines.append(f"**{k}**: {v}")
            return "\n\n".join(lines)
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                # Format as table
                headers = list(data[0].keys())
                lines = ["| " + " | ".join(headers) + " |"]
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for item in data:
                    row = [str(item.get(h, "")) for h in headers]
                    lines.append("| " + " | ".join(row) + " |")
                return "\n".join(lines)
            else:
                return "\n".join(f"- {item}" for item in data)
        else:
            return str(data)
