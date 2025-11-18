# CVE Scanner Dashboard

**Complete solution for analyzing customer container images and demonstrating Chainguard value**

## Overview

This project provides an automated workflow to analyze customer container images and generate comprehensive CVE comparisons showing the security value of using Chainguard images vs upstream images.

**What it does:**
- ✅ Scans customer images with multiple scanners (Grype, Trivy, Prisma Cloud)
- ✅ Automatically maps upstream images to Chainguard equivalents
- ✅ Resolves historical versions (6 months ago, 1 year ago) - **SOLVED!**
- ✅ Generates unified CSV reports for easy analysis
- ✅ Supports Docker Hub, Microsoft Container Registry, and other registries
- ✅ **NEW: Parallel processing for 5-10x faster execution**
- ✅ **NEW: Manual mapping support for explicit control**

## Quick Start

```bash
# 1. Create customer image list
cat > customer-images.txt <<EOF
python:3.11
node:20
nginx:latest
EOF

# 2. Run complete analysis
./scripts/workflows/run-customer-analysis.sh \
  --customer="Customer Name" \
  --input=customer-images.txt \
  --output-dir=./reports/customer \
  --workers=10 \
  --verbose

# 3. View results
cat ./reports/customer/*_merged.csv | column -t -s,
```

**Result:** Complete CVE analysis comparing Chainguard vs upstream for current, 6mo ago, and 1yr ago.

## Key Features

### 1. Historical Version Resolution ✅
**Problem:** Finding what image versions existed 6 months or 1 year ago across different registries.

**Solution:** Automated registry crawlers for Docker Hub and Microsoft Container Registry that:
- Fetch all available tags with creation timestamps
- Filter by semantic versioning
- Find closest versions to target dates (6mo/1yr ago)
- Support parallel processing for speed

### 2. Multi-Scanner Support ✅
- Grype (fast, accurate)
- Trivy (comprehensive)
- Prisma Cloud (enterprise)
- Unified CSV output across all scanners

### 3. Image Mapping ✅
**Automatic mapping:** Matches 40+ common upstream images to Chainguard equivalents
**Manual mapping:** CSV-based explicit control over image pairs

### 4. Performance Optimization 🆕
**Parallelization:** Process multiple images simultaneously (--workers=10)
- 5-10x speedup for large image lists
- Thread-safe with detailed progress logging

**Verbose logging:** See exactly what's happening and where time is spent

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- **[CUSTOMER_WORKFLOW_GUIDE.md](CUSTOMER_WORKFLOW_GUIDE.md)** - Complete customer analysis guide
- **[COMPLETE_SOLUTION_SUMMARY.md](COMPLETE_SOLUTION_SUMMARY.md)** - Full feature list and capabilities
- **[README_IMPLEMENTATION.md](README_IMPLEMENTATION.md)** - Technical implementation details
- **[TEST_REPORT.md](TEST_REPORT.md)** - Testing results and validation

## Example Output

```
Image        | Upstream CVEs | Chainguard CVEs | Reduction
-------------|---------------|-----------------|----------
Python 3.11  | 127           | 5               | 122 (96%)
Node 20      | 89            | 3               | 86  (97%)
Nginx        | 45            | 2               | 43  (96%)
TOTAL        | 261           | 10              | 251 (96%)
```

## New in Latest Version

**Performance Improvements:**
- ⚡ Parallel processing with `--workers=N` flag (5-10x faster!)
- 📊 Verbose logging with `--verbose` flag (see detailed progress)
- ⏱️ Timing information for each image

**Workflow Enhancements:**
- 📝 Manual mapping support via CSV (`--manual-mappings=file.csv`)
- 🎯 Explicit control over upstream → Chainguard pairs
- 🚀 Skip automatic mapping lookup for faster execution

**Example:**
```bash
# Fast parallel processing with manual mappings
./scripts/workflows/run-customer-analysis.sh \
  --customer="ACME Corp" \
  --manual-mappings=mappings.csv \
  --workers=10 \
  --verbose \
  --output-dir=./reports/acme
```

## Status

✅ **Production Ready** - All core features implemented and tested
- Multi-scanner support
- Registry crawling (Docker Hub, MCR)
- Historical tag resolution
- Customer workflow automation
- Parallel processing
- Manual mapping support

See [COMPLETE_SOLUTION_SUMMARY.md](COMPLETE_SOLUTION_SUMMARY.md) for full details.
