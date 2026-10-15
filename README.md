# OpenProfile

**An open-source data profiling and data quality platform for structured datasets.**

OpenProfile helps users understand their data through an interactive web application for uploading datasets and exploring data quality. The project aims to make data profiling accessible while supporting the analysis of large datasets.

**Live application:** https://openprofile.onrender.com  
**Source code:** https://github.com/04mohit12/OpenProfile

## Overview

Data profiling helps identify missing values, unusual patterns, duplicate records, inconsistent formats, and potential data quality issues before data is used for further analysis or processing.

OpenProfile is being developed to simplify this process through a web-based interface.

## Technology

The current project uses:

- **Backend:** Python and FastAPI
- **Data processing:** Pandas and Polars
- **Frontend:** HTML, CSS, and JavaScript
- **Testing:** Automated tests
- **Deployment:** Render

## Getting Started

### Prerequisites

- Python 3.11
- Git
- pip

### Clone the repository

```bash
git clone https://github.com/04mohit12/OpenProfile.git
cd OpenProfile
```

### Create and activate a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the application

```bash
uvicorn backend.app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser.

## Testing

Run the project's automated tests with:

```bash
pytest
```

## Project Status

OpenProfile is an actively developed personal open-source project. Features, performance, validation and the user experience continue to evolve.

## Roadmap

Planned improvements may include:

- Expanded data quality checks
- Improved profiling reports and visualizations
- Better handling of large datasets
- Additional automated tests
- Clearer documentation and usage examples

## Contributing

Suggestions, bug reports and contributions are welcome. Please open an issue to discuss a proposed change before submitting a pull request.

## License

This project is licensed under the Apache License 2.0. See the `LICENSE` file for details.
