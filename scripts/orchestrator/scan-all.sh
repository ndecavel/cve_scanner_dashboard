#!/bin/bash

# CVE Scanner Dashboard - Multi-Scanner Orchestrator
# Runs Grype, Trivy, and Prisma Cloud on the same image list
# Merges results into unified output
#
# Usage:
#   ./scan-all.sh --input=images.txt --output-dir=./data/scans [--scanners=grype,trivy,prisma]
#
# Input format (text file, one image per line):
#   cgr.dev/chainguard/python:latest,chainguard
#   python:3.11,upstream
#
# Outputs:
#   - Individual scanner CSV files
#   - Merged CSV with all scanner results
#   - Summary report

set -euo pipefail

# Ensure standard tools are in PATH (including /tmp/bin for test environments)
export PATH="/tmp/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCANNER_DIR="$(cd "$SCRIPT_DIR/../scanners" && pwd)"

# Default values
INPUT_FILE=""
OUTPUT_DIR="./data/scans"
SCANNERS="grype,trivy,prisma"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_ID="${RUN_ID:-scan_$TIMESTAMP}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --input=*)
      INPUT_FILE="${1#*=}"
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#*=}"
      ;;
    --scanners=*)
      SCANNERS="${1#*=}"
      ;;
    --run-id=*)
      RUN_ID="${1#*=}"
      ;;
    -h|--help)
      echo "Usage: $0 --input=images.txt --output-dir=./data/scans [OPTIONS]"
      echo ""
      echo "Required:"
      echo "  --input=FILE          Input file with image list"
      echo ""
      echo "Optional:"
      echo "  --output-dir=DIR      Output directory for scan results (default: ./data/scans)"
      echo "  --scanners=LIST       Comma-separated list of scanners to run"
      echo "                        Options: grype,trivy,prisma (default: all)"
      echo "  --run-id=ID          Run identifier (default: scan_TIMESTAMP)"
      echo ""
      echo "Environment variables:"
      echo "  PRISMATOKEN          Prisma Cloud API token (required for Prisma)"
      echo "  PRISMA_ADDRESS       Prisma Cloud address (optional)"
      echo ""
      echo "Input format (CSV): image_ref,image_type"
      echo ""
      echo "Example:"
      echo "  $0 --input=images.txt --output-dir=./results --scanners=grype,trivy"
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
if [[ -z "$INPUT_FILE" ]]; then
  echo "Error: --input is required" >&2
  exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
  echo "Error: Input file not found: $INPUT_FILE" >&2
  exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Parse scanner list
IFS=',' read -ra SCANNER_LIST <<< "$SCANNERS"

echo "===========================================" >&2
echo "CVE Scanner Dashboard - Multi-Scanner Run" >&2
echo "===========================================" >&2
echo "Run ID: $RUN_ID" >&2
echo "Input: $INPUT_FILE" >&2
echo "Output: $OUTPUT_DIR" >&2
echo "Scanners: ${SCANNER_LIST[*]}" >&2
echo "" >&2

# Count images
image_count=$(grep -v '^[[:space:]]*#' "$INPUT_FILE" | grep -v '^[[:space:]]*$' | wc -l)
echo "Images to scan: $image_count" >&2
echo "" >&2

# Array to track successful scans
declare -a successful_scans=()
declare -a failed_scans=()

# Run each scanner
for scanner in "${SCANNER_LIST[@]}"; do
  scanner=$(echo "$scanner" | xargs)  # Trim whitespace

  echo "-------------------------------------------" >&2
  echo "Running scanner: $scanner" >&2
  echo "-------------------------------------------" >&2

  output_file="$OUTPUT_DIR/${RUN_ID}_${scanner}.csv"

  case "$scanner" in
    grype)
      if command -v grype &> /dev/null; then
        if "$SCANNER_DIR/scan-grype-or-trivy.sh" --scanner=grype --input="$INPUT_FILE" --output="$output_file"; then
          echo "✓ Grype scan completed: $output_file" >&2
          successful_scans+=("grype:$output_file")
        else
          echo "✗ Grype scan failed" >&2
          failed_scans+=("grype")
        fi
      else
        echo "⊘ Grype not installed, skipping" >&2
        failed_scans+=("grype (not installed)")
      fi
      ;;

    trivy)
      if command -v trivy &> /dev/null; then
        if "$SCANNER_DIR/scan-grype-or-trivy.sh" --scanner=trivy --input="$INPUT_FILE" --output="$output_file"; then
          echo "✓ Trivy scan completed: $output_file" >&2
          successful_scans+=("trivy:$output_file")
        else
          echo "✗ Trivy scan failed" >&2
          failed_scans+=("trivy")
        fi
      else
        echo "⊘ Trivy not installed, skipping" >&2
        failed_scans+=("trivy (not installed)")
      fi
      ;;

    prisma)
      if command -v twistcli &> /dev/null; then
        if [[ -z "${PRISMATOKEN:-}" ]]; then
          echo "⊘ PRISMATOKEN not set, skipping Prisma" >&2
          failed_scans+=("prisma (no token)")
        else
          if "$SCANNER_DIR/scan-prisma.sh" --input="$INPUT_FILE" --output="$output_file"; then
            echo "✓ Prisma scan completed: $output_file" >&2
            successful_scans+=("prisma:$output_file")
          else
            echo "✗ Prisma scan failed" >&2
            failed_scans+=("prisma")
          fi
        fi
      else
        echo "⊘ Prisma (twistcli) not installed, skipping" >&2
        failed_scans+=("prisma (not installed)")
      fi
      ;;

    *)
      echo "⊘ Unknown scanner: $scanner, skipping" >&2
      failed_scans+=("$scanner (unknown)")
      ;;
  esac

  echo "" >&2
done

# Merge results
echo "-------------------------------------------" >&2
echo "Merging scan results..." >&2
echo "-------------------------------------------" >&2

merged_file="$OUTPUT_DIR/${RUN_ID}_merged.csv"

if [[ ${#successful_scans[@]} -eq 0 ]]; then
  echo "✗ No successful scans to merge" >&2
  exit 1
fi

# Combine all CSV files (skip headers except first)
first=true
for scan_info in "${successful_scans[@]}"; do
  IFS=':' read -r scanner_name file_path <<< "$scan_info"

  if [[ "$first" == "true" ]]; then
    cat "$file_path" > "$merged_file"
    first=false
  else
    tail -n +2 "$file_path" >> "$merged_file"
  fi
done

echo "✓ Merged results: $merged_file" >&2

# Generate summary report
summary_file="$OUTPUT_DIR/${RUN_ID}_summary.txt"

cat > "$summary_file" <<EOF
CVE Scanner Dashboard - Scan Summary
====================================

Run ID: $RUN_ID
Date: $(date)
Input: $INPUT_FILE
Images scanned: $image_count

Scanners
--------
Requested: ${SCANNER_LIST[*]}
Successful: ${#successful_scans[@]}
Failed: ${#failed_scans[@]}

Successful scans:
EOF

for scan_info in "${successful_scans[@]}"; do
  IFS=':' read -r scanner_name file_path <<< "$scan_info"
  echo "  ✓ $scanner_name -> $file_path" >> "$summary_file"
done

if [[ ${#failed_scans[@]} -gt 0 ]]; then
  echo "" >> "$summary_file"
  echo "Failed/Skipped scans:" >> "$summary_file"
  for failed in "${failed_scans[@]}"; do
    echo "  ✗ $failed" >> "$summary_file"
  done
fi

echo "" >> "$summary_file"
echo "Output Files" >> "$summary_file"
echo "------------" >> "$summary_file"
echo "Merged CSV: $merged_file" >> "$summary_file"
echo "Summary: $summary_file" >> "$summary_file"

# Calculate aggregate statistics
echo "" >> "$summary_file"
echo "Aggregate Statistics" >> "$summary_file"
echo "--------------------" >> "$summary_file"

if command -v awk &> /dev/null; then
  # Total vulnerabilities across all scans
  total_vulns=$(awk -F',' 'NR>1 {sum+=$6} END {print sum}' "$merged_file")
  total_critical=$(awk -F',' 'NR>1 {sum+=$7} END {print sum}' "$merged_file")
  total_high=$(awk -F',' 'NR>1 {sum+=$8} END {print sum}' "$merged_file")
  total_medium=$(awk -F',' 'NR>1 {sum+=$9} END {print sum}' "$merged_file")
  total_low=$(awk -F',' 'NR>1 {sum+=$10} END {print sum}' "$merged_file")

  echo "Total vulnerabilities: $total_vulns" >> "$summary_file"
  echo "  Critical: $total_critical" >> "$summary_file"
  echo "  High: $total_high" >> "$summary_file"
  echo "  Medium: $total_medium" >> "$summary_file"
  echo "  Low: $total_low" >> "$summary_file"

  # Per-image averages
  num_scans=$(awk 'END {print NR-1}' "$merged_file")
  if [[ $num_scans -gt 0 ]]; then
    avg_vulns=$(echo "scale=1; $total_vulns / $num_scans" | bc)
    echo "" >> "$summary_file"
    echo "Average per scan: $avg_vulns vulnerabilities" >> "$summary_file"
  fi

  # Breakdown by image type
  echo "" >> "$summary_file"
  echo "By Image Type:" >> "$summary_file"

  for image_type in "chainguard" "upstream"; do
    type_total=$(awk -F',' -v type="$image_type" 'NR>1 && $4==type {sum+=$6} END {print sum+0}' "$merged_file")
    type_count=$(awk -F',' -v type="$image_type" 'NR>1 && $4==type {count++} END {print count+0}' "$merged_file")

    if [[ $type_count -gt 0 ]]; then
      type_avg=$(echo "scale=1; $type_total / $type_count" | bc)
      echo "  $image_type: $type_total total ($type_avg avg across $type_count scans)" >> "$summary_file"
    fi
  done
fi

echo "" >&2
echo "===========================================" >&2
echo "Scan Complete!" >&2
echo "===========================================" >&2
echo "Merged results: $merged_file" >&2
echo "Summary: $summary_file" >&2
echo "" >&2

cat "$summary_file" >&2
