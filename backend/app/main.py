
from pathlib import Path
import json
import os
import tempfile
import uuid

import polars as pl
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from backend.app.services import auth_service

from backend.app.services.delimiter_detector import (
    detect_delimiter_from_file,
)
from backend.app.services.file_profiler import profile_csv, profile_excel
from backend.app.core.profiler import profile_dataframe
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() == "true"

# --------------------------------------------------
# Application configuration
# --------------------------------------------------

app = FastAPI(
    title="OpenProfile API",
    description="Open-source data profiling and data quality platform",
    version="0.1.0",
)

# Project and frontend paths.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"

# Configurable backend storage directory.
STORAGE_DIR = Path(
    os.environ.get("STORAGE_PATH", "data/sources")
).resolve()


# --------------------------------------------------
# Frontend routes
# --------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


@app.get("/", include_in_schema=False)
def home():
    """Serve the OpenProfile dashboard."""
    return FileResponse(STATIC_DIR / "index.html")


# --------------------------------------------------
# Request models
# --------------------------------------------------

class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")

class ExcelProfileRequest(BaseModel):
    source_id: str
    sheet_name: str | None = None

class ConfirmDelimiterRequest(BaseModel):
    source_id: str
    delimiter: str
    confirm_mismatch: bool = False

def get_authenticated_email(request: Request) -> str:
    """Require a valid OpenProfile session for protected routes."""
    token = request.cookies.get("openprofile_session")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Please log in to use OpenProfile.",
        )

    email = auth_service.get_session_email(token)

    if not email:
        raise HTTPException(
            status_code=401,
            detail="Your session is invalid or expired. Please log in again.",
        )

    return email


# --------------------------------------------------
# Authentication routes
# --------------------------------------------------

@app.post("/api/v1/auth/request-otp")
def request_login_otp(
    payload: OTPRequest,
    request: Request,
):
    """Request a login OTP for an approved email address."""
    client_ip = (
        request.client.host if request.client else "unknown"
    )

    try:
        auth_service.request_otp(payload.email, client_ip)
    except ValueError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    # Use a generic response to avoid revealing allowlist membership.
    return {
        "message": (
            "If this email address is approved, "
            "a verification code will be sent."
        )
    }


@app.post("/api/v1/auth/verify-otp")
def verify_login_otp(
    payload: OTPVerifyRequest,
    response: Response,
):
    """Verify the OTP and issue an authenticated session."""

    try:
        is_valid = auth_service.verify_otp(
            payload.email,
            payload.otp,
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from None

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired verification code.",
        )


    try:
        token = auth_service.create_session(payload.email)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to create a login session.",
        ) from exc

    response.set_cookie(
        key="openprofile_session",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,  # Local development only; enable HTTPS in production.
        samesite="lax",
        max_age=auth_service.SESSION_TTL_SECONDS,
        path="/",
    )

    return {"message": "Login successful."}


@app.post("/api/v1/auth/logout")
def logout(
    request: Request,
    response: Response,
):
    """Revoke the current session and clear its cookie."""
    token = request.cookies.get("openprofile_session")

    if token:
        auth_service.revoke_session(token)

    response.delete_cookie(
        key="openprofile_session",
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,  # Local development only.
        samesite="lax",
    )

    return {"message": "Logged out successfully."}


@app.get("/api/v1/auth/me")
def get_current_session(request: Request):
    """Return the current authenticated user's email."""
    email = get_authenticated_email(request)
    return {"email": email, "authenticated": True}

# --------------------------------------------------
# Helper functions
# --------------------------------------------------


def get_source_path(source_id: str) -> Path:
    """Resolve a stored TXT or CSV source safely."""

    try:
        safe_id = str(uuid.UUID(source_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid source_id.",
        ) from exc

    metadata_path = STORAGE_DIR / f"{safe_id}.json"
    extension = ".txt"

    if metadata_path.is_file():
        try:
            metadata = json.loads(
                metadata_path.read_text(encoding="utf-8")
            )
            extension = metadata.get("extension", ".txt")
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400,
                detail="Unable to read uploaded source metadata.",
            ) from exc

    if extension not in {".txt", ".csv"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported source file type.",
        )

    source_path = (STORAGE_DIR / f"{safe_id}{extension}").resolve()

    if source_path.parent != STORAGE_DIR.resolve():
        raise HTTPException(
            status_code=400,
            detail="Invalid source_id.",
        )

    if not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Uploaded source not found. Please upload the file again.",
        )

    return source_path



def get_original_filename(source_id: str, source_path: Path) -> str:
    """Return the original uploaded filename when metadata exists."""

    metadata_path = STORAGE_DIR / f"{source_id}.json"

    if not metadata_path.is_file():
        return source_path.name

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
        filename = metadata.get("filename")

        if isinstance(filename, str) and filename:
            return Path(filename).name

    except (OSError, json.JSONDecodeError):
        pass

    return source_path.name


def profile_csv_dataframe(df: pl.DataFrame) -> dict:
    """Run the existing profiler on an already parsed DataFrame."""
    return profile_dataframe(df)


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "application": "OpenProfile",
    }


# --------------------------------------------------
# CSV profiling endpoint
# --------------------------------------------------


@app.post("/api/v1/profile/csv")
async def profile_uploaded_csv(
    file: UploadFile = File(...),
    email: str = Depends(get_authenticated_email),
):
    """Upload and profile a CSV file."""

    if not file.filename or Path(file.filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".csv",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

            while chunk := await file.read(1024 * 1024):
                temp_file.write(chunk)

        return profile_csv(str(temp_path))

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to profile CSV: {exc}",
        ) from exc

    finally:
        await file.close()

        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


# --------------------------------------------------
# Excel upload and worksheet discovery
# --------------------------------------------------



@app.post("/api/v1/excel/upload")
async def upload_excel(
    file: UploadFile = File(...),
    email: str = Depends(get_authenticated_email),
):
    """Upload an Excel workbook and return its worksheet names."""

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Please select an Excel file.",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in {".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail="Please upload an .xlsx or .xls file.",
        )

    source_id = str(uuid.uuid4())
    source_path = None
    metadata_path = STORAGE_DIR / f"{source_id}.json"

    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        source_path = STORAGE_DIR / f"{source_id}{extension}"

        with source_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                destination.write(chunk)

        import pandas as pd

        engine = "openpyxl" if extension == ".xlsx" else "xlrd"

        with pd.ExcelFile(source_path, engine=engine) as workbook:
            sheet_names = workbook.sheet_names

        if not sheet_names:
            raise HTTPException(
                status_code=400,
                detail="The workbook contains no worksheets.",
            )

        metadata_path.write_text(
            json.dumps({
                "filename": Path(file.filename).name,
                "extension": extension,
            }),
            encoding="utf-8",
        )

        return {
            "source_id": source_id,
            "filename": Path(file.filename).name,
            "sheet_names": sheet_names,
            "default_sheet": sheet_names[0],
        }

    except HTTPException:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise

    except Exception as exc:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail=f"Unable to read Excel workbook: {exc}",
        ) from exc

    finally:
        await file.close()





@app.post("/api/v1/excel/profile")
def profile_excel_worksheet(
    request: ExcelProfileRequest,
    email: str = Depends(get_authenticated_email),
):
    """Profile the selected worksheet from an uploaded workbook."""

    try:
        safe_id = str(uuid.UUID(request.source_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid source_id.",
        ) from exc

    metadata_path = STORAGE_DIR / f"{safe_id}.json"

    if not metadata_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Uploaded workbook not found. Please upload it again.",
        )

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read workbook metadata.",
        ) from exc

    extension = metadata.get("extension")

    if extension not in {".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail="The stored source is not an Excel workbook.",
        )

    source_path = (STORAGE_DIR / f"{safe_id}{extension}").resolve()

    if source_path.parent != STORAGE_DIR or not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Uploaded workbook not found. Please upload it again.",
        )

    try:
        import pandas as pd

        engine = "openpyxl" if extension == ".xlsx" else "xlrd"

        with pd.ExcelFile(source_path, engine=engine) as workbook:
            sheet_names = workbook.sheet_names

        sheet_name = request.sheet_name or (
            sheet_names[0] if sheet_names else None
        )

        if sheet_name not in sheet_names:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Worksheet not found. Available worksheets: "
                    f"{sheet_names}"
                ),
            )

        result = profile_excel(
            str(source_path),
            sheet_name=sheet_name,
        )

        return {
            "source_id": safe_id,
            "filename": metadata.get("filename", source_path.name),
            "sheet_name": sheet_name,
            "profiling": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to profile Excel worksheet: {exc}",
        ) from exc


# --------------------------------------------------
# TXT upload and delimiter detection
# --------------------------------------------------



@app.post("/api/v1/delimiters/detect")
async def detect_uploaded_txt_delimiter(
    file: UploadFile = File(...),
    email: str = Depends(get_authenticated_email),
):
    """Store a TXT or CSV upload and detect its delimiter."""

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Please select a TXT or CSV file.",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in {".txt", ".csv"}:
        raise HTTPException(
            status_code=400,
            detail="Please upload a .txt or .csv file.",
        )

    source_id = str(uuid.uuid4())
    source_path = None
    metadata_path = STORAGE_DIR / f"{source_id}.json"

    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        source_path = STORAGE_DIR / f"{source_id}{extension}"

        with source_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                destination.write(chunk)

        result = detect_delimiter_from_file(
            str(source_path),
            sample_bytes=64 * 1024,
            max_rows=20,
        )

        metadata_path.write_text(
            json.dumps({
                "filename": Path(file.filename).name,
                "extension": extension,
            }),
            encoding="utf-8",
        )

        return {
            "source_id": source_id,
            "filename": Path(file.filename).name,
            **result,
        }

    except HTTPException:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise

    except (OSError, UnicodeError) as exc:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail="Unable to inspect the uploaded TXT or CSV file.",
        ) from exc

    finally:
        await file.close()



# --------------------------------------------------
# Confirm delimiter and generate profiling report
# --------------------------------------------------




@app.post("/api/v1/delimiters/confirm-and-profile")
def confirm_delimiter_and_profile(
    request: ConfirmDelimiterRequest,
    email: str = Depends(get_authenticated_email),
):
    """Validate a delimited file and generate its profiling report."""
    import csv

    source_path = get_source_path(request.source_id)

    if (
        not isinstance(request.delimiter, str)
        or len(request.delimiter) != 1
        or request.delimiter in {"\r", "\n", "\x00"}
    ):
        raise HTTPException(
            status_code=400,
            detail="Delimiter must be one valid character.",
        )

    delimiter_labels = {
        ",": "Comma (,)",
        ";": "Semicolon (;)",
        "|": "Pipe (|)",
        "\t": "Tab",
        " ": "Space",
    }

    selected_label = delimiter_labels.get(
        request.delimiter, repr(request.delimiter)
    )

    try:
        detected = detect_delimiter_from_file(
            str(source_path),
            sample_bytes=64 * 1024,
            max_rows=20,
        )

        detected_delimiter = detected.get("delimiter")
        detected_label = delimiter_labels.get(
            detected_delimiter,
            repr(detected_delimiter)
            if detected_delimiter is not None
            else None,
        )

        mismatch = (
            detected_delimiter is not None
            and request.delimiter != detected_delimiter
        )

        if mismatch and not request.confirm_mismatch:
            return {
                "source_id": request.source_id,
                "filename": get_original_filename(
                    request.source_id, source_path
                ),
                "detected_delimiter": detected_delimiter,
                "selected_delimiter": request.delimiter,
                "warning": (
                    "The selected delimiter differs from the detected "
                    "delimiter. Confirm before profiling."
                ),
                "requires_confirmation": True,
            }

        # Validate the file using the detected delimiter before allowing
        # a confirmed alternative delimiter to produce a one-column profile.
        if mismatch and request.confirm_mismatch:
            detected_widths = []

            try:
                with source_path.open(
                    "r", encoding="utf-8-sig", newline=""
                ) as csv_file:
                    reader = csv.reader(
                        csv_file,
                        delimiter=detected_delimiter,
                        strict=True,
                    )

                    for record_number, row in enumerate(reader, start=1):
                        if not row or all(
                            value.strip() == "" for value in row
                        ):
                            continue

                        detected_widths.append(
                            (record_number, len(row))
                        )

            except (csv.Error, UnicodeError):
                detected_widths = []

            if detected_widths:
                detected_expected = detected_widths[0][1]
                detected_inconsistent = [
                    (record_number, width)
                    for record_number, width in detected_widths[1:]
                    if width != detected_expected
                ]

                if detected_inconsistent:
                    examples = "; ".join(
                        f"record {record_number}: expected "
                        f"{detected_expected} fields, got {width}"
                        for record_number, width
                        in detected_inconsistent[:5]
                    )

                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "The file contains inconsistent row widths "
                            f"when parsed using the detected delimiter "
                            f"({detected_label}). Examples: {examples}. "
                            "No profile was generated. Please correct "
                            "the file or review its structure."
                        ),
                    )

        # Preserve single-column files containing spaces when detection
        # found no delimiter, e.g. values such as "In Progress".
        single_column_mode = (
            detected_delimiter is None
            and request.delimiter == " "
        )

        parse_delimiter = (
            "\x1f" if single_column_mode else request.delimiter
        )

        widths = []

        try:
            with source_path.open(
                "r", encoding="utf-8-sig", newline=""
            ) as csv_file:
                reader = csv.reader(
                    csv_file,
                    delimiter=parse_delimiter,
                    strict=True,
                )

                for record_number, row in enumerate(reader, start=1):
                    if not row or all(
                        value.strip() == "" for value in row
                    ):
                        continue

                    widths.append((record_number, len(row)))

        except (csv.Error, UnicodeError) as exc:
            if mismatch:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"The selected delimiter ({selected_label}) "
                        f"could not parse this file consistently. "
                        f"The detected delimiter is {detected_label}. "
                        "Please select the detected delimiter or "
                        "review the file structure."
                    ),
                ) from exc

            raise HTTPException(
                status_code=400,
                detail=(
                    "Unable to parse the file as delimited text. "
                    "Check the quoting and delimiter. "
                    f"Parser detail: {exc}"
                ),
            ) from exc

        if not widths:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        expected_width = widths[0][1]

        inconsistent_rows = [
            (record_number, width)
            for record_number, width in widths[1:]
            if width != expected_width
        ]

        if mismatch and inconsistent_rows:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The selected delimiter ({selected_label}) "
                    f"produced inconsistent field counts. The detected "
                    f"delimiter is {detected_label}. Select it or review "
                    "the file structure. No profile was generated."
                ),
            )

        if inconsistent_rows:
            examples = "; ".join(
                f"record {record_number}: expected "
                f"{expected_width} fields, got {width}"
                for record_number, width in inconsistent_rows[:5]
            )

            raise HTTPException(
                status_code=400,
                detail=(
                    "The file contains inconsistent row widths. "
                    f"Examples: {examples}. No profile was generated. "
                    "Please correct the file or review its structure."
                ),
            )

        df = pl.read_csv(
            source_path,
            separator=parse_delimiter,
            infer_schema=False,
            try_parse_dates=False,
            encoding="utf8",
        )

        result = profile_csv_dataframe(df)

        result["delimiter"] = (
            "Single column (no delimiter detected)"
            if single_column_mode
            else selected_label
        )

        result["delimiter_character"] = (
            None if single_column_mode else request.delimiter
        )

        return {
            "source_id": request.source_id,
            "filename": get_original_filename(
                request.source_id, source_path
            ),
            "confirmed_delimiter": (
                None if single_column_mode else request.delimiter
            ),
            "profiling": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to profile delimited file: {exc}",
        ) from exc
