from pathlib import Path
import json
import yaml
import yaml.scanner


def validate_json(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            json.load(f)
        return True
    except json.JSONDecodeError:
        return False


def validate_yaml(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            yaml.safe_load(f)
        return True
    except yaml.scanner.ScannerError:
        return False
