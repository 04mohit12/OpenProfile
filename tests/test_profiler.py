
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

    assert column["completeness_percentage"] == 75.0
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



