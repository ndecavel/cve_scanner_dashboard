#!/bin/bash

# CVE Scanner Dashboard - Customer Analysis Workflow
# End-to-end workflow: Map images → Resolve historical versions → Scan → Generate reports
#
# Usage:
#   ./run-customer-analysis.sh --customer="ACME Corp" --input=customer-images.txt --output-dir=./reports/acme

set -euo pipefail

# Ensure standard tools are in PATH
export PATH="/tmp/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default values
CUSTOMER_NAME=""
INPUT_FILE=""
MANUAL_MAPPINGS_FILE=""
OUTPUT_DIR=""
SCANNERS="grype"
RATE_LIMIT=1.0
WORKERS=5
VERBOSE=false
SKIP_MAPPING=false
SKIP_HISTORICAL=false
SKIP_SCAN=false
SKIP_REPORT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --customer=*)
      CUSTOMER_NAME="${1#*=}"
      ;;
    --input=*)
      INPUT_FILE="${1#*=}"
      ;;
    --manual-mappings=*)
      MANUAL_MAPPINGS_FILE="${1#*=}"
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#*=}"
      ;;
    --scanners=*)
      SCANNERS="${1#*=}"
      ;;
    --rate-limit=*)
      RATE_LIMIT="${1#*=}"
      ;;
    --workers=*)
      WORKERS="${1#*=}"
      ;;
    --verbose)
      VERBOSE=true
      ;;
    --skip-mapping)
      SKIP_MAPPING=true
      ;;
    --skip-historical)
      SKIP_HISTORICAL=true
      ;;
    --skip-scan)
      SKIP_SCAN=true
      ;;
    --skip-report)
      SKIP_REPORT=true
      ;;
    -h|--help)
      echo "Usage: $0 --customer=NAME [--input=FILE | --manual-mappings=FILE] --output-dir=DIR [OPTIONS]"
      echo ""
      echo "Required:"
      echo "  --customer=NAME       Customer name"
      echo "  --output-dir=DIR      Output directory for all results"
      echo ""
      echo "Input (choose one):"
      echo "  --input=FILE          Input file with customer image list (for automatic mapping)"
      echo "  --manual-mappings=FILE CSV file with manual upstream,chainguard mappings"
      echo ""
      echo "Optional:"
      echo "  --scanners=LIST       Comma-separated scanners (default: grype)"
      echo "  --rate-limit=N        API rate limit delay in seconds (default: 1.0)"
      echo "  --workers=N           Parallel workers for historical resolution (default: 5)"
      echo "  --verbose             Show detailed progress logging"
      echo "  --skip-mapping        Skip image mapping step"
      echo "  --skip-historical     Skip historical version resolution"
      echo "  --skip-scan           Skip scanning step"
      echo "  --skip-report         Skip report generation"
      echo ""
      echo "Examples:"
      echo "  # Automatic mapping"
      echo "  $0 --customer=\"ACME\" --input=images.txt --output-dir=./reports/acme"
      echo ""
      echo "  # Manual mappings (faster, more control)"
      echo "  $0 --customer=\"ACME\" --manual-mappings=mappings.csv --output-dir=./reports/acme"
      echo ""
      echo "  # Fast parallel processing with verbose logging"
      echo "  $0 --customer=\"ACME\" --manual-mappings=map.csv --workers=10 --verbose --output-dir=./reports/acme"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
  shift
done

# Validate required arguments
if [[ -z "$CUSTOMER_NAME" ]]; then
  echo "Error: --customer is required" >&2
  exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  echo "Error: --output-dir is required" >&2
  exit 1
fi

# Must have either INPUT_FILE or MANUAL_MAPPINGS_FILE
if [[ -z "$INPUT_FILE" && -z "$MANUAL_MAPPINGS_FILE" ]]; then
  echo "Error: Either --input or --manual-mappings is required" >&2
  exit 1
fi

# Can't have both
if [[ -n "$INPUT_FILE" && -n "$MANUAL_MAPPINGS_FILE" ]]; then
  echo "Error: Cannot use both --input and --manual-mappings. Choose one." >&2
  exit 1
fi

# Validate file exists
if [[ -n "$INPUT_FILE" && ! -f "$INPUT_FILE" ]]; then
  echo "Error: Input file not found: $INPUT_FILE" >&2
  exit 1
fi

if [[ -n "$MANUAL_MAPPINGS_FILE" && ! -f "$MANUAL_MAPPINGS_FILE" ]]; then
  echo "Error: Manual mappings file not found: $MANUAL_MAPPINGS_FILE" >&2
  exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate run ID
RUN_ID=$(echo "$CUSTOMER_NAME" | tr '[:upper:] ' '[:lower:]_')_$(date +%Y%m%d_%H%M%S)

echo "==========================================="
echo "CVE Scanner Dashboard - Customer Analysis"
echo "==========================================="
echo "Customer: $CUSTOMER_NAME"
if [[ -n "$INPUT_FILE" ]]; then
  echo "Input: $INPUT_FILE (automatic mapping)"
else
  echo "Input: $MANUAL_MAPPINGS_FILE (manual mappings)"
fi
echo "Output: $OUTPUT_DIR"
echo "Run ID: $RUN_ID"
echo "Scanners: $SCANNERS"
echo "Workers: $WORKERS"
if [[ "$VERBOSE" == "true" ]]; then
  echo "Verbose: enabled"
fi
echo ""

# Step 1: Map images to Chainguard equivalents
if [[ "$SKIP_MAPPING" == "false" ]]; then
  echo "Step 1/4: Mapping images to Chainguard equivalents..."
  echo "-------------------------------------------"

  MAPPINGS_FILE="$OUTPUT_DIR/${RUN_ID}_mappings.yaml"

  if [[ -n "$MANUAL_MAPPINGS_FILE" ]]; then
    # Use manual mappings from CSV
    echo "Using manual mappings from: $MANUAL_MAPPINGS_FILE"
    python "$SCRIPT_DIR/parse-manual-mappings.py" \
      --input="$MANUAL_MAPPINGS_FILE" \
      --output="$MAPPINGS_FILE" \
      --verbose
  else
    # Use automatic mapping
    echo "Using automatic mapping from: $INPUT_FILE"
    python "$SCRIPT_DIR/../mapping/map-to-chainguard.py" \
      --input="$INPUT_FILE" \
      --output="$MAPPINGS_FILE" \
      --mappings="$PROJECT_ROOT/config/chainguard-mappings.yaml" \
      --verbose
  fi

  echo ""
  echo "✓ Mappings saved to: $MAPPINGS_FILE"
  echo ""
else
  echo "Step 1/4: Skipping image mapping (using existing mappings)"
  MAPPINGS_FILE="$OUTPUT_DIR/${RUN_ID}_mappings.yaml"
  if [[ ! -f "$MAPPINGS_FILE" ]]; then
    echo "Error: Mappings file not found: $MAPPINGS_FILE" >&2
    exit 1
  fi
fi

# Step 2: Resolve historical versions
if [[ "$SKIP_HISTORICAL" == "false" ]]; then
  echo "Step 2/4: Resolving historical versions..."
  echo "-------------------------------------------"
  if [[ "$WORKERS" -gt 1 ]]; then
    echo "Using $WORKERS parallel workers for faster processing."
  fi
  echo "This may take several minutes depending on the number of images."
  echo ""

  HISTORICAL_FILE="$OUTPUT_DIR/${RUN_ID}_historical.yaml"

  # Build verbose flag if needed
  VERBOSE_FLAG=""
  if [[ "$VERBOSE" == "true" ]]; then
    VERBOSE_FLAG="--verbose"
  fi

  python "$SCRIPT_DIR/resolve-historical-versions.py" \
    --mappings="$MAPPINGS_FILE" \
    --output="$HISTORICAL_FILE" \
    --rate-limit="$RATE_LIMIT" \
    --workers="$WORKERS" \
    $VERBOSE_FLAG

  echo ""
  echo "✓ Historical versions saved to: $HISTORICAL_FILE"
  echo ""
else
  echo "Step 2/4: Skipping historical version resolution (using existing data)"
  HISTORICAL_FILE="$OUTPUT_DIR/${RUN_ID}_historical.yaml"
  if [[ ! -f "$HISTORICAL_FILE" ]]; then
    echo "Error: Historical file not found: $HISTORICAL_FILE" >&2
    exit 1
  fi
fi

# Step 3: Generate scan list and run scans
if [[ "$SKIP_SCAN" == "false" ]]; then
  echo "Step 3/4: Generating scan list and running scans..."
  echo "-------------------------------------------"

  SCAN_LIST_FILE="$OUTPUT_DIR/${RUN_ID}_scan_list.txt"

  python "$SCRIPT_DIR/generate-scan-list.py" \
    --input="$HISTORICAL_FILE" \
    --output="$SCAN_LIST_FILE" \
    --customer="$CUSTOMER_NAME"

  echo ""
  echo "✓ Scan list saved to: $SCAN_LIST_FILE"
  echo ""

  # Run scans
  echo "Running vulnerability scans..."
  echo ""

  "$SCRIPT_DIR/../orchestrator/scan-all.sh" \
    --input="$SCAN_LIST_FILE" \
    --output-dir="$OUTPUT_DIR" \
    --scanners="$SCANNERS" \
    --run-id="$RUN_ID"

  echo ""
  echo "✓ Scans complete"
  echo ""
else
  echo "Step 3/4: Skipping scan (using existing scan results)"
  SCAN_LIST_FILE="$OUTPUT_DIR/${RUN_ID}_scan_list.txt"
fi

# Step 4: Generate customer reports
if [[ "$SKIP_REPORT" == "false" ]]; then
  echo "Step 4/4: Generating customer reports..."
  echo "-------------------------------------------"

  # For now, create a simple summary report
  # Full report generator will be built separately

  SUMMARY_FILE="$OUTPUT_DIR/${RUN_ID}_analysis_summary.txt"

  cat > "$SUMMARY_FILE" <<EOF
CVE Scanner Dashboard - Customer Analysis Summary
==================================================

Customer: $CUSTOMER_NAME
Analysis Date: $(date)
Run ID: $RUN_ID

Files Generated:
---------------
- Mappings: ${RUN_ID}_mappings.yaml
- Historical Versions: ${RUN_ID}_historical.yaml
- Scan List: ${RUN_ID}_scan_list.txt
- Scan Results (merged): ${RUN_ID}_merged.csv
- Scan Summary: ${RUN_ID}_summary.txt

Next Steps:
-----------
1. Review scan results in: ${RUN_ID}_merged.csv
2. Import CSV into Excel/Sheets for analysis
3. Create comparison charts (Chainguard vs upstream)
4. Generate executive summary for customer

For detailed analysis, use:
  cat ${RUN_ID}_merged.csv | column -t -s,

EOF

  echo "✓ Analysis summary saved to: $SUMMARY_FILE"
  echo ""
fi

# Final summary
echo "==========================================="
echo "Customer Analysis Complete!"
echo "==========================================="
echo ""
echo "All results saved to: $OUTPUT_DIR"
echo ""
echo "Key files:"
echo "  - Scan results: $OUTPUT_DIR/${RUN_ID}_merged.csv"
echo "  - Summary: $OUTPUT_DIR/${RUN_ID}_summary.txt"
echo "  - Analysis summary: $OUTPUT_DIR/${RUN_ID}_analysis_summary.txt"
echo ""
echo "To view scan results:"
echo "  cat $OUTPUT_DIR/${RUN_ID}_merged.csv | column -t -s,"
echo ""
echo "To analyze in Python/Pandas:"
echo "  import pandas as pd"
echo "  df = pd.read_csv('$OUTPUT_DIR/${RUN_ID}_merged.csv')"
echo "  df.groupby('image_type')[['critical','high','medium','low']].sum()"
echo ""
