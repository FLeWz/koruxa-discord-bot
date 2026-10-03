import json
import os
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}

        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return {}

            return data

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            print(
                f"Could not load {self.path}: {exc}"
            )
            return {}

    def save(self, data: dict[str, Any]) -> None:
        temporary_path = Path(
            f"{self.path}.tmp"
        )

        try:
            with temporary_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    data,
                    file,
                    indent=2,
                    sort_keys=True,
                )
                file.write("\n")

            os.replace(
                temporary_path,
                self.path,
            )

        except OSError as exc:
            print(
                f"Could not save {self.path}: {exc}"
            )

