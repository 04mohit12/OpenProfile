
import polars as pl

from backend.app.core.profiler import profile_dataframe


def test_basic_column_statistics():
    df = pl.DataFrame(
        {
            "name": ["A", "B", "A", None],
            "age": [20, 30, 20, 40],
        }
    )

    result = profile_dataframe(df)

    assert result["total_rows"] == 4
    assert result["total_columns"] == 2

    name_profile = next(
        col for col in result["columns"] if col["name"] == "name"
    )

    assert name_profile["null_count"] == 1
    assert name_profile["distinct_count"] == 3
    assert name_profile["duplicate_value_count"] == 1
