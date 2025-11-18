#!/bin/bash

# CVE Scanner Dashboard - Prisma Cloud Scanner
# Adapted from cookbook/scripts/scans/scan-array-prisma.sh
#
# Usage:
#   ./scan-prisma.sh [--input=file.txt] [--output=results.csv]
#
# Input format (text file, one image per line):
#   cgr.dev/chainguard/python:latest,chainguard
#   python:3.11,upstream
#   mcr.microsoft.com/dotnet/runtime:8.0,upstream
#
# Format: image_ref,image_type
# image_type: "chainguard" or "upstream"
#
# Requires:
#   - twistcli (Prisma Cloud CLI)
#   - $PRISMATOKEN environment variable
#   - $PRISMA_ADDRESS environment variable (optional, has default)

set -euo pipefail

# Ensure standard tools are in PATH
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Default values
INPUT_FILE=""
OUTPUT_FILE=""
SCAN_DATE=$(date +%Y-%m-%d)
PRISMA_ADDRESS="${PRISMA_ADDRESS:-https://us-east1.cloud.twistlock.com/us-1-113031256}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --input=*)
      INPUT_FILE="${1#*=}"
      ;;
    --output=*)
      OUTPUT_FILE="${1#*=}"
      ;;
    --address=*)
      PRISMA_ADDRESS="${1#*=}"
      ;;
    -h|--help)
      echo "Usage: $0 [--input=file.txt] [--output=results.csv] [--address=URL]"
      echo ""
      echo "Options:"
      echo "  --input=FILE      Input file with image list (or use stdin)"
      echo "  --output=FILE     Output CSV file (or use stdout)"
      echo "  --address=URL     Prisma Cloud address (default: $PRISMA_ADDRESS)"
      echo ""
      echo "Environment variables:"
      echo "  PRISMATOKEN       Prisma Cloud API token (required)"
      echo "  PRISMA_ADDRESS    Prisma Cloud address (optional)"
      echo ""
      echo "Input format (CSV): image_ref,image_type"
      echo "  image_type: 'chainguard' or 'upstream'"
      echo ""
      echo "Example:"
      echo "  export PRISMATOKEN=your_token_here"
      echo "  echo 'cgr.dev/chainguard/python:latest,chainguard' | $0"
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

# Check for required tools and credentials
if ! command -v twistcli &> /dev/null; then
  echo "Error: twistcli is not installed or not in PATH" >&2
  echo "Install from: https://docs.paloaltonetworks.com/prisma/prisma-cloud/prisma-cloud-admin-compute/tools/twistcli" >&2
  exit 1
fi

if [[ -z "${PRISMATOKEN:-}" ]]; then
  echo "Error: PRISMATOKEN environment variable is not set" >&2
  echo "Get token from: Prisma Cloud Console > Settings > Access Control > Access Keys" >&2
  exit 1
fi

if ! command -v crane &> /dev/null; then
  echo "Warning: crane is not installed, created_date will be set to 'unknown'" >&2
  CRANE_AVAILABLE=false
else
  CRANE_AVAILABLE=true
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

echo "Starting Prisma Cloud scan for ${#images[@]} images..." >&2

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

# CSV header (unified format)
csv_header="scan_date,image_name,image_tag,image_type,scanner,total,critical,high,medium,low,wontfix,fixed_total,fixed_critical,fixed_high,fixed_medium,fixed_low,size_mb,created_date"

# Output header
if [[ -n "$OUTPUT_FILE" ]]; then
  echo "$csv_header" > "$OUTPUT_FILE"
else
  echo "$csv_header"
fi

# Create temp file for scan results
temp_scan_file=$(mktemp)
trap "rm -f $temp_scan_file" EXIT

# Scan images
for image in "${images[@]}"; do
  echo "  Scanning $image with Prisma Cloud..." >&2

  # Get image metadata
  image_type="${image_types[$image]}"
  size=$(docker inspect "$image" | jq -r '.[0].Size // 0')
  size_mb=$(echo "scale=2; $size / 1024 / 1024" | bc)

  # Try to get created date
  if [[ "$CRANE_AVAILABLE" == "true" ]]; then
    created_date=$(crane config "$image" 2>/dev/null | jq -r '.created // "unknown"' | cut -d'T' -f1 || echo "unknown")
  else
    created_date=$(docker inspect "$image" | jq -r '.[0].Created // "unknown"' | cut -d'T' -f1)
  fi

  # Parse image name and tag
  if [[ "$image" =~ ^(.+):([^:]+)$ ]]; then
    image_name="${BASH_REMATCH[1]}"
    image_tag="${BASH_REMATCH[2]}"
  else
    image_name="$image"
    image_tag="unknown"
  fi

  # Run Prisma scan
  : > "$temp_scan_file"  # Clear temp file

  if twistcli images scan --address="$PRISMA_ADDRESS" --token="$PRISMATOKEN" --output-file="$temp_scan_file" "$image" >/dev/null 2>&1; then
    # Parse scan results
    scan_output=$(jq -r '
      [.results[] | (
        (.vulnerabilities // []) as $vulns
        | reduce $vulns[].severity? as $s (
            {critical:0,high:0,medium:0,low:0,other:0};
            .[
              (if $s=="critical" then "critical"
               elif $s=="high" then "high"
               elif $s=="medium" then "medium"
               elif $s=="low" then "low"
               else "other" end)
            ] += 1
          )
        | .total = ($vulns | length)
        | [.total, .critical, .high, .medium, .low, .other]
        | @csv
      )]
      | .[]
    ' "$temp_scan_file" 2>/dev/null || echo "0,0,0,0,0,0")

    # Parse CSV output
    IFS=',' read -r total critical high medium low other <<< "$scan_output"

    # Prisma doesn't provide wont-fix or fixed data in the same format
    wontfix=0
    fixed_total=0
    fixed_critical=0
    fixed_high=0
    fixed_medium=0
    fixed_low=0
  else
    echo "Warning: Prisma scan failed for $image, setting all counts to 0" >&2
    total=0
    critical=0
    high=0
    medium=0
    low=0
    other=0
    wontfix=0
    fixed_total=0
    fixed_critical=0
    fixed_high=0
    fixed_medium=0
    fixed_low=0
  fi

  # Build CSV row
  csv_row="$SCAN_DATE,$image_name,$image_tag,$image_type,prisma,$total,$critical,$high,$medium,$low,$wontfix,$fixed_total,$fixed_critical,$fixed_high,$fixed_medium,$fixed_low,$size_mb,$created_date"

  # Output
  if [[ -n "$OUTPUT_FILE" ]]; then
    echo "$csv_row" >> "$OUTPUT_FILE"
  else
    echo "$csv_row"
  fi
done

echo "Prisma scan complete!" >&2
if [[ -n "$OUTPUT_FILE" ]]; then
  echo "Results written to: $OUTPUT_FILE" >&2
fi
