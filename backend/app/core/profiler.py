
from __future__ import annotations

from typing import Any

import polars as pl


def profile_dataframe(df: pl.DataFrame) -> dict[str, Any]:
    """Generate a basic, exact profile of a Polars DataFrame."""
    row_count = df.height
    column_count = df.width

    columns: list[dict[str, Any]] = []

    for name, dtype in df.schema.items():
        series = df.get_column(name)
        null_count = series.null_count()
        filled_count = row_count - null_count
        distinct_count = series.n_unique()

        columns.append(
            {
                "name": name,
                "data_type": str(dtype),
                "total_rows": row_count,
                "null_count": null_count,
                "null_percentage": (
                    round(null_count / row_count * 100, 2)
                    if row_count
                    else 0.0
                ),
                "filled_count": filled_count,
                "distinct_count": distinct_count,
                "duplicate_value_count": filled_count - series.drop_nulls().n_unique(),
            }
        )

    return {
        "total_rows": row_count,
        "total_columns": column_count,
        "columns": columns,
    }
