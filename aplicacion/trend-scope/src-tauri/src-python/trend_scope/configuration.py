"""Store the two workspace documents in the current user's data directory."""

import json
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel

CONFIG_FILES = ("cfg_data.json", "cfg_visual.json")


class ConfigurationName(BaseModel):
    name: str


class ConfigurationSnapshot(BaseModel):
    data: str
    visual: str


def directory() -> Path:
    if sys.platform == "win32":
        parent = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        parent = Path.home() / "Library" / "Application Support"
    else:
        parent = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return parent / "com.xurca.trend-scope"


def read_configuration(name: str) -> str:
    if name not in CONFIG_FILES:
        raise ValueError("Archivo de configuración desconocido")
    try:
        return (directory() / name).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_configurations(snapshot: ConfigurationSnapshot) -> None:
    contents = (snapshot.data, snapshot.visual)
    for raw in contents:
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get("schemaVersion") != 1:
            raise ValueError("Versión de configuración inválida")

    folder = directory()
    folder.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for raw in contents:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as file:
                staged.append(Path(file.name))
                file.write(raw + "\n")
                file.flush()
                os.fsync(file.fileno())
        for path, name in zip(staged, CONFIG_FILES):
            path.replace(folder / name)
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
