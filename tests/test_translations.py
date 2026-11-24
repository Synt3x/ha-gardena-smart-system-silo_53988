"""Texts are complete in every language."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent / "custom_components" / "gardena_sileno_local"


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def flat(node, path=""):
    if not isinstance(node, dict):
        return {path: node}
    return {key: value for k, v in node.items() for key, value in flat(v, f"{path}/{k}").items()}


def test_english_matches_strings():
    assert load("translations/en.json") == load("strings.json")


@pytest.mark.parametrize("language", ["sv"])
def test_complete(language):
    strings, translated = flat(load("strings.json")), flat(load(f"translations/{language}.json"))
    assert strings.keys() == translated.keys()
    for key, text in strings.items():
        assert set(re.findall(r"{\w+}", text)) == set(re.findall(r"{\w+}", translated[key])), key


def test_exceptions_exist():
    used = set()
    for name in ("__init__.py", "entity.py", "lawn_mower.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        used |= set(re.findall(r'translation_key="(\w+)"', source))
    assert used == set(load("strings.json")["exceptions"])


def test_icons_belong_to_named_entities():
    strings, icons = load("strings.json")["entity"], load("icons.json")["entity"]
    for platform, entities in icons.items():
        for key in entities:
            assert "name" in strings[platform][key], (platform, key)
