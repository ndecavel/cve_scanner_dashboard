# CVE Scanner Dashboard - Quick Start Guide

## 🎯 What You Have Now

A production-ready foundation for scanning and comparing Chainguard vs. upstream container images across multiple CVE scanners with historical tracking capabilities.

## ✅ Completed Components

1. **Multi-Scanner Scripts** - Grype, Trivy, and Prisma Cloud with unified output
2. **Registry Crawler** - Python module for Docker Hub and Microsoft Container Registry
3. **Historical Tag Resolver** - Find "latest" images from 6 months ago, 1 year ago, etc.
4. **Orchestration** - Run all scanners at once and merge results
5. **Configuration System** - YAML-based image comparison definitions
6. **Database Schema** - Complete PostgreSQL schema design

## 🚀 Getting Started in 5 Minutes

### Step 1: Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install scanners (choose what you have licenses for)
# Grype (free)
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

# Trivy (free)
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Prisma Cloud (enterprise - optional)
# Download twistcli from Prisma Cloud console
```

### Step 2: Configure Your Comparisons

Edit `config/image-comparisons.yaml` to define which images you want to compare:

```yaml
comparisons:
  - name: "Python 3.11"
    chainguard:
      registry: "cgr.dev/chainguard"
      image: "python"
      tag: "latest"
    upstream:
      registry: "docker"
      image: "python"
      tag: "3.11"
```

### Step 3: Run Your First Scan

```bash
# Use the example image list or create your own
./scripts/orchestrator/scan-all.sh \
  --input=config/example-images.txt \
  --output-dir=./data/scans \
  --scanners=grype,trivy
```

### Step 4: View Results

```bash
# Check the latest scan results
ls -lh data/scans/

# View the merged CSV
cat data/scans/scan_*_merged.csv | column -t -s,

# View summary
cat data/scans/scan_*_summary.txt
```

## 📊 Example Output

After running a scan, you'll see:

```
CVE Scanner Dashboard - Scan Summary
====================================

Images scanned: 6
Successful scans: 2 (grype, trivy)

Aggregate Statistics:
Total vulnerabilities: 342
  Critical: 15
  High: 87
  Medium: 145
  Low: 95

By Image Type:
  chainguard: 18 total (3.0 avg across 6 scans)
  upstream: 324 total (54.0 avg across 6 scans)

💡 Chainguard images show 94.5% fewer CVEs!
```

## 🔍 Finding Historical Images

### Example 1: Find what Python 3.11 tags existed 6 months ago

```bash
python -m crawler.cli find-historical python \
  --registry=docker \
  --pattern="3\.11\.*" \
  --only-semver
```

**Output:**
```
Period               Tag                            Created
--------------------------------------------------------------------------------
current              3.11.10                        2025-11-15T00:00:00
6_months_ago         3.11.7                         2025-05-10T00:00:00
1_year_ago           3.11.4                         2024-11-05T00:00:00
```

### Example 2: List all available tags

```bash
python -m crawler.cli list-tags python \
  --registry=docker \
  --filter \
  --only-semver \
  --sort-by-date \
  --output-format=csv > python-tags.csv
```

### Example 3: Generate image list from config

```bash
python -m crawler.cli generate-image-list \
  --config=config/image-comparisons.yaml > images-to-scan.txt

# Then scan them
./scripts/orchestrator/scan-all.sh --input=images-to-scan.txt
```

## 📈 Typical Workflow

### For a Customer Report

```bash
# 1. Define comparisons (one-time setup)
vim config/image-comparisons.yaml

# 2. Find historical versions
python -m crawler.cli find-historical python --registry=docker --pattern="3\.11\.*"
python -m crawler.cli find-historical dotnet/runtime --registry=mcr --pattern="8\.0\.*"

# 3. Create image list with current + historical versions
cat > customer-images.txt <<EOF
# Current
cgr.dev/chainguard/python:latest,chainguard
python:3.11,upstream

# 6 months ago
cgr.dev/chainguard/python:3.11.7,chainguard
python:3.11.7,upstream

# 1 year ago
cgr.dev/chainguard/python:3.11.4,chainguard
python:3.11.4,upstream
EOF

# 4. Scan all images
./scripts/orchestrator/scan-all.sh \
  --input=customer-images.txt \
  --output-dir=./data/scans/customer-xyz \
  --run-id=customer_xyz_$(date +%Y%m%d)

# 5. Review results
cat data/scans/customer-xyz/customer_xyz_*_summary.txt

# 6. Share results (CSV can be imported into Excel/Google Sheets)
cp data/scans/customer-xyz/customer_xyz_*_merged.csv ~/Desktop/cve-report.csv
```

## 🔧 Advanced Usage

### Scan Only Specific Scanners

```bash
# Only Grype
./scripts/orchestrator/scan-all.sh --input=images.txt --scanners=grype

# Grype + Trivy (skip Prisma)
./scripts/orchestrator/scan-all.sh --input=images.txt --scanners=grype,trivy
```

### Run Individual Scanners

```bash
# Grype only
./scripts/scanners/scan-grype-or-trivy.sh \
  --scanner=grype \
  --input=images.txt \
  --output=grype-results.csv

# Trivy only
./scripts/scanners/scan-grype-or-trivy.sh \
  --scanner=trivy \
  --input=images.txt \
  --output=trivy-results.csv

# Prisma only (requires PRISMATOKEN env var)
export PRISMATOKEN="your_token"
./scripts/scanners/scan-prisma.sh \
  --input=images.txt \
  --output=prisma-results.csv
```

### Customize Time Periods

```bash
# Custom periods in JSON format
python -m crawler.cli find-historical python \
  --registry=docker \
  --periods='[{"name":"current","offset_days":0},{"name":"3mo","offset_days":90},{"name":"6mo","offset_days":180}]'
```

## 📝 Understanding the CSV Output

The unified CSV format has these columns:

| Column | Description | Example |
|--------|-------------|---------|
| `scan_date` | When scan was run | `2025-11-18` |
| `image_name` | Image without tag | `cgr.dev/chainguard/python` |
| `image_tag` | Image tag | `latest` |
| `image_type` | Type of image | `chainguard` or `upstream` |
| `scanner` | Scanner used | `grype`, `trivy`, or `prisma` |
| `total` | Total CVEs | `127` |
| `critical` | Critical CVEs | `12` |
| `high` | High CVEs | `35` |
| `medium` | Medium CVEs | `45` |
| `low` | Low CVEs | `35` |
| `wontfix` | Won't fix CVEs | `15` |
| `fixed_*` | CVEs with fixes available | (Grype only) |
| `size_mb` | Image size in MB | `180.5` |
| `created_date` | Image creation date | `2025-11-10` |

## 🎨 Visualizing Results

### Excel/Google Sheets

1. Import the CSV: `data/scans/scan_*_merged.csv`
2. Create pivot table with:
   - Rows: `image_name`, `image_type`
   - Values: Sum of `critical`, `high`, `medium`, `low`
3. Add charts to visualize Chainguard vs upstream

### Python/Pandas

```python
import pandas as pd

# Load results
df = pd.read_csv('data/scans/scan_TIMESTAMP_merged.csv')

# Group by image type
summary = df.groupby('image_type')[['critical', 'high', 'medium', 'low']].sum()
print(summary)

# Calculate savings
cg = df[df['image_type'] == 'chainguard']['critical'].sum()
up = df[df['image_type'] == 'upstream']['critical'].sum()
print(f"Critical CVE reduction: {up - cg} ({100*(up-cg)/up:.1f}%)")
```

## ❓ Troubleshooting

### "Error: grype is not installed"
```bash
# Install Grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
```

### "Error: Failed to pull image"
```bash
# Make sure you're authenticated to private registries
docker login cgr.dev
docker login
```

### "Warning: Prisma scan failed"
```bash
# Make sure PRISMATOKEN is set
export PRISMATOKEN="your_token_here"

# Or skip Prisma
./scripts/orchestrator/scan-all.sh --scanners=grype,trivy
```

### "No tags found for repository"
```bash
# Docker Hub has rate limits - try with authentication
docker login

# Or increase rate limit delay
python -m crawler.cli list-tags python --rate-limit=2.0
```

## 📚 Next Steps

1. **Set up database** (see `docs/DATABASE_SCHEMA.md`)
   - Store scan results for historical queries
   - Build comparison views

2. **Build backend API** (Phase 4)
   - REST API for querying scan data
   - Report generation endpoints

3. **Create dashboard UI** (Phase 5)
   - Web interface for visualizations
   - Interactive comparisons

4. **Automate scanning** (Phase 6)
   - Scheduled scans (daily/weekly)
   - Automatic historical tracking
   - Email reports

## 🤝 Getting Help

- **Project structure**: `docs/PROJECT_STRUCTURE.md`
- **Implementation details**: `README_IMPLEMENTATION.md`
- **Database design**: `docs/DATABASE_SCHEMA.md`
- **Original requirements**: `README.md`
- **Cookbook reference**: `cookbook/` directory

## 🎉 Success Criteria Checklist

- [x] Scan Chainguard images with Grype/Trivy/Prisma
- [x] Scan upstream images with same scanners
- [x] Get CVE counts by severity (total/critical/high/medium/low)
- [x] Compare Chainguard vs upstream
- [x] Find historical image versions (6mo, 1yr ago)
- [x] Generate exportable reports (CSV)
- [x] Demonstrate value to customers

**You're ready to start scanning and generating customer reports!** 🚀
