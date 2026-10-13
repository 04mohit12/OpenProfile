from pathlib import Path

from backend.app.services.delimiter_detector import (
    detect_delimiter_from_file,
)
from backend.app.services.delimiter_detector import detect_delimiter


def test_detect_pipe_delimiter():
    text = (
        "C001|Mohit|Chennai|Developer\n"
        "C002|Rahul|Mumbai|Tester\n"
        "C003|Pradeep|Delhi|Manager\n"
    )

    result = detect_delimiter(text)

    assert result["delimiter"] == "|"
    assert result["name"] == "Pipe"


def test_detect_comma_delimiter():
    text = (
        "id,name,city\n"
        "1,Mohit,Chennai\n"
        "2,Rahul,Mumbai\n"
    )

    result = detect_delimiter(text)

    assert result["delimiter"] == ","
    assert result["name"] == "Comma"


def test_detect_semicolon_delimiter():
    text = (
        "id;name;city\n"
        "1;Mohit;Chennai\n"
        "2;Rahul;Mumbai\n"
    )

    result = detect_delimiter(text)

    assert result["delimiter"] == ";"
    assert result["name"] == "Semicolon"


def test_detect_tab_delimiter():
    text = (
        "id\tname\tcity\n"
        "1\tMohit\tChennai\n"
        "2\tRahul\tMumbai\n"
    )

    result = detect_delimiter(text)

    assert result["delimiter"] == "\t"
    assert result["name"] == "Tab"


def test_detect_space_delimiter():
    text = (
        "id name city\n"
        "1 Mohit Chennai\n"
        "2 Rahul Mumbai\n"
    )

    result = detect_delimiter(text)

    assert result["delimiter"] == " "
    assert result["name"] == "Space"


def test_empty_input_does_not_guess_delimiter():
    result = detect_delimiter("")

    assert result["delimiter"] is None
    assert result["name"] == "Unknown"


def test_detect_delimiter_from_file(tmp_path: Path):
    file_path = tmp_path / "customers.txt"
    file_path.write_text(
        "C001|Mohit|Chennai\n"
        "C002|Rahul|Mumbai\n"
        "C003|Pradeep|Delhi\n",
        encoding="utf-8",
    )

    result = detect_delimiter_from_file(str(file_path))

    assert result["delimiter"] == "|"
    assert result["name"] == "Pipe"


def test_empty_file_returns_unknown(tmp_path: Path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("", encoding="utf-8")

    result = detect_delimiter_from_file(str(file_path))

    assert result["delimiter"] is None
    assert result["name"] == "Unknown"


def test_file_sample_size_is_bounded(tmp_path: Path):
    file_path = tmp_path / "large.txt"
    file_path.write_text(
        "id|name|city\n"
        + ("1|Mohit|Chennai\n" * 10000),
        encoding="utf-8",
    )

    result = detect_delimiter_from_file(
        str(file_path),
        sample_bytes=64,
    )

    assert result["delimiter"] == "|"
    assert result["sample_rows"] <= 20
