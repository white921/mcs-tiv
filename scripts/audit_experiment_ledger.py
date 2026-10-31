"""Check that the experiment index and individual record states agree."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "experiments"
README = LEDGER / "README.md"
VALID_STATES = {
    "planned",
    "running",
    "completed",
    "failed",
    "incomplete",
    "superseded",
}
INDEX_ROW = re.compile(
    r"^\|\s*(?P<state>planned|running|completed|failed|incomplete|superseded)\s*"
    r"\|.*\[記録\]\((?P<path>[^)]+\.md)\)\s*\|\s*$"
)
INLINE_STATE = re.compile(
    r"^-\s*状態:\s*`(?P<state>planned|running|completed|failed|incomplete|superseded)`\s*$"
)
BLOCK_STATE = re.compile(
    r"^##\s+状態\s*$\n(?:\s*\n)*`(?P<state>planned|running|completed|failed|incomplete|superseded)`\s*$",
    re.MULTILINE,
)


def record_state(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = INLINE_STATE.match(line)
        if match:
            return match.group("state")
    match = BLOCK_STATE.search(text)
    if match:
        return match.group("state")
    raise ValueError(f"状態が見つかりません: {path.relative_to(ROOT)}")


def main() -> int:
    errors: list[str] = []
    indexed: dict[str, str] = {}

    for line in README.read_text(encoding="utf-8").splitlines():
        match = INDEX_ROW.match(line)
        if not match:
            continue
        relative = match.group("path")
        state = match.group("state")
        if relative in indexed:
            errors.append(f"READMEで記録が重複しています: {relative}")
        indexed[relative] = state

    records = {
        path.name: path
        for path in LEDGER.glob("*.md")
        if path.name not in {"README.md", "template.md"}
    }

    for relative, index_state in indexed.items():
        path = LEDGER / relative
        if not path.is_file():
            errors.append(f"READMEのリンク先がありません: {relative}")
            continue
        try:
            actual_state = record_state(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if actual_state not in VALID_STATES:
            errors.append(f"不正な状態です: {relative}: {actual_state}")
        elif actual_state != index_state:
            errors.append(
                f"状態が不一致です: {relative}: README={index_state}, 記録={actual_state}"
            )

    for name in sorted(records.keys() - indexed.keys()):
        errors.append(f"READMEに未掲載の記録があります: {name}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"experiment ledger OK: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
