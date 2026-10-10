
from __future__ import annotations

from typing import Any

import polars as pl


def profile_dataframe(df: pl.DataFrame) -> dict[str, Any]:
    """Generate exact basic statistics for each DataFrame column."""
    row_count = df.height
    column_count = df.width
    columns: list[dict[str, Any]] = []

    for name, dtype in df.schema.items():
        series = df.get_column(name)
        non_null = series.drop_nulls()
        null_count = series.null_count()
        filled_count = len(non_null)
        distinct_count = non_null.n_unique()

        blank_count = 0
        min_length = None
        max_length = None
        avg_length = None
        top_values = []

        if dtype == pl.String:
            stripped = non_null.str.strip_chars()
            blank_count = int((stripped == "").sum() or 0)

            lengths = non_null.str.len_chars()
            if filled_count:
                min_length = int(lengths.min())
                max_length = int(lengths.max())
                avg_length = round(float(lengths.mean()), 2)

            top_values = (
                non_null.value_counts(sort=True)
                .head(5)
                .to_dicts()
            )

        duplicate_value_count = filled_count - distinct_count

        columns.append(
            {
                "name": name,
                "data_type": str(dtype),
                "total_rows": row_count,
                "null_count": null_count,
                "null_percentage": round(null_count / row_count * 100, 2)
                if row_count else 0.0,
                "filled_count": filled_count,
                "blank_count": blank_count,
                "distinct_count": distinct_count,
                "duplicate_value_count": duplicate_value_count,
                "min_length": min_length,
                "max_length": max_length,
                "avg_length": avg_length,
                "top_values": top_values,
            }
        )

    return {
        "total_rows": row_count,
        "total_columns": column_count,
        "columns": columns,
    }
