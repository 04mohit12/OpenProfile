
from __future__ import annotations

from collections import Counter
from io import StringIO
from typing import Any
import csv


SUPPORTED_DELIMITERS = {
    "|": "Pipe",
    ",": "Comma",
    ";": "Semicolon",
    "\t": "Tab",
    " ": "Space",
}


def detect_delimiter(
    text: str,
    max_rows: int = 20,
    custom_delimiters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Detect a likely delimiter from a limited text sample."""

    if not text or not text.strip():
        return {
            "delimiter": None,
            "name": "Unknown",
            "confidence": 0.0,
            "needs_confirmation": True,
            "sample_rows": 0,
        }

    candidates = dict(SUPPORTED_DELIMITERS)

    if custom_delimiters:
        candidates.update(custom_delimiters)

    # Inspect only the initial rows supplied to this function.
    sample_lines = text.splitlines()[:max_rows]
    sample = "\n".join(sample_lines)

    best_delimiter = None
    best_score = 0.0
    best_row_count = 0

    for delimiter, name in candidates.items():
        try:
            reader = csv.reader(
                StringIO(sample),
                delimiter=delimiter,
                strict=True,
            )
            rows = [
                row for row in reader
                if row and any(value.strip() for value in row)
            ]
        except (csv.Error, TypeError):
            continue

        if len(rows) < 2:
            continue

        widths = [len(row) for row in rows]

        # A delimiter should consistently produce multiple fields.
        if min(widths) < 2:
            continue

        width_counts = Counter(widths)
        most_common_width, matching_rows = width_counts.most_common(1)[0]

        consistency = matching_rows / len(widths)

        # Prefer consistent rows with multiple fields.
        score = consistency * (1 - 1 / most_common_width)

        if score > best_score:
            best_score = score
            best_delimiter = delimiter
            best_row_count = len(rows)

    # Avoid guessing when no delimiter produces a consistent structure.
    if best_delimiter is None:
        return {
            "delimiter": None,
            "name": "Unknown",
            "confidence": 0.0,
            "needs_confirmation": True,
            "sample_rows": len(sample_lines),
        }

    return {
        "delimiter": best_delimiter,
        "name": candidates[best_delimiter],
        "confidence": round(best_score * 100, 2),
        "needs_confirmation": best_score < 0.75,
        "sample_rows": best_row_count,
    }



def detect_delimiter_from_file(
    file_path: str,
    sample_bytes: int = 64 * 1024,
    max_rows: int = 20,
    custom_delimiters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Detect a delimiter using only a bounded sample of a text file."""

    if sample_bytes <= 0:
        raise ValueError("sample_bytes must be greater than zero.")

    if max_rows <= 0:
        raise ValueError("max_rows must be greater than zero.")

    # Read only a bounded number of bytes from the start of the file.
    with open(file_path, "rb") as file:
        sample_bytes_data = file.read(sample_bytes)

    if not sample_bytes_data:
        return detect_delimiter("")

    # Decode the sample. Ignore an incomplete UTF-8 character at its end.
    sample_text = sample_bytes_data.decode("utf-8-sig", errors="replace")

    # Only pass the configured initial rows to the detector.
    return detect_delimiter(
        sample_text,
        max_rows=max_rows,
        custom_delimiters=custom_delimiters,
    )
