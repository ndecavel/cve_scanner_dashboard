# CVE Scanner Dashboard - Project Structure

## Directory Layout

```
cve_scanner_dashboard/
├── scripts/
│   ├── scanners/          # Adapted scanner scripts (grype, trivy, prisma)
│   └── orchestrator/      # Orchestration scripts to run multiple scanners
├── crawler/               # Registry crawler for historical image tracking
├── backend/               # Dashboard backend API
├── frontend/              # Dashboard frontend UI
│   ├── src/
│   └── public/
├── data/
│   ├── scans/            # Scan results (JSON/CSV)
│   ├── cache/            # Cached registry data
│   └── reports/          # Generated reports
├── config/               # Configuration files
├── docs/                 # Documentation
└── cookbook/             # Original Chainguard cookbook scripts (reference)
```

## Key Components

### 1. Scanner Scripts (`scripts/scanners/`)
Adapted versions of cookbook scripts that:
- Accept image lists from external sources (file/stdin)
- Support both Chainguard and upstream images
- Output unified CSV format with metadata
- Handle errors gracefully

### 2. Orchestrator (`scripts/orchestrator/`)
Coordinates multiple scanners:
- Runs Grype, Trivy, and Prisma on same image set
- Merges results into unified format
- Handles scanner availability (e.g., Prisma may not be installed)

### 3. Registry Crawler (`crawler/`)
Python-based crawler for:
- Docker Hub API
- Microsoft Container Registry (MCR)
- Quay.io
- Google Container Registry (GCR)
- Chainguard Registry
- Historical tag resolution (find "latest" at specific dates)

### 4. Backend API (`backend/`)
REST API for:
- Serving scan results
- Comparison data (Chainguard vs upstream)
- Historical trend data
- Report generation

### 5. Frontend Dashboard (`frontend/`)
Web UI for:
- Side-by-side comparisons
- Differential/savings view
- Historical trends
- Exportable reports

## Data Flow

```
Customer Image List → Registry Crawler → Historical Tags
                                              ↓
                                         Image List
                                              ↓
                              ┌───────────────┴───────────────┐
                              ↓                               ↓
                    Chainguard Images                 Upstream Images
                              ↓                               ↓
                    Scanner Orchestrator              Scanner Orchestrator
                    (Grype/Trivy/Prisma)             (Grype/Trivy/Prisma)
                              ↓                               ↓
                         Scan Results                    Scan Results
                              └───────────────┬───────────────┘
                                              ↓
                                          Database
                                              ↓
                                        Backend API
                                              ↓
                                      Dashboard Frontend
                                              ↓
                                     Customer Reports
```

## CSV Output Format

Unified format across all scanners:

```csv
scan_date,image_name,image_tag,image_type,scanner,total,critical,high,medium,low,wontfix,fixed_total,fixed_critical,fixed_high,fixed_medium,fixed_low,size_mb,created_date
2025-11-18,cgr.dev/chainguard/python,3.11,chainguard,grype,5,0,1,2,2,0,3,0,1,1,1,45.2,2025-11-15
2025-11-18,python,3.11,upstream,grype,127,12,35,45,35,15,45,5,15,15,10,180.5,2025-11-10
```

## Configuration Files

### `config/image-comparisons.yaml`
Defines which images to compare:

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

  - name: ".NET 8 Runtime"
    chainguard:
      registry: "cgr.dev/chainguard"
      image: "dotnet-runtime"
      tag: "8"
    upstream:
      registry: "mcr.microsoft.com"
      image: "dotnet/runtime"
      tag: "8.0"
```

### `config/scanners.yaml`
Scanner configuration:

```yaml
scanners:
  grype:
    enabled: true
    binary: "grype"
  trivy:
    enabled: true
    binary: "trivy"
  prisma:
    enabled: true
    binary: "twistcli"
    token_env: "PRISMATOKEN"
    address: "https://us-east1.cloud.twistlock.com/us-1-113031256"
```

### `config/registries.yaml`
Registry API configuration:

```yaml
registries:
  docker:
    api_base: "https://hub.docker.com/v2"
    rate_limit: true
  mcr:
    api_base: "https://mcr.microsoft.com/v2"
  quay:
    api_base: "https://quay.io/api/v1"
  chainguard:
    api_base: "cgr.dev"
    use_chainctl: true
```

## Development Phases

1. **Phase 1**: Adapt scanner scripts ← Current
2. **Phase 2**: Build registry crawler
3. **Phase 3**: Data pipeline & storage
4. **Phase 4**: Backend API
5. **Phase 5**: Frontend dashboard
6. **Phase 6**: Automation
