
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

def test_constant_column_detection():
    df = pl.DataFrame({"status": ["ACTIVE", "ACTIVE", "ACTIVE"]})
    result = profile_dataframe(df)
    column = result["columns"][0]

    assert column["is_constant"] is True
    assert column["is_empty"] is False
    assert column["distinct_count"] == 1


def test_empty_column_detection():
    df = pl.DataFrame({"value": [None, None, None]})
    result = profile_dataframe(df)
    column = result["columns"][0]

    assert column["is_empty"] is True
    assert column["is_constant"] is False
    assert column["null_count"] == 3
    assert column["completeness_percentage"] == 0.0


def test_quality_percentages():
    df = pl.DataFrame({"city": ["Chennai", "", "  ", None]})
    result = profile_dataframe(df)
    column = result["columns"][0]

    assert column["completeness_percentage"] == 25.0
    assert column["blank_percentage"] == 50.0
    assert column["distinct_percentage"] == 25.0


def test_mixed_numeric_and_text_values_are_preserved():
    df = pl.DataFrame(
        {"zipcode": ["600001", "600002", "Unknown", None]}
    )

    result = profile_dataframe(df)
    column = result["columns"][0]

    assert column["total_rows"] == 4
    assert column["null_count"] == 1
    assert column["distinct_count"] == 3


def test_infer_integer_type():
    df = pl.DataFrame({"age": ["20", "30", "40"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Integer"


def test_infer_decimal_type():
    df = pl.DataFrame({"price": ["10.5", "20.75", "30.0"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Decimal"


def test_infer_boolean_type():
    df = pl.DataFrame({"active": ["true", "false", "true"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Boolean"


def test_infer_date_type():
    df = pl.DataFrame({"date": ["2026-10-10", "2026-10-11"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Date"


def test_infer_datetime_type():
    df = pl.DataFrame(
        {"created_at": ["2026-10-10 09:30:00", "2026-10-11 10:45:00"]}
    )
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Datetime"


def test_infer_mixed_values_as_string():
    df = pl.DataFrame({"zipcode": ["600001", "600002", "Unknown"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "String"


def test_infer_day_first_date_type():
    df = pl.DataFrame(
        {"birth_date": ["01-01-1970", "15-05-1990", "31-12-2020"]}
    )
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Date"


def test_infer_slash_separated_date_type():
    df = pl.DataFrame(
        {"birth_date": ["15/05/1990", "31/12/2020"]}
    )
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Date"


def test_phone_number_column_is_not_treated_as_integer():
    df = pl.DataFrame(
        {"Mobile": ["9811110443", "9820324286", "9268880303"]}
    )
    column = profile_dataframe(df)["columns"][0]

    assert column["inferred_type"] == "Phone Number"


def test_postal_code_detection():
    df = pl.DataFrame({"zipcode": ["060001", "060002", "060003"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Postal Code"


def test_identifier_detection():
    df = pl.DataFrame({"customer_id": ["10001", "10002", "10003"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Identifier"


def test_age_remains_integer():
    df = pl.DataFrame({"age": ["20", "30", "40"]})
    column = profile_dataframe(df)["columns"][0]
    assert column["inferred_type"] == "Integer"


def test_email_validation():
    df = pl.DataFrame({
        "email": [
            "mohit@example.com",
            "invalid-email",
            "user@test.org",
            "",
            None,
        ]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["validation_type"] == "Email"
    assert column["valid_count"] == 2
    assert column["invalid_count"] == 1
    assert column["validity_percentage"] == 66.67


def test_phone_validation():
    df = pl.DataFrame({
        "Mobile": [
            "9876543210",
            "98765",
            "+919876543210",
            None,
            "",
        ]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["validation_type"] == "Phone Number"
    assert column["valid_count"] == 2
    assert column["invalid_count"] == 1
    assert column["validity_percentage"] == 66.67



def test_unrelated_column_has_no_format_validation():
    df = pl.DataFrame({"age": ["20", "30", "40"]})

    column = profile_dataframe(df)["columns"][0]

    assert column["validation_type"] is None
    assert column["valid_count"] is None
    assert column["invalid_count"] is None
    assert column["validity_percentage"] is None


def test_numeric_statistics_for_string_column():
    df = pl.DataFrame({
        "amount": ["10", "20", "30", "40"]
    })

    column = profile_dataframe(df)["columns"][0]

    # Existing type inference should remain intact.
    assert column["inferred_type"] == "Integer"

    # These fields will be added by our numeric profiling enhancement.
    assert column["numeric_min"] == 10.0
    assert column["numeric_max"] == 40.0
    assert column["numeric_mean"] == 25.0
    assert column["numeric_median"] == 25.0


def test_numeric_statistics_with_invalid_values():
    df = pl.DataFrame({
        "amount": ["10", "20", "not-a-number", "30", None]
    })

    column = profile_dataframe(df)["columns"][0]

    # Numeric statistics should use successfully parsed values only.
    assert column["numeric_min"] == 10.0
    assert column["numeric_max"] == 30.0
    assert column["numeric_mean"] == 20.0
    assert column["numeric_median"] == 20.0

    # Invalid values must be reported separately from actual nulls.
    assert column["numeric_invalid_count"] == 1
    assert column["null_count"] == 1


def test_numeric_statistics_do_not_convert_identifiers():
    df = pl.DataFrame({
        "customer_id": ["001", "002", "003"]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["inferred_type"] == "Identifier"

    # Identifier values must not be treated as numeric measures.
    assert column["numeric_min"] is None
    assert column["numeric_max"] is None



def test_numeric_statistics_detect_iqr_outliers():
    df = pl.DataFrame({
        "amount": [
            "10", "11", "12", "13", "14",
            "15", "16", "17", "18", "1000",
        ]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["numeric_q1"] is not None
    assert column["numeric_q3"] is not None
    assert column["numeric_iqr"] is not None
    assert column["numeric_outlier_count"] == 1


def test_numeric_statistics_no_outliers():
    df = pl.DataFrame({
        "amount": ["10", "11", "12", "13", "14"]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["numeric_outlier_count"] == 0


def test_identifiers_have_no_numeric_outlier_statistics():
    df = pl.DataFrame({
        "customer_id": ["001", "002", "003"]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["numeric_q1"] is None
    assert column["numeric_q3"] is None
    assert column["numeric_iqr"] is None
    assert column["numeric_outlier_count"] is None



def test_blank_values_are_separate_from_null_values():
    import polars as pl

    from backend.app.core.profiler import profile_dataframe

    df = pl.DataFrame(
        {
            "city": [
                "Chennai",
                "",
                "   ",
                None,
            ]
        }
    )

    result = profile_dataframe(df)
    column = result["columns"][0]

    assert column["total_rows"] == 4
    assert column["null_count"] == 1
    assert column["blank_count"] == 2
    assert column["filled_count"] == 3
    assert column["completeness_percentage"] == 25.0


def test_text_columns_do_not_report_numeric_invalid_values():
    import polars as pl

    from backend.app.core.profiler import profile_dataframe

    df = pl.DataFrame(
        {
            "city": ["Chennai", "Mumbai", "Delhi"],
            "email": [
                "arun@example.com",
                "devi@example.com",
                "farah@example.com",
            ],
        }
    )

    result = profile_dataframe(df)
    columns = {column["name"]: column for column in result["columns"]}

    for name in ("city", "email"):
        column = columns[name]

        assert column["inferred_type"] == "String"
        assert column["numeric_min"] is None
        assert column["numeric_max"] is None
        assert column["numeric_invalid_count"] is None
        assert column["numeric_outlier_count"] is None


def test_duplicate_count_excludes_nulls():
    df = pl.DataFrame({
        "value": ["A", "A", "B", None]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["null_count"] == 1
    assert column["filled_count"] == 3
    assert column["distinct_count"] == 2
    assert column["duplicate_value_count"] == 1


def test_top_values_exclude_actual_nulls():
    df = pl.DataFrame({
        "email": [
            "arun@example.com",
            "NULL",
            "N/A",
            None,
            "arun@example.com",
        ]
    })

    column = profile_dataframe(df)["columns"][0]
    top_values = column["top_values"]

    assert sum(item["count"] for item in top_values) == 4
    assert any(
        item["value"] == "NULL" and item["count"] == 1
        for item in top_values
    )
    assert any(
        item["value"] == "N/A" and item["count"] == 1
        for item in top_values
    )
    assert not any(item["value"] == "None" for item in top_values)


def test_completeness_excludes_nulls_and_whitespace():
    df = pl.DataFrame({
        "phone": ["9876543210", "1234567890", "   ", None]
    })

    column = profile_dataframe(df)["columns"][0]

    assert column["null_count"] == 1
    assert column["blank_count"] == 1
    assert column["completeness_percentage"] == 50.0


def test_mixed_decimal_column_reports_type_and_invalid_value():
    df = pl.DataFrame({
        "amount": [
            "120.50",
            "45.00",
            "invalid",
            "99.00",
            "-5.00",
        ]
    })

    column = profile_dataframe(df)["columns"][0]

    # Current behavior: mixed numeric/text values remain String.
    assert column["inferred_type"] == "String"

    # Numeric profiling should still identify valid and invalid values.
    assert column["numeric_min"] == -5.0
    assert column["numeric_max"] == 120.5
    assert column["numeric_invalid_count"] == 1

