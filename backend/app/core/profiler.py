
from __future__ import annotations

from typing import Any

import polars as pl



def calculate_numeric_statistics(
    values: pl.Series,
    inferred_type: str,
) -> dict[str, Any]:
    """Calculate numeric statistics only for numeric-like columns."""

    result = {
        "numeric_min": None,
        "numeric_max": None,
        "numeric_mean": None,
        "numeric_median": None,
        "numeric_stddev": None,
        "numeric_invalid_count": None,
        "numeric_q1": None,
        "numeric_q3": None,
        "numeric_iqr": None,
        "numeric_outlier_count": None,
    }

    excluded_types = {
        "Identifier",
        "Postal Code",
        "Phone Number",
        "Date",
        "Datetime",
        "Boolean",
        "Empty",
    }

    if inferred_type in excluded_types:
        return result

    non_null = values.drop_nulls().str.strip_chars()
    usable = non_null.filter(non_null != "")

    if len(usable) == 0:
        return result

    numeric = usable.cast(pl.Float64, strict=False)
    valid_numeric = numeric.drop_nulls()

    valid_count = len(valid_numeric)
    invalid_count = len(usable) - valid_count

    # Ordinary text columns should not report numeric-invalid counts.
    # Mixed columns with numeric values can still be profiled.
    if valid_count == 0:
        return result

    # Require at least half of the usable values to be numeric.
    # This permits mixed numeric columns such as amount with an invalid
    # value while preventing mostly textual columns from being analyzed.
    if valid_count / len(usable) < 0.5:
        return result

    result["numeric_invalid_count"] = invalid_count

    q1 = float(valid_numeric.quantile(0.25, interpolation="linear"))
    q3 = float(valid_numeric.quantile(0.75, interpolation="linear"))
    iqr = q3 - q1

    lower_bound = q1 - (1.5 * iqr)
    upper_bound = q3 + (1.5 * iqr)

    outlier_count = int(
        (
            (valid_numeric < lower_bound)
            | (valid_numeric > upper_bound)
        ).sum()
    )

    result.update({
        "numeric_min": float(valid_numeric.min()),
        "numeric_max": float(valid_numeric.max()),
        "numeric_mean": round(float(valid_numeric.mean()), 4),
        "numeric_median": round(float(valid_numeric.median()), 4),
        "numeric_stddev": (
            round(float(valid_numeric.std()), 4)
            if valid_count > 1
            else 0.0
        ),
        "numeric_q1": round(q1, 4),
        "numeric_q3": round(q3, 4),
        "numeric_iqr": round(iqr, 4),
        "numeric_outlier_count": outlier_count,
    })

    return result






def infer_string_type(
    values: pl.Series,
    column_name: str = "",
) -> str:
    """Infer a likely type using column names and value patterns."""

    cleaned = values.str.strip_chars()
    usable = cleaned.filter(cleaned != "")

    if len(usable) == 0:
        return "Empty"

    name = (
        column_name.lower()
        .replace("_", "")
        .replace(" ", "")
        .replace("-", "")
    )

    # Postal-code detection
    postal_hints = (
        "zipcode",
        "postalcode",
        "postcode",
        "pincode",
    )

    if any(hint in name for hint in postal_hints):
        if usable.str.contains(r"^[0-9]{3,12}$").all():
            return "Postal Code"

    # Phone-number detection
    phone_hints = (
        "phone",
        "mobile",
        "phonenumber",
        "telephone",
        "contactnumber",
    )

    if any(hint in name for hint in phone_hints):
        normalized = usable.str.replace_all(r"[\s().-]", "")
        valid_phone_mask = normalized.str.contains(
            r"^\+?[0-9]{7,15}$"
        )
        valid_phone_count = int(valid_phone_mask.sum() or 0)

        # Recognize phone columns even when some values are invalid.
        # Invalid values are reported separately by format validation.
        if valid_phone_count / len(usable) >= 0.5:
            return "Phone Number"

    # Identifier detection
    identifier_hints = (
        "identifier",
        "customerid",
        "accountid",
        "recordid",
        "employeeid",
        "productid",
        "uuid",
    )

    if any(hint in name for hint in identifier_hints) or name.endswith("id"):
        return "Identifier"

    # Boolean detection
    lowered = usable.str.to_lowercase()

    if lowered.is_in(["true", "false", "yes", "no"]).all():
        return "Boolean"

    # Integer detection
    integers = usable.cast(pl.Int64, strict=False)

    if integers.is_not_null().all():
        return "Integer"

    # Decimal detection
    decimals = usable.cast(pl.Float64, strict=False)

    if decimals.is_not_null().all():
        return "Decimal"

    # Date detection
    date_formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ]

    for date_format in date_formats:
        parsed_dates = usable.str.to_date(
            format=date_format,
            strict=False,
        )

        if parsed_dates.is_not_null().all():
            return "Date"

    # Datetime detection
    datetime_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for datetime_format in datetime_formats:
        parsed_datetimes = usable.str.to_datetime(
            format=datetime_format,
            strict=False,
        )

        if parsed_datetimes.is_not_null().all():
            return "Datetime"

    return "String"



def validate_column(
    values: pl.Series,
    column_name: str,
) -> dict[str, Any]:
    """Validate email or phone formats for recognized columns."""
    name = (
        column_name.lower()
        .replace("_", "")
        .replace(" ", "")
        .replace("-", "")
    )

    email_hints = ("email", "emailaddress")

    phone_hints = (
        "phone",
        "mobile",
        "phonenumber",
        "telephone",
        "contactnumber",
    )

    if any(hint in name for hint in email_hints):
        validation_type = "Email"
    elif any(hint in name for hint in phone_hints):
        validation_type = "Phone Number"
    else:
        return {
            "validation_type": None,
            "valid_count": None,
            "invalid_count": None,
            "validity_percentage": None,
        }

    # Exclude null and blank values from format validation.
    non_null = values.drop_nulls().str.strip_chars()
    usable = non_null.filter(non_null != "")

    if validation_type == "Email":
        pattern = (
            r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
            r"@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$"
        )
        valid_mask = usable.str.contains(pattern)
    else:
        # Allow common formatting characters in phone numbers.
        normalized = usable.str.replace_all(r"[\s().-]", "")
        valid_mask = normalized.str.contains(r"^\+?[0-9]{7,15}$")

    valid_count = int(valid_mask.sum() or 0)
    checked_count = len(usable)
    invalid_count = checked_count - valid_count

    return {
        "validation_type": validation_type,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "validity_percentage": round(
            valid_count / checked_count * 100, 2
        ) if checked_count else 0.0,
    }




def profile_dataframe(df: pl.DataFrame) -> dict[str, Any]:
    """Generate statistics and data-quality indicators per column."""
    row_count = df.height
    column_count = df.width
    columns: list[dict[str, Any]] = []

    for name, dtype in df.schema.items():
        series = df.get_column(name)
        non_null = series.drop_nulls()

        null_count = series.null_count()
        blank_count = 0

        if dtype == pl.String:
            stripped = non_null.str.strip_chars()
            blank_count = int((stripped == "").sum() or 0)

        filled_count = len(non_null)
        distinct_count = non_null.n_unique()
        numeric_statistics = {
            "numeric_min": None,
            "numeric_max": None,
            "numeric_mean": None,
            "numeric_median": None,
            "numeric_stddev": None,
            "numeric_invalid_count": None,
            "numeric_q1": None,
            "numeric_q3": None,
            "numeric_iqr": None,
            "numeric_outlier_count": None,
        }
        min_length = None
        max_length = None
        avg_length = None
        top_values: list[dict[str, Any]] = []

        if dtype == pl.String:
            stripped = non_null.str.strip_chars()
            blank_mask = stripped == ""
            blank_count = int(blank_mask.sum() or 0)

            if filled_count:
                lengths = non_null.str.len_chars()
                min_length = int(lengths.min())
                max_length = int(lengths.max())
                avg_length = round(float(lengths.mean()), 2)

            inferred_type = infer_string_type(non_null, name)
            usable_values = non_null.filter(~blank_mask)
            distinct_usable_count = usable_values.n_unique()
            validation = validate_column(series, name)
            numeric_statistics = calculate_numeric_statistics(
                non_null,
                inferred_type,
            )
        else:
            inferred_type = str(dtype)
            distinct_usable_count = distinct_count

            validation = {
                "validation_type": None,
                "valid_count": None,
                "invalid_count": None,
                "validity_percentage": None,
            }

        # Calculate top values using non-null values only.
        # This prevents actual nulls from appearing as "None"
        # and ensures top-value counts exclude missing records.
        if filled_count:
            counts_df = (
                non_null.value_counts(sort=True)
                .head(5)
            )

            top_values = [
                {
                    "value": str(row[name]),
                    "count": int(row["count"]),
                }
                for row in counts_df.to_dicts()
            ]

        # Number of repeated non-null values beyond the first occurrence.
        duplicate_value_count = filled_count - distinct_count

        # Exclude nulls and whitespace-only strings when determining
        # whether a column contains usable data.
        usable_count = filled_count - blank_count

        columns.append(
            {
                "name": name,
                "data_type": str(dtype),
                "inferred_type": inferred_type,
                "total_rows": row_count,
                "null_count": null_count,
                "null_percentage": round(
                    null_count / row_count * 100, 2
                ) if row_count else 0.0,
                "filled_count": filled_count,
                "blank_count": blank_count,
                "blank_percentage": round(
                    blank_count / row_count * 100, 2
                ) if row_count else 0.0,
                "completeness_percentage": round(
                    usable_count / row_count * 100, 2
                ) if row_count else 0.0,
                "distinct_count": distinct_count,
                "distinct_percentage": round(
                    distinct_usable_count / row_count * 100, 2
                ) if row_count else 0.0,
                "duplicate_value_count": duplicate_value_count,
                "is_constant": distinct_count == 1,
                "is_empty": usable_count == 0,
                "min_length": min_length,
                "max_length": max_length,
                "avg_length": avg_length,
                "top_values": top_values,
                **validation,
                **numeric_statistics,
            }
        )

    return {
        "total_rows": row_count,
        "total_columns": column_count,
        "columns": columns,
    }
