"""
XML Comparison API
==================
FastAPI application exposing a single POST /compare-xml endpoint.

Usage
-----
Start the server:

    uvicorn xml_comparator.main:app --reload

Then POST two XML files:

    curl -X POST http://localhost:8000/compare-xml \\
      -F "file_a=@reference.xml" \\
      -F "file_b=@target.xml" \\
      -F "case_insensitive=false" \\
      -F "numeric_tolerance=0.01" \\
      -F "ignore_fields=CreatedAt,UpdatedAt"
"""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from comparator.comparison_engine import compare_xml_trees
from models.schemas import ComparisonConfig, ComparisonResponse
from parser.xml_parser import XMLParseError, parse_xml_bytes
from reporter.report_generator import generate_report

app = FastAPI(
    title="XML Comparison API",
    description=(
        "Production-grade XML comparison engine.\n\n"
        "- Learns document structure dynamically from **file_a** (reference).\n"
        "- MULTIPLE nodes are matched strictly by index (ordered).\n"
        "- Leaf fields within a parent are compared by key, not by position (unordered).\n"
        "- Configurable: case-insensitive matching, numeric tolerance, field exclusions."
    ),
    version="1.0.0",
)


@app.post(
    "/compare-xml",
    response_model=ComparisonResponse,
    summary="Compare two XML files",
    responses={
        200: {"description": "Comparison completed – differences (if any) are in the response."},
        422: {"description": "One or both uploaded files contain invalid XML, or root tags differ."},
        500: {"description": "Unexpected server-side error during comparison."},
    },
)
async def compare_xml(
    file_a: UploadFile = File(..., description="Reference XML file. Structure is learned from this file."),
    file_b: UploadFile = File(..., description="Target XML file compared against the reference."),
    case_insensitive: bool = Form(
        False,
        description="Compare leaf values case-insensitively.",
    ),
    numeric_tolerance: float = Form(
        0.0,
        description=(
            "Maximum allowed absolute difference between two numeric values "
            "for them to be considered equal (e.g. 0.01). "
            "Set to 0 for exact numeric matching."
        ),
    ),
    ignore_fields: str = Form(
        "",
        description="Comma-separated list of XML tag names to exclude from comparison.",
    ),
) -> ComparisonResponse:
    """
    Compare **file_a** (reference) against **file_b** (target) and return a
    structured JSON diff report.

    ### Processing pipeline
    1. Parse both files with lxml (strict, large-file-safe).
    2. Analyse the structure of **file_a** to classify each tag as
       SINGLE or MULTIPLE.
    3. Recursively compare both trees using the learned structure:
       - MULTIPLE → ordered index matching
       - SINGLE → direct matching
       - Leaf level → unordered key-value comparison
    4. Apply rules (case-insensitivity, numeric tolerance, ignored fields).
    5. Return structured JSON with every detected difference.
    """
    # ── Parse ignore-fields form value ────────────────────────────────────
    ignore_list = [f.strip() for f in ignore_fields.split(",") if f.strip()]
    config = ComparisonConfig(
        case_insensitive=case_insensitive,
        numeric_tolerance=numeric_tolerance,
        ignore_fields=ignore_list,
    )

    # ── Read uploads ──────────────────────────────────────────────────────
    try:
        content_a = await file_a.read()
        content_b = await file_b.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded files: {exc}")

    if not content_a:
        raise HTTPException(status_code=422, detail="file_a is empty.")
    if not content_b:
        raise HTTPException(status_code=422, detail="file_b is empty.")

    # ── Parse XML ─────────────────────────────────────────────────────────
    try:
        root_a = parse_xml_bytes(content_a)
    except XMLParseError as exc:
        raise HTTPException(status_code=422, detail=f"file_a – {exc}")

    try:
        root_b = parse_xml_bytes(content_b)
    except XMLParseError as exc:
        raise HTTPException(status_code=422, detail=f"file_b – {exc}")

    # ── Compare ───────────────────────────────────────────────────────────
    try:
        differences = compare_xml_trees(root_a, root_b, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Comparison error: {exc}")

    # ── Report ────────────────────────────────────────────────────────────
    return generate_report(differences)


@app.get("/health", summary="Health check", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}
