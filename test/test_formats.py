from pathlib import Path
from stash.formats import validate_json, validate_yaml


def test_json_validator():
    assert validate_json(Path(__file__).parent / "assets/formats/valid.json")
    assert not validate_json(Path(__file__).parent / "assets/formats/invalid.json")


def test_yaml_validator():
    assert validate_yaml(Path(__file__).parent / "assets/formats/valid.yaml")
    assert not validate_yaml(Path(__file__).parent / "assets/formats/invalid.yaml")
