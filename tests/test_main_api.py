

from fastapi.testclient import TestClient

from backend.app import main


main.app.dependency_overrides[main.get_authenticated_email] = (
    lambda: "testuser@example.com"
)

client = TestClient(main.app)



PIPE_FILE = (
    b"C001|Mohit|Chennai|Developer\n"
    b"C002|Rahul|Mumbai|Tester\n"
    b"C003|Pradeep|Delhi|Manager\n"
)


def upload_pipe_file(monkeypatch, tmp_path):
    """Upload a test file using isolated temporary storage."""

    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path.resolve())

    response = client.post(
        "/api/v1/delimiters/detect",
        files={
            "file": (
                "Testing_Delimiter.txt",
                PIPE_FILE,
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    return response.json()


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_txt_upload_detects_pipe_and_preserves_filename(
    monkeypatch, tmp_path
):
    result = upload_pipe_file(monkeypatch, tmp_path)

    assert result["filename"] == "Testing_Delimiter.txt"
    assert result["delimiter"] == "|"
    assert result["name"] == "Pipe"
    assert result["source_id"]

    source_path = (
        tmp_path.resolve() / f"{result['source_id']}.txt"
    )
    metadata_path = (
        tmp_path.resolve() / f"{result['source_id']}.json"
    )

    assert source_path.is_file()
    assert metadata_path.is_file()


def test_wrong_delimiter_returns_warning_without_profiling(
    monkeypatch, tmp_path
):
    uploaded = upload_pipe_file(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/delimiters/confirm-and-profile",
        json={
            "source_id": uploaded["source_id"],
            "delimiter": ",",
        },
    )

    assert response.status_code == 200

    result = response.json()
    assert result["detected_delimiter"] == "|"
    assert result["selected_delimiter"] == ","
    assert result["requires_confirmation"] is True
    assert "warning" in result
    assert "profiling" not in result


def test_correct_delimiter_profiles_four_columns(
    monkeypatch, tmp_path
):
    uploaded = upload_pipe_file(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/delimiters/confirm-and-profile",
        json={
            "source_id": uploaded["source_id"],
            "delimiter": "|",
        },
    )

    assert response.status_code == 200

    result = response.json()
    assert result["filename"] == "Testing_Delimiter.txt"
    assert result["confirmed_delimiter"] == "|"
    assert result["profiling"]["total_rows"] == 2
    assert result["profiling"]["total_columns"] == 4


def test_explicit_confirmation_allows_delimiter_override(
    monkeypatch, tmp_path
):
    uploaded = upload_pipe_file(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/delimiters/confirm-and-profile",
        json={
            "source_id": uploaded["source_id"],
            "delimiter": ",",
            "confirm_mismatch": True,
        },
    )

    assert response.status_code == 200

    result = response.json()
    assert result["filename"] == "Testing_Delimiter.txt"
    assert result["confirmed_delimiter"] == ","
    assert result["profiling"]["total_columns"] == 1


def test_invalid_source_id_is_rejected():
    response = client.post(
        "/api/v1/delimiters/confirm-and-profile",
        json={
            "source_id": "not-a-valid-uuid",
            "delimiter": "|",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid source_id."


def test_missing_source_file_returns_404(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path.resolve())

    response = client.post(
        "/api/v1/delimiters/confirm-and-profile",
        json={
            "source_id": "6905e50a-670c-415e-887f-2ce605ce0477",
            "delimiter": "|",
        },
    )

    assert response.status_code == 404
