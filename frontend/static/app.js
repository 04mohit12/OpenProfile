"use strict";

const API_BASE = "/api/v1";

const $ = (id) => document.getElementById(id);

const state = {
  file: null,
  fileType: null,
  detection: null,
  excelSourceId: null,
  excelFilename: null,
  profile: null,
  columns: [],
};

const el = {
  fileInput: $("fileInput"),
  fileLabel: $("fileLabel"),
  uploadMessage: $("uploadMessage"),
  detectButton: $("detectButton"),
  dropzone: $("dropzone"),

  detectionPanel: $("detectionPanel"),
  detectedDelimiter: $("detectedDelimiter"),
  delimiterValue: $("delimiterValue"),
  confidence: $("confidence"),
  delimiterSelect: $("delimiterSelect"),
  sampleRows: $("sampleRows"),
  warningPanel: $("warningPanel"),
  warningMessage: $("warningMessage"),
  overrideButton: $("overrideButton"),
  profileButton: $("profileButton"),
  profileMessage: $("profileMessage"),

  excelPanel: $("excelPanel"),
  sheetSelect: $("sheetSelect"),
  excelProfileButton: $("excelProfileButton"),
  excelMessage: $("excelMessage"),

  resultsPanel: $("resultsPanel"),
  resultFilename: $("resultFilename"),
  datasetMeta: $("datasetMeta"),
  datasetDelimiter: $("datasetDelimiter"),
  totalRows: $("totalRows"),
  totalColumns: $("totalColumns"),
  overallCompleteness: $("overallCompleteness"),
  completenessFoot: $("completenessFoot"),
  columnsWithNulls: $("columnsWithNulls"),
  resultsMessage: $("resultsMessage"),

  columnSearch: $("columnSearch"),
  typeFilter: $("typeFilter"),
  columnSort: $("columnSort"),
  columnsTable: $("columnsTable"),
  columnCountLabel: $("columnCountLabel"),
  explorerMessage: $("explorerMessage"),

  detailsEmpty: $("detailsEmpty"),
  detailsContent: $("detailsContent"),
  detailColumnName: $("detailColumnName"),
  detailColumnType: $("detailColumnType"),
  detailNullCount: $("detailNullCount"),
  detailBlankCount: $("detailBlankCount"),
  detailCompleteness: $("detailCompleteness"),
  detailCompletenessFill: $("detailCompletenessFill"),
  detailCompletenessLabel: $("detailCompletenessLabel"),
  detailMissingLabel: $("detailMissingLabel"),
  detailDistinctCount: $("detailDistinctCount"),
  detailNonNullCount: $("detailNonNullCount"),
  detailDuplicateCount: $("detailDuplicateCount"),
  detailMinLength: $("detailMinLength"),
  detailMaxLength: $("detailMaxLength"),
  detailNote: $("detailNote"),
  topValues: $("topValues"),

  numericStatsSection: $("numericStatsSection"),
  numericMin: $("numericMin"),
  numericMax: $("numericMax"),
  numericMean: $("numericMean"),
  numericMedian: $("numericMedian"),
  numericStddev: $("numericStddev"),
  numericQ1: $("numericQ1"),
  numericQ3: $("numericQ3"),
  numericIqr: $("numericIqr"),
  numericOutlierCount: $("numericOutlierCount"),
  numericInvalidCount: $("numericInvalidCount"),
};

function showMessage(element, message, type = "") {
  if (!element) return;

  element.textContent = message || "";
  element.classList.remove("error", "success");

  if (type) element.classList.add(type);
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  const number = Number(value);

  return Number.isFinite(number)
    ? number.toLocaleString("en-IN")
    : String(value);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  const number = Number(value);

  return Number.isFinite(number)
    ? `${number.toFixed(1)}%`
    : String(value);
}

function firstDefined(object, keys) {
  for (const key of keys) {
    if (
      object &&
      object[key] !== undefined &&
      object[key] !== null
    ) {
      return object[key];
    }
  }

  return undefined;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDelimiter(delimiter) {
  const labels = {
    ",": "Comma (,)",
    ";": "Semicolon (;)",
    "|": "Pipe (|)",
    "\t": "Tab",
    " ": "Space",
  };

  return labels[delimiter] || String(delimiter || "Not detected");
}


function isSingleColumnFile(profile) {
  const columns = firstDefined(profile, [
    "total_columns",
    "column_count",
    "columns_count",
    "field_count",
  ]);

  return columns !== undefined && Number(columns) === 1;
}

function getDelimiterDisplay(profile) {
  if (!profile) return "Delimiter: -";

  const delimiter = profile.delimiter;
  const character = profile.delimiter_character;

  // A single-column file with no delimiter detected does not
  // need a delimiter to separate its fields.
  if (
    isSingleColumnFile(profile) &&
    state.detection &&
    !firstDefined(state.detection, [
      "delimiter",
      "detected_delimiter",
      "best_delimiter",
      "detectedDelimiter",
    ])
  ) {
    return "Single-column file | No delimiter detected";
  }

  if (delimiter) {
    return `Delimiter: ${delimiter}`;
  }

  if (character) {
    return `Delimiter: ${formatDelimiter(character)}`;
  }

  return "Delimiter: -";
}


function setBusy(button, busy, busyText = "Working...") {
  if (!button) return;

  if (busy) {
    if (button.dataset.busy === "true") return;

    button.dataset.busy = "true";
    button.dataset.originalText = button.textContent;
    button.dataset.originalDisabled = String(button.disabled);
    button.textContent = busyText;
    button.disabled = true;
  } else {
    if (button.dataset.busy !== "true") return;

    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = button.dataset.originalDisabled === "true";

    delete button.dataset.busy;
    delete button.dataset.originalText;
    delete button.dataset.originalDisabled;
  }
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const responseText = await response.text();

  let data = {};

  try {
    data = responseText ? JSON.parse(responseText) : {};
  } catch {
    data = {
      detail: responseText || "The server returned an unreadable response.",
    };
  }

  if (!response.ok) {
    const detail = firstDefined(data, ["detail", "message", "error"]);

    throw new Error(
      typeof detail === "string"
        ? detail
        : JSON.stringify(detail || `HTTP ${response.status}`)
    );
  }

  return data;
}

function fileFormData(file) {
  const form = new FormData();
  form.append("file", file);
  return form;
}

function navigateTo(view) {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });

  const pages = {
    overview: [
      "Overview",
      "Understand your data.",
      "Upload a dataset to explore its structure, completeness, and quality.",
    ],
    explorer: [
      "Column explorer",
      "Explore every field.",
      "Search columns and inspect the available profiling statistics.",
    ],
    upload: [
      "Upload dataset",
      "Bring your data in.",
      "Choose a supported file to begin profiling.",
    ],
  };

  const page = pages[view] || pages.overview;

  $("breadcrumbCurrent").textContent = page[0];
  $("pageTitle").textContent = page[1];
  $("pageSubtitle").textContent = page[2];

  if (view === "upload") {
    $("uploadPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (
    view === "explorer" &&
    !el.resultsPanel.classList.contains("hidden")
  ) {
    $("explorerSection").scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (
    view === "overview" &&
    !el.resultsPanel.classList.contains("hidden")
  ) {
    el.resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function setFile(file) {
  if (!file) return;

  const extension = file.name.split(".").pop().toLowerCase();

  if (!["csv", "txt", "xlsx", "xls"].includes(extension)) {
    showMessage(
      el.uploadMessage,
      "Unsupported file. Please select CSV, TXT, XLSX, or XLS.",
      "error"
    );
    return;
  }

  state.file = file;
  state.fileType = extension;
  state.detection = null;
  state.excelSourceId = null;
  state.excelFilename = null;

  el.fileLabel.textContent = `${file.name} | ${formatBytes(file.size)}`;
  el.detectButton.disabled = false;

  el.detectionPanel.classList.add("hidden");
  el.excelPanel.classList.add("hidden");

  showMessage(
    el.uploadMessage,
    "File selected. Click Analyze dataset to continue.",
    "success"
  );

  showMessage(el.profileMessage, "");
  showMessage(el.excelMessage, "");
  showMessage(el.resultsMessage, "");
}


async function analyzeSelectedFile() {
  if (!state.file) {
    showMessage(el.uploadMessage, "Please select a file first.", "error");
    return;
  }

  if (state.fileType === "csv" || state.fileType === "txt") {
    await detectTextDelimiter();
  } else {
    await uploadExcel();
  }
}



async function profileCsv() {
  setBusy(el.detectButton, true, "Profiling...");
  showMessage(el.uploadMessage, "Profiling CSV file...");

  try {
    const data = await apiRequest("/profile/csv", {
      method: "POST",
      body: fileFormData(state.file),
    });

    renderResults(data, state.file.name);

    showMessage(
      el.uploadMessage,
      "CSV profiling completed.",
      "success"
    );

    navigateTo("overview");
  } catch (error) {
    showMessage(
      el.uploadMessage,
      `CSV profiling failed: ${error.message}`,
      "error"
    );
  } finally {
    setBusy(el.detectButton, false);
  }
}


// TXT only: upload, save source_id, then show delimiter detection.
async function detectTextDelimiter() {
  setBusy(el.detectButton, true, "Detecting...");
  showMessage(el.uploadMessage, `Uploading ${state.fileType.toUpperCase()} and detecting delimiter...`);

  try {
    const data = await apiRequest("/delimiters/detect", {
      method: "POST",
      body: fileFormData(state.file),
    });

    const sourceId = firstDefined(data, ["source_id", "sourceId"]);

    if (!sourceId) {
      throw new Error("The detection response did not contain source_id.");
    }

    state.detection = { ...data, source_id: sourceId };

    const delimiter = firstDefined(data, [
      "delimiter",
      "detected_delimiter",
      "best_delimiter",
      "detectedDelimiter",
    ]);

    el.detectionPanel.classList.remove("hidden");

    el.detectedDelimiter.textContent = delimiter
      ? "Detection complete"
      : "Review required";

    el.delimiterValue.textContent = formatDelimiter(delimiter);

    const confidence = firstDefined(data, [
      "confidence",
      "confidence_score",
      "score",
    ]);

    if (confidence === undefined) {
      el.confidence.textContent = "Not provided";
    } else {
      const value = Number(confidence);
      el.confidence.textContent = Number.isFinite(value)
        ? `${(value <= 1 ? value * 100 : value).toFixed(1)}%`
        : String(confidence);
    }

    if (delimiter !== undefined) {
      const option = [...el.delimiterSelect.options].find(
        (item) => item.value === delimiter
      );

      if (option) el.delimiterSelect.value = delimiter;
    }

    const preview = firstDefined(data, [
      "sample_rows",
      "sample",
      "preview",
      "preview_rows",
      "sample_data",
    ]);

    el.sampleRows.textContent = formatPreview(preview);

    const warning = firstDefined(data, ["warning", "warnings", "recommendation"]);

    if (warning) {
      el.warningPanel.classList.remove("hidden");
      el.warningMessage.textContent =
        typeof warning === "string" ? warning : JSON.stringify(warning);
    } else {
      el.warningPanel.classList.add("hidden");
    }

    showMessage(
      el.profileMessage,
      "Review the delimiter, then click Profile with this delimiter."
    );

    showMessage(el.uploadMessage, "Delimiter detection completed.", "success");

    el.detectionPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showMessage(
      el.uploadMessage,
      `TXT Delimiter detection failed: ${error.message}`,
      "error"
    );
  } finally {
    setBusy(el.detectButton, false);
  }
}

function formatPreview(preview) {
  if (preview === null || preview === undefined) {
    return "No preview was returned by the API.";
  }

  if (typeof preview === "string") return preview;

  if (Array.isArray(preview)) {
    return preview.map((row) =>
      Array.isArray(row) ? row.join(" | ") : JSON.stringify(row)
    ).join("\n");
  }

  return JSON.stringify(preview, null, 2);
}

// ------------------------------------------------------------
// TXT profiling: matches ConfirmDelimiterRequest in main.py
// ------------------------------------------------------------




async function profileTextWithDelimiter(confirmMismatch = false) {
  if (!state.detection?.source_id) {
    showMessage(
      el.profileMessage,
      "Missing source ID. Please upload the TXT file and detect its delimiter again.",
      "error"
    );
    return;
  }

  setBusy(el.profileButton, true, "Profiling...");
  showMessage(
    el.profileMessage,
    "Profiling TXT using the selected delimiter..."
  );

  try {
    const response = await apiRequest(
      "/delimiters/confirm-and-profile",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: state.detection.source_id,
          delimiter: el.delimiterSelect.value,
          confirm_mismatch: confirmMismatch,
        }),
      }
    );

    if (response.requires_confirmation) {
      state.pendingDelimiterConfirmation = true;

      el.warningPanel.classList.remove("hidden");
      el.warningMessage.textContent =
        response.warning ||
        "The selected delimiter differs from the detected delimiter. Click Apply delimiter to confirm.";

      showMessage(
        el.profileMessage,
        "Please confirm the selected delimiter by clicking Apply delimiter.",
        "error"
      );
      return;
    }

    state.pendingDelimiterConfirmation = false;

    const profiling = response.profiling || response;

    renderResults(
      profiling,
      response.filename || state.file.name
    );

    const detectedDelimiter = firstDefined(state.detection, [
      "delimiter",
      "detected_delimiter",
      "best_delimiter",
      "detectedDelimiter",
    ]);

    const totalColumns = extractTotalColumns(
      profiling,
      extractColumnProfiles(profiling)
    );

    if (
      totalColumns === 1 &&
      (detectedDelimiter === undefined ||
        detectedDelimiter === null ||
        detectedDelimiter === "")
    ) {
      showMessage(
        el.profileMessage,
        "Single-column file detected. No delimiter was detected automatically; the selected delimiter does not change the one-column structure.",
        "success"
      );
    } else {
      showMessage(
        el.profileMessage,
        "TXT profiling completed.",
        "success"
      );
    }

    navigateTo("overview");
  } catch (error) {
    el.resultsPanel.classList.add("hidden");
    state.profile = null;
    state.columns = [];

    clearColumnDetails();

    showMessage(
      el.profileMessage,
      `TXT profiling failed: ${error.message}`,
      "error"
    );
  } finally {
    setBusy(el.profileButton, false);
  }
}



// Apply delimiter: if it differs from the detected delimiter,
// ask the backend to confirm it and profile using that delimiter.
async function applyDelimiter() {
  if (!state.detection?.source_id) {
    showMessage(
      el.profileMessage,
      "Run delimiter detection before applying a delimiter.",
      "error"
    );
    return;
  }

  const selected = el.delimiterSelect.value;
  const detected = firstDefined(state.detection, [
    "delimiter",
    "detected_delimiter",
    "best_delimiter",
    "detectedDelimiter",
  ]);

  el.delimiterValue.textContent = formatDelimiter(selected);

  const mismatch = detected !== undefined && selected !== detected;

  if (mismatch) {
    el.warningPanel.classList.remove("hidden");
    el.warningMessage.textContent =
      `You selected ${formatDelimiter(selected)} instead of ` +
      `${formatDelimiter(detected)}. Click "Profile with this delimiter" ` +
      "to confirm and continue.";
    showMessage(
      el.profileMessage,
      "The delimiter differs from the detected value. Click Profile with this delimiter to confirm.",
      "error"
    );
    return;
  }

  el.warningPanel.classList.add("hidden");
  showMessage(
    el.profileMessage,
    "Delimiter selected. Click Profile with this delimiter to generate the profile.",
    "success"
  );
}

// ------------------------------------------------------------
// Excel upload and worksheet profiling
// ------------------------------------------------------------

async function uploadExcel() {
  setBusy(el.detectButton, true, "Uploading...");
  showMessage(el.uploadMessage, "Uploading Excel workbook...");

  try {
    const data = await apiRequest("/excel/upload", {
      method: "POST",
      body: fileFormData(state.file),
    });

    state.excelSourceId = data.source_id;
    state.excelFilename = data.filename || state.file.name;

    if (!state.excelSourceId) {
      throw new Error("Excel upload response did not contain source_id.");
    }

    const sheets = Array.isArray(data.sheet_names)
      ? data.sheet_names
      : [];

    el.sheetSelect.replaceChildren();

    sheets.forEach((sheetName) => {
      const option = document.createElement("option");
      option.value = sheetName;
      option.textContent = sheetName;
      el.sheetSelect.appendChild(option);
    });

    if (data.default_sheet && sheets.includes(data.default_sheet)) {
      el.sheetSelect.value = data.default_sheet;
    }

    if (!sheets.length) {
      throw new Error("No worksheets were returned by the Excel upload API.");
    }

    el.excelPanel.classList.remove("hidden");

    showMessage(
      el.excelMessage,
      `Workbook uploaded. Select a worksheet from ${sheets.length} available worksheet(s).`,
      "success"
    );

    showMessage(el.uploadMessage, "Excel workbook uploaded.", "success");

    el.excelPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showMessage(
      el.uploadMessage,
      `Excel upload failed: ${error.message}`,
      "error"
    );
  } finally {
    setBusy(el.detectButton, false);
  }
}

async function profileExcel() {
  if (!state.excelSourceId) {
    showMessage(
      el.excelMessage,
      "Please upload the Excel workbook again.",
      "error"
    );
    return;
  }

  const sheetName = el.sheetSelect.value;

  if (!sheetName) {
    showMessage(el.excelMessage, "Please select a worksheet.", "error");
    return;
  }

  setBusy(el.excelProfileButton, true, "Profiling...");
  showMessage(el.excelMessage, `Profiling worksheet "${sheetName}"...`);

  try {
    const data = await apiRequest("/excel/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: state.excelSourceId,
        sheet_name: sheetName,
      }),
    });

    renderResults(
      data.profiling || data,
      `${data.filename || state.excelFilename} - ${data.sheet_name || sheetName}`
    );

    showMessage(el.excelMessage, "Excel worksheet profiling completed.", "success");
    navigateTo("overview");
  } catch (error) {
    showMessage(
      el.excelMessage,
      `Excel profiling failed: ${error.message}`,
      "error"
    );
  } finally {
    setBusy(el.excelProfileButton, false);
  }
}

// ------------------------------------------------------------
// Read the profile response
// ------------------------------------------------------------

function extractColumnProfiles(data) {
  const candidates = [
    data?.column_profiles,
    data?.columns,
    data?.profiles,
    data?.column_stats,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;

    if (candidate && typeof candidate === "object") {
      return Object.entries(candidate).map(([name, stats]) => ({
        column_name: name,
        ...(stats && typeof stats === "object" ? stats : {}),
      }));
    }
  }

  return [];
}

function extractTotalRows(data) {
  const value = firstDefined(data, [
    "total_rows",
    "row_count",
    "rows",
    "record_count",
  ]);

  if (value !== undefined && Number.isFinite(Number(value))) {
    return Number(value);
  }

  if (Array.isArray(data?.shape) && Number.isFinite(Number(data.shape[0]))) {
    return Number(data.shape[0]);
  }

  return null;
}

function extractTotalColumns(data, columns) {
  const value = firstDefined(data, [
    "total_columns",
    "column_count",
    "columns_count",
    "field_count",
  ]);

  if (value !== undefined && Number.isFinite(Number(value))) {
    return Number(value);
  }

  if (Array.isArray(data?.shape) && Number.isFinite(Number(data.shape[1]))) {
    return Number(data.shape[1]);
  }

  return columns.length || null;
}

function normalizeType(type) {
  const value = String(type || "Unknown").trim().toLowerCase();

  // Preserve semantic types before generic numeric matching.
  if (/phone[\s_-]*number|phonenumber/.test(value)) {
    return "Phone Number";
  }

  if (/postal[\s_-]*code|postcode|zip[\s_-]*code|pincode/.test(value)) {
    return "Postal Code";
  }

  if (/identifier|customerid|accountid|recordid|employeeid|productid|uuid/.test(value)) {
    return "Identifier";
  }

  if (/bool/.test(value)) return "Boolean";
  if (/datetime|timestamp/.test(value)) return "Date / Time";
  if (/date|time/.test(value)) return "Date / Time";
  if (/int|long|short|uint/.test(value)) return "Integer";
  if (/float|double|decimal|numeric|number/.test(value)) {
    return "Float / Decimal";
  }
  if (/str|string|object|utf8|categorical|category/.test(value)) {
    return "String";
  }

  return type ? String(type) : "Unknown";
}

function getTypeFilter(type) {
  const value = normalizeType(type).toLowerCase();

  if (value === "integer") return "integer";
  if (value.includes("float") || value.includes("decimal")) return "float";
  if (value === "boolean") return "boolean";
  if (value.includes("date") || value.includes("time")) return "date";
  if (value === "string") return "string";

  return "other";
}

function normalizeColumn(raw, index, totalRows) {
  const name = firstDefined(raw, [
    "column_name", "name", "column", "field", "columnName",
  ]) ?? `Column ${index + 1}`;

  const type = firstDefined(raw, [
    "inferred_type", "data_type", "dtype", "type", "detected_type",
  ]) ?? "Unknown";

  const nullRaw = firstDefined(raw, [
    "null_count", "nulls", "missing_count", "missing_values", "nulls_count",
  ]);

  const distinctRaw = firstDefined(raw, [
    "distinct_count", "unique_count", "n_unique", "distinct",
    "unique_values_count",
  ]);

  const nonNullRaw = firstDefined(raw, [
    "non_null_count", "nonnull_count", "filled_count", "not_null_count",
  ]);

  const blankRaw = firstDefined(raw, [
    "blank_count", "blankCount", "empty_string_count", "whitespace_count",
  ]);

  let nullCount = nullRaw !== undefined && Number.isFinite(Number(nullRaw))
    ? Number(nullRaw)
    : null;

  let nonNullCount = nonNullRaw !== undefined && Number.isFinite(Number(nonNullRaw))
    ? Number(nonNullRaw)
    : null;

  const blankCount = blankRaw !== undefined && blankRaw !== null &&
    Number.isFinite(Number(blankRaw))
      ? Number(blankRaw)
      : null;

  if (nullCount === null && nonNullCount !== null && totalRows !== null) {
    nullCount = Math.max(0, totalRows - nonNullCount);
  }

  if (nonNullCount === null && nullCount !== null && totalRows !== null) {
    nonNullCount = Math.max(0, totalRows - nullCount);
  }

  const completenessRaw = firstDefined(raw, [
    "completeness", "completeness_pct", "completeness_percentage",
    "filled_percentage", "non_null_percentage",
  ]);

  let completeness = null;

  if (completenessRaw !== undefined && Number.isFinite(Number(completenessRaw))) {
    const value = Number(completenessRaw);
    completeness = value >= 0 && value <= 1 ? value * 100 : value;
  } else if (totalRows > 0 && nonNullCount !== null) {
    completeness = (nonNullCount / totalRows) * 100;
  } else if (totalRows > 0 && nullCount !== null) {
    completeness = ((totalRows - nullCount) / totalRows) * 100;
  }

  const distinctCount = distinctRaw !== undefined && Number.isFinite(Number(distinctRaw))
    ? Number(distinctRaw)
    : null;



  const duplicateRaw = firstDefined(raw, [
      "duplicate_value_count",
      "duplicate_count",
      "duplicates",
      "repeated_count",
  ]);

  const duplicateCount =
      duplicateRaw !== undefined &&
      duplicateRaw !== null &&
      Number.isFinite(Number(duplicateRaw))
          ? Number(duplicateRaw)
          : null;

  console.log("Duplicate count check:", {
      column: name,
      backendValue: raw.duplicate_value_count,
      normalizedValue: duplicateCount,
  });
  return {
    raw,
    name: String(name),
    type: String(type),
    displayType: normalizeType(type),
    filterType: getTypeFilter(type),
    nullCount,
    blankCount,
    nonNullCount,
    distinctCount,
    duplicateCount,
    completeness: completeness === null
      ? null
      : Math.max(0, Math.min(100, completeness)),
    minLength: firstDefined(raw, ["min_length", "minimum_length", "min_len"]),
    maxLength: firstDefined(raw, ["max_length", "maximum_length", "max_len"]),
    topValues: firstDefined(raw, [
      "top_values", "value_counts", "frequencies",
      "top_value_counts", "distribution", "most_common",
    ]),
    numericMin: firstDefined(raw, ["numeric_min"]),
    numericMax: firstDefined(raw, ["numeric_max"]),
    numericMean: firstDefined(raw, ["numeric_mean"]),
    numericMedian: firstDefined(raw, ["numeric_median"]),
    numericStddev: firstDefined(raw, ["numeric_stddev"]),
    numericInvalidCount: firstDefined(raw, ["numeric_invalid_count"]),
    numericQ1: firstDefined(raw, ["numeric_q1"]),
    numericQ3: firstDefined(raw, ["numeric_q3"]),
    numericIqr: firstDefined(raw, ["numeric_iqr"]),
    numericOutlierCount: firstDefined(raw, ["numeric_outlier_count"]),
  };
}

// ------------------------------------------------------------
// Dashboard rendering
// ------------------------------------------------------------

function renderResults(data, filename) {
  state.profile = data;

  const rawColumns = extractColumnProfiles(data);
  const totalRows = extractTotalRows(data);
  const totalColumns = extractTotalColumns(data, rawColumns);

  state.columns = rawColumns.map((column, index) =>
    normalizeColumn(column, index, totalRows)
  );

  el.resultFilename.textContent = filename || "Dataset";
  el.datasetMeta.textContent =
    `${formatNumber(totalRows)} rows | ${formatNumber(totalColumns)} columns`;


  if (el.datasetDelimiter) {
    el.datasetDelimiter.textContent = getDelimiterDisplay(data);
    el.datasetDelimiter.classList.remove("hidden");
  }

  el.totalRows.textContent = formatNumber(totalRows);
  el.totalColumns.textContent = formatNumber(totalColumns);

  const knownNulls = state.columns.filter(c => c.nullCount !== null);

  const knownMissingStats = state.columns.filter(
    c => c.nullCount !== null &&
        c.nullCount !== undefined &&
        c.blankCount !== null &&
        c.blankCount !== undefined
  );

  const withMissing = knownMissingStats.filter(
    c => c.nullCount > 0 || c.blankCount > 0
  ).length;

  el.columnsWithNulls.textContent =
    knownMissingStats.length === state.columns.length
      ? formatNumber(withMissing)
      : "—";


  // Calculate dataset completeness from column completeness percentages,
  // which already exclude both NULL and blank values when supplied by the API.
  let completeness = null;

  if (
    state.columns.length > 0 &&
    state.columns.every(c => c.completeness !== null && c.completeness !== undefined)
  ) {
    completeness = state.columns.reduce(
      (sum, column) => sum + column.completeness,
      0
    ) / state.columns.length;
  }

  el.overallCompleteness.textContent =
    completeness === null ? "-" : formatPercent(completeness);

  el.completenessFoot.textContent = completeness === null
    ? "Not available from the returned statistics"
    : "Calculated from available column statistics";

  el.resultsPanel.classList.remove("hidden");

  showMessage(el.resultsMessage, "");
  renderColumnTable();
  clearColumnDetails();

  if (!state.columns.length) {
    showMessage(
      el.resultsMessage,
      "The API returned a response, but no column profiles were found. The response structure from the profiler needs to be checked.",
      "error"
    );
  }
}

// ------------------------------------------------------------
// Column explorer
// ------------------------------------------------------------

function renderColumnTable() {
  const search = (el.columnSearch.value || "").trim().toLowerCase();
  const filter = el.typeFilter.value;
  const sort = el.columnSort.value;

  const columns = state.columns.filter(column => {
    const matchesSearch = column.name.toLowerCase().includes(search);

    const matchesType =
      filter === "all" ||
      column.filterType === filter ||
      (filter === "numeric" &&
        ["integer", "float"].includes(column.filterType));

    return matchesSearch && matchesType;
  });

  columns.sort((a, b) => {
    if (sort === "nulls-desc") {
      return compareNullable(b.nullCount, a.nullCount);
    }
    if (sort === "nulls-asc") {
      return compareNullable(a.nullCount, b.nullCount);
    }
    if (sort === "distinct-desc") {
      return compareNullable(b.distinctCount, a.distinctCount);
    }
    if (sort === "completeness-asc") {
      return compareNullable(a.completeness, b.completeness);
    }

    return a.name.localeCompare(b.name);
  });

  el.columnsTable.replaceChildren();

  el.columnCountLabel.textContent =
    `${formatNumber(columns.length)} of ${formatNumber(state.columns.length)} columns`;

  if (!columns.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");

    cell.colSpan = 6;
    cell.className = "empty-state";
    cell.textContent = "No matching columns.";

    row.appendChild(cell);
    el.columnsTable.appendChild(row);
    showMessage(el.explorerMessage, "No matching columns.");
    return;
  }

  columns.forEach(column => {
    const row = document.createElement("tr");

    const nameCell = document.createElement("td");
    const name = document.createElement("div");
    name.className = "column-name";
    name.title = column.name;
    name.textContent = column.name;
    nameCell.appendChild(name);

    const typeCell = document.createElement("td");
    const type = document.createElement("span");
    type.className = "type-pill";
    type.textContent = column.displayType;
    typeCell.appendChild(type);

    const nullCell = document.createElement("td");
    nullCell.textContent = formatNumber(column.nullCount);

    const distinctCell = document.createElement("td");
    distinctCell.textContent = formatNumber(column.distinctCount);

    const completenessCell = document.createElement("td");

    if (column.completeness === null) {
      completenessCell.textContent = "-";
    } else {
      const pill = document.createElement("span");

      pill.className = "quality-pill " +
        (column.completeness >= 95
          ? "quality-good"
          : column.completeness >= 80
            ? "quality-medium"
            : "quality-low");

      pill.textContent = formatPercent(column.completeness);
      completenessCell.appendChild(pill);
    }

    const actionCell = document.createElement("td");
    const button = document.createElement("button");

    button.className = "details-button";
    button.type = "button";
    button.textContent = "View";
    button.addEventListener("click", () => showColumnDetails(column));

    actionCell.appendChild(button);

    row.append(
      nameCell,
      typeCell,
      nullCell,
      distinctCell,
      completenessCell,
      actionCell
    );

    el.columnsTable.appendChild(row);
  });

  showMessage(
    el.explorerMessage,
    `Showing ${columns.length} column${columns.length === 1 ? "" : "s"}.`
  );
}

function compareNullable(a, b) {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;

  return a - b;
}

// ------------------------------------------------------------
// Column details
// ------------------------------------------------------------

function clearColumnDetails() {
  el.detailsEmpty.classList.remove("hidden");
  el.detailsContent.classList.add("hidden");
  el.numericStatsSection.classList.add("hidden");
}

function showColumnDetails(column) {
  console.log("SHOW COLUMN DETAILS FIRED:", column.name);
  el.detailsEmpty.classList.add("hidden");
  el.detailsContent.classList.remove("hidden");

  // Column name and inferred data type
  el.detailColumnName.textContent = column.name;
  el.detailColumnType.textContent = column.displayType;

  // NULL, blank, distinct and non-NULL counts
  el.detailNullCount.textContent = formatNumber(column.nullCount);
  if (el.detailBlankCount) {
    el.detailBlankCount.textContent = formatNumber(column.blankCount);
  }
  el.detailDistinctCount.textContent = formatNumber(column.distinctCount);
  el.detailNonNullCount.textContent = formatNumber(column.nonNullCount);

  // Duplicate count and length statistics
  el.detailDuplicateCount.textContent =
    column.duplicateCount == null ? "—" : formatNumber(column.duplicateCount);
  el.detailMinLength.textContent = formatNumber(column.minLength);
  el.detailMaxLength.textContent = formatNumber(column.maxLength);

  // Completeness percentage and progress bar
  el.detailCompleteness.textContent = formatPercent(column.completeness);
  el.detailCompletenessFill.style.width =
    `${column.completeness === null ? 0 : column.completeness}%`;

  el.detailCompletenessLabel.textContent =
    column.nonNullCount === null
      ? "Filled values unavailable"
      : `${formatNumber(column.nonNullCount)} non-NULL`;

  el.detailMissingLabel.textContent =
    column.nullCount === null
      ? "NULL count unavailable"
      : `${formatNumber(column.nullCount)} NULL`;

  // Keep NULLs distinct from empty and whitespace-only strings.
  if (column.nullCount === null) {
    el.detailNote.textContent =
      "The API did not provide a NULL count for this field.";
  } else if (column.blankCount === null) {
    el.detailNote.textContent =
      `${formatNumber(column.nullCount)} NULL values were reported. ` +
      "Blank-value statistics are unavailable.";
  } else {
    const nulls = column.nullCount;
    const blanks = column.blankCount;

    if (nulls === 0 && blanks === 0) {
      el.detailNote.textContent =
        "No NULL or blank values were reported. " +
        "This does not confirm that every value meets business rules.";
    } else {
      el.detailNote.textContent =
        `${formatNumber(nulls)} NULL values and ` +
        `${formatNumber(blanks)} blank values were found. ` +
        "Review whether missing values are acceptable for this field.";
    }
  }

  console.log("Selected column:", column.name);
  console.log("Top values received by frontend:", column.topValues);
  renderTopValues(column.topValues);
  renderNumericStats(column);
}

function renderNumericStats(column) {
  const fields = [
    ["numericMin", column.numericMin],
    ["numericMax", column.numericMax],
    ["numericMean", column.numericMean],
    ["numericMedian", column.numericMedian],
    ["numericStddev", column.numericStddev],
    ["numericQ1", column.numericQ1],
    ["numericQ3", column.numericQ3],
    ["numericIqr", column.numericIqr],
    ["numericOutlierCount", column.numericOutlierCount],
    ["numericInvalidCount", column.numericInvalidCount],
  ];

  const hasNumericStats = fields.some(
    ([, value]) => value !== null && value !== undefined
  );

  el.numericStatsSection.classList.toggle("hidden", !hasNumericStats);

  fields.forEach(([elementId, value]) => {
    el[elementId].textContent = formatNumber(value);
  });
}

function renderTopValues(values) {
  el.topValues.replaceChildren();
  console.log("RENDER TOP VALUES FIRED:", values);
  if (
    values === undefined ||
    values === null ||
    (Array.isArray(values) && values.length === 0)
  ) {
    const message = document.createElement("p");
    message.className = "muted-copy";
    message.textContent = "No value distribution was returned for this column.";
    el.topValues.appendChild(message);
    return;
  }

  let entries = [];

  if (Array.isArray(values)) {
    entries = values.slice(0, 8).map(item => {
      if (Array.isArray(item)) return [item[0], item[1]];

      if (item && typeof item === "object") {
        return [
          firstDefined(item, ["value", "name", "label", "key"]) ?? "Unknown",
          firstDefined(item, ["count", "frequency", "total", "n"]),
        ];
      }

      return [String(item), undefined];
    });
  } else if (typeof values === "object") {
    entries = Object.entries(values).slice(0, 8);
  } else {
    entries = [[String(values), undefined]];
  }


  entries.forEach(([value, count]) => {
    const row = document.createElement("div");
    row.className = "top-value-row";

    const label = document.createElement("span");

    if (value === null || value === undefined) {
      label.textContent = "(null)";
    } else if (String(value) === "") {
      label.textContent = "(blank)";
    } else if (String(value).trim() === "") {
      label.textContent = "(whitespace only)";
    } else {
      label.textContent = String(value);
    }

    label.title = label.textContent;
    row.appendChild(label);


    if (count !== undefined && count !== null) {
      const number = document.createElement("strong");
      number.textContent = formatNumber(count);
      row.appendChild(number);
    }

    el.topValues.appendChild(row);
  });
}

// ------------------------------------------------------------
// Reset workspace
// ------------------------------------------------------------

function resetWorkspace() {
  state.file = null;
  state.fileType = null;
  state.detection = null;
  state.excelSourceId = null;
  state.excelFilename = null;
  state.profile = null;
  state.columns = [];

  el.fileInput.value = "";
  el.fileLabel.textContent = "No file selected";
  el.detectButton.disabled = true;

  el.detectionPanel.classList.add("hidden");
  el.excelPanel.classList.add("hidden");
  el.resultsPanel.classList.add("hidden");
  el.warningPanel.classList.add("hidden");

  el.columnSearch.value = "";
  el.typeFilter.value = "all";
  el.columnSort.value = "name";

  showMessage(el.uploadMessage, "Choose a file to start profiling.");
  showMessage(el.profileMessage, "");
  showMessage(el.excelMessage, "");
  showMessage(el.resultsMessage, "");

  navigateTo("upload");
}

// ------------------------------------------------------------
// Event handlers
// ------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".nav-item").forEach(button => {
    button.addEventListener("click", () => navigateTo(button.dataset.view));
  });

  $("headerUploadButton").addEventListener("click", () => navigateTo("upload"));
  $("newFileButton").addEventListener("click", resetWorkspace);
  $("closeColumnDetails").addEventListener("click", clearColumnDetails);

  el.fileInput.addEventListener("change", event => {
    setFile(event.target.files?.[0]);
  });

  el.detectButton.addEventListener("click", analyzeSelectedFile);

  // Applying a delimiter asks for confirmation when it differs.
  el.overrideButton.addEventListener("click", applyDelimiter);

  // Profile button retries with confirm_mismatch=true.
  el.profileButton.addEventListener("click", () =>
    profileTextWithDelimiter(true)
  );

  el.excelProfileButton.addEventListener("click", profileExcel);

  el.columnSearch.addEventListener("input", renderColumnTable);
  el.typeFilter.addEventListener("change", renderColumnTable);
  el.columnSort.addEventListener("change", renderColumnTable);

  ["dragenter", "dragover"].forEach(type => {
    el.dropzone.addEventListener(type, event => {
      event.preventDefault();
      el.dropzone.classList.add("drag-over");
    });
  });

  ["dragleave", "drop"].forEach(type => {
    el.dropzone.addEventListener(type, event => {
      event.preventDefault();
      el.dropzone.classList.remove("drag-over");
    });
  });

  el.dropzone.addEventListener("drop", event => {
    const file = event.dataTransfer?.files?.[0];
    if (file) setFile(file);
  });

  el.detectButton.disabled = true;
  showMessage(
    el.uploadMessage,
    "Choose a CSV, TXT, XLSX, or XLS file to begin."
  );
});
