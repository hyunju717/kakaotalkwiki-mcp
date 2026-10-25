"""Alias wiki: maps what the user calls a room to its exact KakaoTalk title."""
import json
import os
from typing import Dict

from . import config


def load() -> Dict[str, str]:
    if not os.path.isfile(config.ALIASES_FILE):
        return {}
    with open(config.ALIASES_FILE, encoding="utf-8") as f:
        return json.load(f)


def resolve(name: str) -> str:
    """Return the exact room title for name, or name itself if it has no alias."""
    return load().get(name, name)


def save(alias: str, room_name: str):
    data = load()
    data[alias] = room_name
    save_all(data)


def save_all(data: Dict[str, str]):
    with open(config.ALIASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
