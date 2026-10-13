import csv
from pathlib import Path

import polars as pl
import pandas as pd

from backend.app.core.profiler import profile_dataframe




def profile_csv(file_path: str) -> dict:
    """Detect the delimiter, validate CSV rows, and profile the CSV."""
    from backend.app.services.delimiter_detector import (
        detect_delimiter_from_file,
    )

    detection = detect_delimiter_from_file(
        file_path,
        sample_bytes=64 * 1024,
        max_rows=20,
    )

    delimiter = detection.get("delimiter")

    if not delimiter:
        raise ValueError(
            "Unable to detect the CSV delimiter. "
            "Please check the file format."
        )

    # Validate that every non-empty CSV record has the same field count.
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.reader(
                csv_file,
                delimiter=delimiter,
                strict=True,
            )

            expected_width = None
            inconsistent_rows = []

            for record_number, row in enumerate(reader, start=1):
                if not row:
                    continue

                if expected_width is None:
                    expected_width = len(row)
                elif len(row) != expected_width:
                    inconsistent_rows.append(
                        f"record {record_number}: "
                        f"expected {expected_width} fields, "
                        f"got {len(row)}"
                    )

                if len(inconsistent_rows) >= 5:
                    break

            if expected_width is None:
                raise ValueError("The CSV file is empty.")

            if inconsistent_rows:
                raise ValueError(
                    "The file contains inconsistent row widths. "
                    + "; ".join(inconsistent_rows)
                    + ". No profile was generated. "
                    "Please correct the file or review its structure."
                )

    except csv.Error as exc:
        raise ValueError(
            f"Invalid CSV structure: {exc}"
        ) from exc

    # Profile only after validation succeeds.
    df = pl.read_csv(
        file_path,
        separator=delimiter,
        infer_schema=False,
        try_parse_dates=False,
    )

    result = profile_dataframe(df)

    delimiter_label = {
        ",": "Comma (,)",
        ";": "Semicolon (;)",
        "|": "Pipe (|)",
        "\t": "Tab",
        " ": "Space",
    }.get(delimiter, repr(delimiter))

    result["delimiter"] = delimiter_label
    result["delimiter_character"] = delimiter

    return result





def profile_excel(
    file_path: str,
    sheet_name: str | None = None,
) -> dict:
    """Profile an Excel worksheet while preserving mixed values."""

    path = Path(file_path)
    extension = path.suffix.lower()

    if extension not in {".xlsx", ".xls"}:
        raise ValueError("Only .xlsx and .xls files are supported.")

    engine = "openpyxl" if extension == ".xlsx" else "xlrd"
    excel_file = pd.ExcelFile(file_path, engine=engine)

    try:
        available_sheets = excel_file.sheet_names

        if not available_sheets:
            raise ValueError("The Excel workbook contains no worksheets.")

        if sheet_name is None:
            sheet_name = available_sheets[0]

        if sheet_name not in available_sheets:
            raise ValueError(
                f"Worksheet '{sheet_name}' was not found. "
                f"Available worksheets: {available_sheets}"
            )

        pandas_df = pd.read_excel(
            excel_file,
            sheet_name=sheet_name,
            dtype=str,
            keep_default_na=False,
        )

        # Build Polars columns directly to preserve strings and blanks.
        columns = {
            str(name): pl.Series(
                str(name),
                pandas_df[name].tolist(),
                dtype=pl.String,
                strict=False,
            )
            for name in pandas_df.columns
        }

        df = pl.DataFrame(columns)

        return profile_dataframe(df)

    finally:
        excel_file.close()
