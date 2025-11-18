# Customer CVE Analysis Workflow Guide

## Overview

This guide shows you how to take a customer's current container images and generate a comprehensive CVE analysis showing:
- **Current State:** Chainguard vs upstream CVE comparison
- **Historical Trends:** How CVEs have changed over time (6mo ago, 1yr ago)
- **Value Demonstration:** Quantified security improvements

## Quick Start (5 Minutes)

### Step 1: Get Customer's Image List

Ask the customer for their current production images. Save to a text file:

```bash
cat > customer-images.txt <<EOF
python:3.11
node:20
nginx:latest
postgres:15
redis:7
mcr.microsoft.com/dotnet/runtime:8.0
EOF
```

### Step 2: Run Analysis

**Option A: Automatic Mapping (recommended for first-time use)**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --customer="ACME Corp" \
  --input=customer-images.txt \
  --output-dir=./reports/acme
```

**Option B: Manual Mappings (faster, more control)**
```bash
# First, create a CSV with your mappings
cat > customer-mappings.csv <<EOF
upstream_image,chainguard_image
python:3.11,cgr.dev/chainguard/python:latest
node:20,cgr.dev/chainguard/node:latest
nginx:latest,cgr.dev/chainguard/nginx:latest
EOF

# Then run with manual mappings
./scripts/workflows/run-customer-analysis.sh \
  --customer="ACME Corp" \
  --manual-mappings=customer-mappings.csv \
  --output-dir=./reports/acme
```

**Option C: Fast Parallel Processing (recommended for 5+ images)**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --customer="ACME Corp" \
  --input=customer-images.txt \
  --output-dir=./reports/acme \
  --workers=10 \
  --verbose
```

### Step 3: View Results

```bash
# View scan results
cat ./reports/acme/acme_corp_*_merged.csv | column -t -s,

# View summary
cat ./reports/acme/acme_corp_*_summary.txt
```

**Done!** You now have a complete CVE analysis for the customer.

---

## Detailed Workflow

### What the Analysis Does

The workflow automatically:

1. **Maps Images** - Finds Chainguard equivalent for each upstream image (automatic or manual)
2. **Resolves Historical Versions** - Finds what versions existed 6mo and 1yr ago (now with parallel processing!)
3. **Scans Everything** - Scans all versions (current, 6mo, 1yr) for both upstream and Chainguard
4. **Generates Reports** - Creates CSV with all results for easy analysis

### Performance Options

**NEW: Parallelization Support**
- Use `--workers=N` to process multiple images simultaneously
- Default: 5 workers (processes 5 images at once)
- Recommended: 10 workers for large image lists (10+ images)
- Speedup: ~5-10x faster than sequential processing
- Example: `--workers=10` can reduce a 10-minute job to ~1-2 minutes

**NEW: Verbose Logging**
- Use `--verbose` to see detailed progress and timing information
- Shows which image is being processed and how long each takes
- Helpful for understanding bottlenecks and rate limiting issues
- Example output:
  ```
  [1/10] Processing: python:3.11
    → Upstream: python:3.11
    ✓ Resolved python (docker) in 12.3s
  [1/10] ✓ Completed in 12.3s
  ```

### Input Format

**Option 1: Simple text file, one image per line (for automatic mapping):**

```
# Customer: ACME Corp
# Production Images

# Languages
python:3.11
node:20
ruby:3.2

# Web Servers
nginx:latest

# Databases
postgres:15
redis:7

# .NET (Microsoft)
mcr.microsoft.com/dotnet/runtime:8.0

# Java
openjdk:17
```

**Option 2: Manual mappings CSV (for explicit control):**

Create a CSV file with two columns: `upstream_image,chainguard_image`

```csv
upstream_image,chainguard_image
python:3.11,cgr.dev/chainguard/python:latest
node:20,cgr.dev/chainguard/node:latest
nginx:latest,cgr.dev/chainguard/nginx:latest
postgres:15,cgr.dev/chainguard/postgres:latest
redis:7,cgr.dev/chainguard/redis:latest
mcr.microsoft.com/dotnet/runtime:8.0,cgr.dev/chainguard/dotnet-runtime:latest
```

**Benefits of Manual Mappings:**
- ✅ Explicit control over which Chainguard image to use
- ✅ Skip automatic mapping lookup (faster)
- ✅ Use specific Chainguard tags instead of "latest"
- ✅ Works for images not in the automatic mapping database

**Supported Registries:**
- Docker Hub: `python:3.11` or `docker.io/python:3.11`
- Microsoft: `mcr.microsoft.com/dotnet/runtime:8.0`
- Quay: `quay.io/image:tag`
- Google: `gcr.io/image:tag`
- Custom registries: Any OCI-compliant registry

### Output Files

After running the analysis, you'll get:

```
reports/acme/
├── acme_corp_20251118_123456_mappings.yaml          # Image mappings
├── acme_corp_20251118_123456_historical.yaml        # Historical versions
├── acme_corp_20251118_123456_scan_list.txt          # Generated scan list
├── acme_corp_20251118_123456_merged.csv             # ⭐ MAIN RESULTS
├── acme_corp_20251118_123456_summary.txt            # Aggregate statistics
└── acme_corp_20251118_123456_analysis_summary.txt   # Final summary
```

---

## Understanding the Results

### Main Results CSV

The merged CSV contains all scan results:

```csv
scan_date,image_name,image_tag,image_type,scanner,total,critical,high,medium,low,...
2025-11-18,python,3.11.10,upstream,grype,127,12,35,45,35,...
2025-11-18,cgr.dev/chainguard/python,latest,chainguard,grype,5,0,1,2,2,...
2025-11-18,python,3.11.7,upstream,grype,142,15,38,48,41,...
2025-11-18,cgr.dev/chainguard/python,3.11.7,chainguard,grype,6,0,1,2,3,...
...
```

**Key Columns:**
- `image_name` - Image identifier
- `image_tag` - Specific version scanned
- `image_type` - "upstream" or "chainguard"
- `scanner` - Which scanner (grype, trivy, prisma)
- `total` - Total CVEs found
- `critical`, `high`, `medium`, `low` - CVEs by severity

### Creating Comparisons

**Example: Python 3.11 Current State**

```bash
# Filter for Python current versions only
grep "python.*latest\|python.*3.11.10" acme_corp_*_merged.csv

# Result:
python,3.11.10,upstream,grype,127,12,35,45,35
cgr.dev/chainguard/python,latest,chainguard,grype,5,0,1,2,2

# Analysis:
# Upstream: 127 CVEs (12 critical, 35 high)
# Chainguard: 5 CVEs (0 critical, 1 high)
# Reduction: 122 CVEs (96% reduction!)
# Critical eliminated: 12 → 0 (100%)
```

**Example: Historical Trend for Python**

```bash
# Filter for Python upstream across time periods
grep "python.*upstream" acme_corp_*_merged.csv

# Result shows:
# 1 year ago: 156 CVEs
# 6 months ago: 142 CVEs
# Current: 127 CVEs
#
# Trend: Improving (156 → 127), but still high
# With Chainguard: 5 CVEs (97% reduction from current upstream)
```

---

## Analyzing in Excel/Google Sheets

### Step 1: Import CSV

1. Open Excel/Google Sheets
2. File → Import → Upload the merged CSV
3. Choose "Comma" as delimiter

### Step 2: Create Pivot Table

**For Current State Comparison:**

- **Rows:** `image_name`
- **Columns:** `image_type` (upstream, chainguard)
- **Values:** Sum of `critical`, `high`, `medium`, `low`

**Result:**
```
Image        | Upstream (total) | Chainguard (total) | Reduction
-------------|------------------|--------------------|-----------
python       | 127              | 5                  | 122 (96%)
node         | 89               | 3                  | 86  (97%)
nginx        | 45               | 2                  | 43  (96%)
postgres     | 67               | 4                  | 63  (94%)
redis        | 23               | 0                  | 23  (100%)
```

### Step 3: Create Charts

**Recommended Charts:**
1. **Comparison Bar Chart** - Upstream vs Chainguard by image
2. **Trend Line Chart** - CVEs over time (1yr ago → 6mo → current)
3. **Severity Breakdown** - Stacked bar showing critical/high/medium/low
4. **Total Savings** - Big number: "370 fewer CVEs with Chainguard"

---

## Advanced Analysis with Python

```python
import pandas as pd

# Load results
df = pd.read_csv('reports/acme/acme_corp_*_merged.csv')

# 1. Current state comparison
current = df[df['image_tag'].str.contains('latest|current', na=False)]
comparison = current.groupby(['image_name', 'image_type'])[
    ['total', 'critical', 'high', 'medium', 'low']
].sum()

print("Current State Comparison:")
print(comparison)

# 2. Calculate savings
upstream_total = current[current['image_type']=='upstream']['total'].sum()
cg_total = current[current['image_type']=='chainguard']['total'].sum()
savings = upstream_total - cg_total
savings_pct = (savings / upstream_total) * 100

print(f"\nTotal CVE Reduction: {savings} ({savings_pct:.1f}%)")

# 3. Critical CVEs eliminated
upstream_crit = current[current['image_type']=='upstream']['critical'].sum()
cg_crit = current[current['image_type']=='chainguard']['critical'].sum()

print(f"Critical CVEs: {upstream_crit} → {cg_crit}")

# 4. Historical trend
# Group by time period for upstream
upstream_trend = df[df['image_type']=='upstream'].groupby('image_tag')['total'].sum()
print("\nUpstream CVE Trend:")
print(upstream_trend.sort_index())
```

---

## Creating Customer Presentations

### Executive Summary Template

```
ACME Corp - Container Security Analysis
Chainguard vs Upstream Images
========================================

CURRENT PRODUCTION STATE
Total Images Analyzed: 7
Total Vulnerabilities (Upstream): 385
Total Vulnerabilities (Chainguard): 15

🎯 CVE REDUCTION: 370 (96%)

Critical Severity:
  Upstream: 45
  Chainguard: 0
  ✅ Eliminated: 45 critical CVEs (100%)

High Severity:
  Upstream: 123
  Chainguard: 2
  ✅ Reduction: 121 high CVEs (98%)

HISTORICAL TREND
================
1 Year Ago → Current (Upstream):
  Average CVEs: 156 → 127 (18% improvement)
  Still contains 127 vulnerabilities

With Chainguard (Current):
  Only 5 vulnerabilities
  97% fewer than current upstream
  99% fewer than upstream 1yr ago

RECOMMENDATION
==============
Immediate migration to Chainguard images will:
- Eliminate 370 CVEs (96% reduction)
- Remove ALL critical vulnerabilities
- Reduce attack surface significantly
- Improve compliance posture
```

### Key Talking Points

1. **Quantified Risk Reduction**
   - "You currently have 385 CVEs across your container images"
   - "With Chainguard, this drops to 15 - a 96% reduction"

2. **Critical Elimination**
   - "All 45 critical vulnerabilities eliminated"
   - "98% of high-severity issues resolved"

3. **Trend Analysis**
   - "Even though upstream is improving, you still have 127 CVEs"
   - "Chainguard has consistently had <10 CVEs over the past year"

4. **Per-Image Value**
   - "Python: 127 → 5 CVEs (96% reduction)"
   - "Node: 89 → 3 CVEs (97% reduction)"
   - "Redis: 23 → 0 CVEs (100% reduction)"

---

## Troubleshooting

### Issue: Image Not Found in Mappings

**Problem:** "No mapping found for `custom-image:latest`"

**Solution:** Add to `config/chainguard-mappings.yaml`:
```yaml
image_mappings:
  custom-image: cgr.dev/chainguard/equivalent-image
```

Or note in customer report: "Custom image - no Chainguard equivalent available"

### Issue: Historical Version Not Found

**Problem:** "Historical version not found for 6mo/1yr ago"

**Solution:** This can happen if:
- Image is newer than the time period (e.g., released 3mo ago)
- Registry doesn't provide creation dates
- Tag naming doesn't follow semver

**Workaround:** Use available versions or note in report

### Issue: Rate Limiting

**Problem:** "Too many API requests to Docker Hub" or "429 Client Error: Too Many Requests"

**Solutions:**

1. **Increase rate limit delay:**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --rate-limit=2.0 \  # Slow down to 2 seconds between requests
  ...
```

2. **Reduce parallelization:**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --workers=2 \  # Use fewer workers to reduce concurrent requests
  ...
```

3. **Authenticate to Docker Hub** (increases rate limit from 100 to 200 requests/6hrs):
```bash
docker login
# Then re-run analysis
```

4. **Use manual mappings** (skips registry lookups entirely):
```bash
# Create CSV with mappings, then:
./scripts/workflows/run-customer-analysis.sh \
  --manual-mappings=mappings.csv \
  ...
```

**Note:** Some rate limit warnings are normal and don't prevent successful completion. The crawler will retry and continue.

### Issue: Scan Takes Too Long

**Problem:** "Scanning 50+ images takes hours"

**Solutions:**

1. **Use parallelization** (NEW - recommended!):
```bash
./scripts/workflows/run-customer-analysis.sh \
  --workers=10 \  # Process 10 images at once (5-10x faster!)
  --verbose \     # See progress
  ...
```

2. **Use manual mappings** (skips automatic lookup):
```bash
./scripts/workflows/run-customer-analysis.sh \
  --manual-mappings=mappings.csv \  # Skip image mapping lookup
  --workers=10 \
  ...
```

3. **Start with a subset:**
```bash
# Create priority-images.txt with critical images only
python:3.11
node:20
nginx:latest

# Run analysis on subset first
./scripts/workflows/run-customer-analysis.sh --input=priority-images.txt ...

# Then expand to full image list
```

**Performance Tips:**
- Historical resolution is the slowest step (fetches tags from registries)
- Parallelization (--workers=10) provides 5-10x speedup
- Manual mappings skip the automatic mapping lookup
- Verbose logging (--verbose) shows which images are taking longest

---

## Command Reference

### Full Analysis (Recommended)

**Automatic Mapping:**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --customer="Customer Name" \
  --input=customer-images.txt \
  --output-dir=./reports/customer \
  --scanners=grype,trivy
```

**Manual Mappings with Parallelization:**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --customer="Customer Name" \
  --manual-mappings=mappings.csv \
  --output-dir=./reports/customer \
  --workers=10 \
  --verbose \
  --scanners=grype,trivy
```

**All Available Options:**
```bash
./scripts/workflows/run-customer-analysis.sh \
  --customer="Customer Name"              # Required: Customer name
  --input=images.txt                       # Option 1: Input file for automatic mapping
  --manual-mappings=mappings.csv          # Option 2: CSV with manual mappings
  --output-dir=./reports/customer         # Required: Output directory
  --workers=10                             # Optional: Parallel workers (default: 5)
  --verbose                                # Optional: Detailed logging
  --scanners=grype,trivy                  # Optional: Scanners to use (default: grype)
  --rate-limit=1.0                        # Optional: API rate limit delay (default: 1.0s)
  --skip-mapping                          # Optional: Skip mapping step
  --skip-historical                       # Optional: Skip historical resolution
  --skip-scan                             # Optional: Skip scanning
  --skip-report                           # Optional: Skip report generation
```

### Individual Steps (Advanced)

```bash
# Step 1: Map images only
python scripts/mapping/map-to-chainguard.py \
  --input=customer-images.txt \
  --output=mappings.yaml

# Step 2: Resolve historical versions
python scripts/workflows/resolve-historical-versions.py \
  --mappings=mappings.yaml \
  --output=historical.yaml

# Step 3: Generate scan list
python scripts/workflows/generate-scan-list.py \
  --input=historical.yaml \
  --output=scan-list.txt

# Step 4: Run scans
./scripts/orchestrator/scan-all.sh \
  --input=scan-list.txt \
  --output-dir=./results
```

### Skip Steps (Use Cached Data)

```bash
# Skip mapping (reuse existing mappings.yaml)
./scripts/workflows/run-customer-analysis.sh \
  --skip-mapping \
  ...

# Skip historical resolution (reuse existing historical.yaml)
./scripts/workflows/run-customer-analysis.sh \
  --skip-historical \
  ...

# Skip scanning (reuse existing scan results)
./scripts/workflows/run-customer-analysis.sh \
  --skip-scan \
  ...
```

---

## Next Steps

After generating the analysis:

1. **Review Results** - Check the merged CSV for accuracy
2. **Create Visualizations** - Import to Excel/Sheets, make charts
3. **Draft Executive Summary** - Use template above
4. **Schedule Customer Call** - Present findings
5. **Follow Up** - Share CSV and charts via email

For questions or issues, check:
- `QUICKSTART.md` - Quick reference guide
- `README_IMPLEMENTATION.md` - Technical details
- `TEST_REPORT.md` - Known issues and limitations
