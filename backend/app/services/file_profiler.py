
import polars as pl

from backend.app.core.profiler import profile_dataframe


def profile_csv(file_path: str) -> dict:
    """Profile a CSV while preserving mixed-type values as strings."""
    df = pl.read_csv(
        file_path,
        infer_schema=False,
        try_parse_dates=False,
    )
    return profile_dataframe(df)
