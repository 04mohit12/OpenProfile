
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

    name = next(c for c in result["columns"] if c["name"] == "name")

    assert name["null_count"] == 1
    assert name["distinct_count"] == 2
    assert name["duplicate_value_count"] == 1
    assert name["blank_count"] == 0
    assert name["min_length"] == 1
    assert name["max_length"] == 1
    assert name["avg_length"] == 1.0


def test_blank_strings_and_nulls():
    df = pl.DataFrame({"city": ["Chennai", "", "  ", None]})

    result = profile_dataframe(df)
    city = result["columns"][0]

    assert city["null_count"] == 1
    assert city["blank_count"] == 2
    assert city["distinct_count"] == 3


def test_empty_dataframe():
    result = profile_dataframe(pl.DataFrame())

    assert result["total_rows"] == 0
    assert result["total_columns"] == 0
    assert result["columns"] == []
