import json
import sys
from pathlib import Path


def iter_data_sections(payload):
    if isinstance(payload, list):
        for idx, item in enumerate(payload):
            if isinstance(item, dict):
                data = item.get("result", {}).get("data")
                yield idx, data
            else:
                yield idx, None
    elif isinstance(payload, dict):
        data = payload.get("result", {}).get("data")
        yield 0, data
    else:
        raise ValueError("Expected a JSON list or object")


def check_data_sections(file_path: str, expected_len: int = 100):
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    issues = []
    section_count = 0

    for idx, data in iter_data_sections(payload):
        section_count += 1
        if data is None:
            issues.append((idx, "missing/empty"))
        elif len(data) != expected_len:
            issues.append((idx, len(data)))

    print(f"Checked {section_count} data section(s) in {path}")
    if issues:
        print(f"Found {len(issues)} issue(s):")
        for idx, value in issues:
            if value == "missing/empty":
                print(f"  section {idx}: missing or empty")
            else:
                print(f"  section {idx}: {value} items (expected {expected_len})")
    else:
        print("All sections look good.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_data_sections.py <json-file> [expected-length]")
        sys.exit(1)

    file_path = sys.argv[1]
    expected_len = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    check_data_sections(file_path, expected_len)
