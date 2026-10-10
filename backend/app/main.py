
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, UploadFile

from backend.app.services.file_profiler import profile_csv

app = FastAPI(
    title="OpenProfile API",
    description="Open-source data profiling and data quality platform",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "application": "OpenProfile"}


@app.post("/api/v1/profile/csv")
async def profile_uploaded_csv(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )

    temp_path = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            suffix=".csv",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

            while chunk := await file.read(1024 * 1024):
                temp_file.write(chunk)

        result = profile_csv(str(temp_path))
        return result

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to profile CSV: {exc}",
        ) from exc

    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
