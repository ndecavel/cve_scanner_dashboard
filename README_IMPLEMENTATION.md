# CVE Scanner Dashboard - Implementation Guide

## Overview

This project provides a comprehensive solution for scanning container images (both Chainguard and upstream) with multiple CVE scanners (Grype, Trivy, Prisma Cloud) and tracking vulnerabilities over time.

## What's Been Implemented

### ✅ Phase 1: Scanner Scripts (COMPLETED)

**Adapted Cookbook Scripts:**
1. `scripts/scanners/scan-grype-or-trivy.sh` - Unified Grype/Trivy scanner
2. `scripts/scanners/scan-prisma.sh` - Prisma Cloud scanner
3. `scripts/orchestrator/scan-all.sh` - Multi-scanner orchestrator

**Features:**
- Accept external image lists (CSV format: `image_ref,image_type`)
- Unified CSV output format across all scanners
- Metadata tracking (scan date, image type, size, created date)
- Graceful error handling
- Summary reports

**Usage Example:**
```bash
# Create an image list
cat > images.txt <<EOF
cgr.dev/chainguard/python:latest,chainguard
python:3.11,upstream
EOF

# Run single scanner
./scripts/scanners/scan-grype-or-trivy.sh --scanner=grype --input=images.txt --output=results.csv

# Run all scanners
./scripts/orchestrator/scan-all.sh --input=images.txt --output-dir=./data/scans
```

### ✅ Phase 2: Registry Crawler (COMPLETED)

**Python Module:** `crawler/`

**Components:**
1. `base.py` - Base crawler class with tag filtering and sorting
2. `docker_hub.py` - Docker Hub API crawler
3. `mcr.py` - Microsoft Container Registry crawler
4. `resolver.py` - Historical tag resolution logic
5. `cli.py` - Command-line interface

**Features:**
- Multi-registry support (Docker Hub, MCR, extensible to others)
- Historical tag resolution (find "latest" at specific dates)
- Semantic versioning awareness
- Dev/preview tag filtering
- Tag metadata extraction (created date, digest, size)

**Usage Example:**
```bash
# Install dependencies
pip install -r requirements.txt

# List all tags for Python on Docker Hub
python -m crawler.cli list-tags python --registry=docker --filter --only-semver --sort-by-date

# Find historical tags
python -m crawler.cli find-historical python --registry=docker --pattern="3.11.*"

# Generate image list from config
python -m crawler.cli generate-image-list --config=config/image-comparisons.yaml > images.txt
```

### ✅ Configuration Files (COMPLETED)

1. **`config/image-comparisons.yaml`** - Defines Chainguard vs upstream comparisons
2. **`config/example-images.txt`** - Example image list for testing
3. **`requirements.txt`** - Python dependencies

## Quick Start

### Prerequisites

```bash
# Install container scanning tools
# Grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

# Trivy
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Prisma Cloud (twistcli)
# Download from: https://docs.paloaltonetworks.com/prisma/prisma-cloud/prisma-cloud-admin-compute/tools/twistcli

# Python dependencies
pip install -r requirements.txt

# Set environment variables (if using Prisma)
export PRISMATOKEN="your_token_here"
```

### Running a Scan

```bash
# 1. Use the example image list
cp config/example-images.txt my-images.txt

# 2. Run all scanners
./scripts/orchestrator/scan-all.sh \
  --input=my-images.txt \
  --output-dir=./data/scans \
  --scanners=grype,trivy,prisma

# 3. View results
ls -lh data/scans/
# Output files:
#   - scan_TIMESTAMP_grype.csv
#   - scan_TIMESTAMP_trivy.csv
#   - scan_TIMESTAMP_prisma.csv
#   - scan_TIMESTAMP_merged.csv (all scanners combined)
#   - scan_TIMESTAMP_summary.txt (aggregate stats)
```

### Finding Historical Images

```bash
# Find what Python 3.11 tags existed 6 months ago and 1 year ago
python -m crawler.cli find-historical python \
  --registry=docker \
  --pattern="3\.11\.*" \
  --only-semver \
  --exclude-dev

# Find historical .NET images from Microsoft
python -m crawler.cli find-historical dotnet/runtime \
  --registry=mcr \
  --pattern="8\.0\.*"
```

## CSV Output Format

All scanners output a unified CSV format:

```csv
scan_date,image_name,image_tag,image_type,scanner,total,critical,high,medium,low,wontfix,fixed_total,fixed_critical,fixed_high,fixed_medium,fixed_low,size_mb,created_date
2025-11-18,cgr.dev/chainguard/python,latest,chainguard,grype,5,0,1,2,2,0,3,0,1,1,1,45.2,2025-11-15
2025-11-18,python,3.11,upstream,grype,127,12,35,45,35,15,45,5,15,15,10,180.5,2025-11-10
```

**Fields:**
- `scan_date` - Date the scan was performed
- `image_name` - Image name (without tag)
- `image_tag` - Image tag
- `image_type` - "chainguard" or "upstream"
- `scanner` - Scanner used (grype, trivy, prisma)
- `total` - Total CVEs found
- `critical` - Critical severity CVEs
- `high` - High severity CVEs
- `medium` - Medium severity CVEs
- `low` - Low severity CVEs
- `wontfix` - CVEs marked as "won't fix"
- `fixed_*` - CVEs with fixes available (Grype only)
- `size_mb` - Image size in MB
- `created_date` - Image creation date

## Next Steps (Remaining Work)

### 🔄 Phase 3: Data Pipeline & Storage

**What needs to be built:**
1. Database schema for storing scan results
2. Data ingestion scripts (CSV → Database)
3. Deduplication and historical tracking
4. Scheduled scanning workflow

**Files to create:**
- `backend/database/schema.sql`
- `backend/scripts/ingest_scans.py`
- `backend/scripts/run_scheduled_scan.sh`

### 🔄 Phase 4: Backend API

**What needs to be built:**
1. REST API server (Flask/FastAPI)
2. Endpoints for:
   - List comparisons
   - Get comparison details
   - Get historical trends
   - Export reports

**Files to create:**
- `backend/api/app.py`
- `backend/api/routes/*.py`
- `backend/api/models/*.py`

### 🔄 Phase 5: Frontend Dashboard

**What needs to be built:**
1. Web UI with:
   - Side-by-side comparison view
   - Differential/savings view
   - Historical trend charts
   - Per-image drill-down
   - Export functionality

**Technology:** React + Chart.js/Recharts

**Files to create:**
- `frontend/src/App.js`
- `frontend/src/components/*.jsx`
- `frontend/src/services/api.js`

### 🔄 Phase 6: Automation

**What needs to be built:**
1. Scheduled scanning (cron jobs or similar)
2. Automated historical tracking
3. Alerting for new critical CVEs
4. Report generation and distribution

## Project Structure

```
cve_scanner_dashboard/
├── scripts/
│   ├── scanners/              # ✅ Adapted scanner scripts
│   │   ├── scan-grype-or-trivy.sh
│   │   └── scan-prisma.sh
│   └── orchestrator/          # ✅ Multi-scanner orchestrator
│       └── scan-all.sh
├── crawler/                   # ✅ Registry crawler (Python)
│   ├── __init__.py
│   ├── base.py
│   ├── docker_hub.py
│   ├── mcr.py
│   ├── resolver.py
│   └── cli.py
├── config/                    # ✅ Configuration files
│   ├── image-comparisons.yaml
│   └── example-images.txt
├── data/                      # Data storage
│   ├── scans/                 # Scan results (CSV)
│   ├── cache/                 # Cached registry data
│   └── reports/               # Generated reports
├── backend/                   # 🔄 To be implemented
│   ├── database/
│   ├── api/
│   └── scripts/
├── frontend/                  # 🔄 To be implemented
│   ├── src/
│   └── public/
├── docs/                      # ✅ Documentation
│   └── PROJECT_STRUCTURE.md
├── cookbook/                  # Reference: Original Chainguard scripts
├── requirements.txt           # ✅ Python dependencies
└── README.md                  # Project overview
```

## Cookbook Scripts Used

The following cookbook scripts were used as the foundation:

| Cookbook Script | Our Adapted Version | Status |
|----------------|---------------------|--------|
| `cookbook/scripts/scans/scan-array-grype-or-trivy.sh` | `scripts/scanners/scan-grype-or-trivy.sh` | ✅ Adapted |
| `cookbook/scripts/scans/scan-array-prisma.sh` | `scripts/scanners/scan-prisma.sh` | ✅ Adapted |
| `cookbook/scripts/registry/latest-tags-by-package/main.py` | `crawler/resolver.py` | ✅ Referenced |

**Key improvements in adapted versions:**
- Accept external input (no hardcoded image arrays)
- Unified CSV output format with metadata
- Better error handling
- Support for both Chainguard and upstream images
- Configurable via command-line arguments

## Key Achievements

1. **✅ Multi-scanner support** - Grype, Trivy, and Prisma Cloud all working with unified output
2. **✅ Unified data format** - Single CSV format across all scanners for easy comparison
3. **✅ Historical tracking capability** - Registry crawler can find images from 6mo/1yr ago
4. **✅ Multi-registry support** - Docker Hub and MCR crawlers implemented, extensible to others
5. **✅ Production-ready scripts** - Error handling, rate limiting, logging
6. **✅ Flexible configuration** - YAML-based comparison definitions

## Known Limitations & Future Improvements

1. **Historical tag resolution challenges:**
   - Not all registries provide creation timestamps
   - Some registries have rate limits (especially Docker Hub)
   - Manual verification may be needed for critical comparisons

2. **Scanner availability:**
   - Prisma Cloud requires enterprise license and token
   - Grype and Trivy are free but may have different CVE databases

3. **Performance:**
   - Scanning many images can be slow
   - Consider parallelization for production use
   - Caching of registry metadata recommended

4. **Missing features (to be implemented):**
   - Database storage and querying
   - Web dashboard UI
   - Automated scheduling
   - Report generation and sharing

## Contributing

To extend this project:

1. **Add new registry crawler:**
   - Inherit from `crawler/base.py:RegistryCrawler`
   - Implement `list_tags()` and `get_tag_metadata()`
   - Add to `crawler/__init__.py`

2. **Add new scanner:**
   - Follow pattern in `scripts/scanners/`
   - Ensure CSV output matches unified format
   - Update `scripts/orchestrator/scan-all.sh`

3. **Customize comparison config:**
   - Edit `config/image-comparisons.yaml`
   - Add your images and registries
   - Run `generate-image-list` to create scan input

## Support & Documentation

- Project structure: `docs/PROJECT_STRUCTURE.md`
- This guide: `README_IMPLEMENTATION.md`
- Original requirement: `README.md`
- Cookbook reference: `cookbook/` directory

## License

(Add appropriate license information)
