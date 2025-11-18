#!/bin/bash

# CVE Scanner Dashboard - Grype/Trivy Scanner
# Adapted from cookbook/scripts/scans/scan-array-grype-or-trivy.sh
#
# Usage:
#   ./scan-grype-or-trivy.sh [--scanner=grype|trivy] [--input=file.txt] [--output=results.csv]
#
# Input format (text file, one image per line):
#   cgr.dev/chainguard/python:latest,chainguard
#   python:3.11,upstream
#   mcr.microsoft.com/dotnet/runtime:8.0,upstream
#
# Format: image_ref,image_type
# image_type: "chainguard" or "upstream"

set -euo pipefail

# Ensure standard tools are in PATH (including /tmp/bin for test environments)
export PATH="/tmp/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Default values
SCANNER="grype"
INPUT_FILE=""
OUTPUT_FILE=""
SCAN_DATE=$(date +%Y-%m-%d)

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --scanner=*)
      SCANNER="${1#*=}"
      ;;
    --input=*)
      INPUT_FILE="${1#*=}"
      ;;
    --output=*)
      OUTPUT_FILE="${1#*=}"
      ;;
    -h|--help)
      echo "Usage: $0 [--scanner=grype|trivy] [--input=file.txt] [--output=results.csv]"
      echo ""
      echo "Options:"
      echo "  --scanner=SCANNER  Scanner to use (grype or trivy), default: grype"
      echo "  --input=FILE       Input file with image list (or use stdin)"
      echo "  --output=FILE      Output CSV file (or use stdout)"
      echo ""
      echo "Input format (CSV): image_ref,image_type"
      echo "  image_type: 'chainguard' or 'upstream'"
      echo ""
      echo "Example:"
      echo "  echo 'cgr.dev/chainguard/python:latest,chainguard' | $0 --scanner=grype"
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

# Validate scanner
if [[ "$SCANNER" != "grype" && "$SCANNER" != "trivy" ]]; then
  echo "Error: Scanner must be 'grype' or 'trivy', got: $SCANNER" >&2
  exit 1
fi

# Check if scanner is installed
if ! command -v "$SCANNER" &> /dev/null; then
  echo "Error: $SCANNER is not installed or not in PATH" >&2
  exit 1
fi

# Read images from file or stdin
declare -a images=()
declare -A image_types=()

if [[ -n "$INPUT_FILE" ]]; then
  if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: Input file not found: $INPUT_FILE" >&2
    exit 1
  fi
  input_source="$INPUT_FILE"
else
  input_source="/dev/stdin"
fi

# Parse input
while IFS=',' read -r image_ref image_type || [[ -n "$image_ref" ]]; do
  # Skip empty lines and comments
  [[ -z "$image_ref" || "$image_ref" =~ ^[[:space:]]*# ]] && continue

  # Trim whitespace
  image_ref=$(echo "$image_ref" | xargs)
  image_type=$(echo "$image_type" | xargs)

  # Default image_type to "unknown" if not specified
  [[ -z "$image_type" ]] && image_type="unknown"

  # Add :latest if no tag specified
  if [[ "$image_ref" != *:* ]]; then
    image_ref="${image_ref}:latest"
  fi

  images+=("$image_ref")
  image_types["$image_ref"]="$image_type"
done < "$input_source"

if [[ ${#images[@]} -eq 0 ]]; then
  echo "Error: No images to scan" >&2
  exit 1
fi

echo "Starting scan with $SCANNER for ${#images[@]} images..." >&2

# Pull images
echo "Pulling images..." >&2
for image in "${images[@]}"; do
  echo "  Pulling $image..." >&2
  if ! docker pull "$image" 2>&1 | grep -iq "error"; then
    :  # Success, do nothing
  else
    echo "Error: Failed to pull $image" >&2
    exit 1
  fi
done

# CSV header
csv_header="scan_date,image_name,image_tag,image_type,scanner,total,critical,high,medium,low,wontfix,fixed_total,fixed_critical,fixed_high,fixed_medium,fixed_low,size_mb,created_date"

# Output header
if [[ -n "$OUTPUT_FILE" ]]; then
  echo "$csv_header" > "$OUTPUT_FILE"
else
  echo "$csv_header"
fi

# Scan images
for image in "${images[@]}"; do
  echo "  Scanning $image with $SCANNER..." >&2

  # Get image metadata
  image_type="${image_types[$image]}"
  size=$(docker inspect "$image" | jq -r '.[0].Size // 0')
  size_mb=$(echo "scale=2; $size / 1024 / 1024" | bc)

  # Try to get created date from image config
  created_date=$(docker inspect "$image" | jq -r '.[0].Created // "unknown"' | cut -d'T' -f1)

  # Parse image name and tag
  if [[ "$image" =~ ^(.+):([^:]+)$ ]]; then
    image_name="${BASH_REMATCH[1]}"
    image_tag="${BASH_REMATCH[2]}"
  else
    image_name="$image"
    image_tag="unknown"
  fi

  if [[ "$SCANNER" == "grype" ]]; then
    # Run Grype scan
    scan_output=$(grype "$image" -o json 2>/dev/null || echo '{"matches":[]}')

    total=$(echo "$scan_output" | jq '[.matches[].vulnerability] | length')
    critical=$(echo "$scan_output" | jq '[.matches[] | select(.vulnerability.severity == "Critical")] | length')
    high=$(echo "$scan_output" | jq '[.matches[] | select(.vulnerability.severity == "High")] | length')
    medium=$(echo "$scan_output" | jq '[.matches[] | select(.vulnerability.severity == "Medium")] | length')
    low=$(echo "$scan_output" | jq '[.matches[] | select(.vulnerability.severity == "Low")] | length')
    wontfix=$(echo "$scan_output" | jq '[.matches[] | select(.vulnerability.fix.state == "wont-fix")] | length')
    fixed_total=$(echo "$scan_output" | jq '[.matches[] | select((.vulnerability.fix.state | ascii_downcase) == "fixed")] | length')
    fixed_critical=$(echo "$scan_output" | jq '[.matches[] | select((.vulnerability.severity | ascii_downcase) == "critical" and (.vulnerability.fix.state | ascii_downcase) == "fixed")] | length')
    fixed_high=$(echo "$scan_output" | jq '[.matches[] | select((.vulnerability.severity | ascii_downcase) == "high" and (.vulnerability.fix.state | ascii_downcase) == "fixed")] | length')
    fixed_medium=$(echo "$scan_output" | jq '[.matches[] | select((.vulnerability.severity | ascii_downcase) == "medium" and (.vulnerability.fix.state | ascii_downcase) == "fixed")] | length')
    fixed_low=$(echo "$scan_output" | jq '[.matches[] | select((.vulnerability.severity | ascii_downcase) == "low" and (.vulnerability.fix.state | ascii_downcase) == "fixed")] | length')

  elif [[ "$SCANNER" == "trivy" ]]; then
    # Run Trivy scan
    scan_output=$(trivy image -f json "$image" 2>/dev/null || echo '{"Results":[]}')

    # Trivy aggregation
    total=$(echo "$scan_output" | jq 'if (.Results | length) == 0 then 0 else [.Results[] | select(has("Vulnerabilities")) | .Vulnerabilities[]] | length end')
    critical=$(echo "$scan_output" | jq 'if (.Results | length) == 0 then 0 else [.Results[] | select(has("Vulnerabilities")) | .Vulnerabilities[] | select(.Severity == "CRITICAL")] | length end')
    high=$(echo "$scan_output" | jq 'if (.Results | length) == 0 then 0 else [.Results[] | select(has("Vulnerabilities")) | .Vulnerabilities[] | select(.Severity == "HIGH")] | length end')
    medium=$(echo "$scan_output" | jq 'if (.Results | length) == 0 then 0 else [.Results[] | select(has("Vulnerabilities")) | .Vulnerabilities[] | select(.Severity == "MEDIUM")] | length end')
    low=$(echo "$scan_output" | jq 'if (.Results | length) == 0 then 0 else [.Results[] | select(has("Vulnerabilities")) | .Vulnerabilities[] | select(.Severity == "LOW")] | length end')
    wontfix=$(echo "$scan_output" | jq 'if (.Results | length) == 0 then 0 else [.Results[] | select(has("Vulnerabilities")) | .Vulnerabilities[] | select(.Status == "will_not_fix")] | length end')

    # Trivy doesn't provide fixed information in the same way
    fixed_total=0
    fixed_critical=0
    fixed_high=0
    fixed_medium=0
    fixed_low=0
  fi

  # Build CSV row
  csv_row="$SCAN_DATE,$image_name,$image_tag,$image_type,$SCANNER,$total,$critical,$high,$medium,$low,$wontfix,$fixed_total,$fixed_critical,$fixed_high,$fixed_medium,$fixed_low,$size_mb,$created_date"

  # Output
  if [[ -n "$OUTPUT_FILE" ]]; then
    echo "$csv_row" >> "$OUTPUT_FILE"
  else
    echo "$csv_row"
  fi
done

echo "Scan complete!" >&2
if [[ -n "$OUTPUT_FILE" ]]; then
  echo "Results written to: $OUTPUT_FILE" >&2
fi
