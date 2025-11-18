# CVE Scanner Dashboard - Database Schema Design

## Overview

This document defines the database schema for storing CVE scan results, image metadata, and historical comparisons.

## Database Choice

**Recommended:** PostgreSQL
- Good support for time-series data
- JSON column support for flexible metadata
- Strong aggregation capabilities
- Open source

**Alternative:** SQLite
- For MVP/single-user deployments
- No separate server required
- Good for prototyping

## Schema Design

### Table: `images`

Stores information about container images.

```sql
CREATE TABLE images (
    id SERIAL PRIMARY KEY,
    registry VARCHAR(255) NOT NULL,           -- e.g., 'docker', 'mcr', 'cgr.dev'
    namespace VARCHAR(255),                   -- e.g., 'library', 'chainguard'
    repository VARCHAR(255) NOT NULL,         -- e.g., 'python', 'dotnet/runtime'
    tag VARCHAR(255) NOT NULL,                -- e.g., '3.11', 'latest', '8.0'
    digest VARCHAR(255),                      -- Image digest (sha256:...)
    image_type VARCHAR(50) NOT NULL,          -- 'chainguard' or 'upstream'
    size_bytes BIGINT,                        -- Image size in bytes
    created_at TIMESTAMP,                     -- Image creation timestamp
    metadata JSONB,                           -- Additional metadata
    first_seen TIMESTAMP DEFAULT NOW(),       -- When we first scanned this image
    last_seen TIMESTAMP DEFAULT NOW(),        -- Last time we scanned this image

    UNIQUE(registry, namespace, repository, tag, digest)
);

CREATE INDEX idx_images_lookup ON images(repository, tag);
CREATE INDEX idx_images_type ON images(image_type);
CREATE INDEX idx_images_created ON images(created_at);
```

**Example rows:**
```sql
INSERT INTO images (registry, namespace, repository, tag, image_type, size_bytes, created_at) VALUES
  ('docker', 'library', 'python', '3.11', 'upstream', 189000000, '2025-11-10'),
  ('cgr.dev', 'chainguard', 'python', 'latest', 'chainguard', 47500000, '2025-11-15');
```

---

### Table: `scans`

Stores individual scan results.

```sql
CREATE TABLE scans (
    id SERIAL PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    scanner VARCHAR(50) NOT NULL,             -- 'grype', 'trivy', 'prisma'
    scan_date TIMESTAMP NOT NULL DEFAULT NOW(),
    total_cves INTEGER NOT NULL DEFAULT 0,
    critical INTEGER NOT NULL DEFAULT 0,
    high INTEGER NOT NULL DEFAULT 0,
    medium INTEGER NOT NULL DEFAULT 0,
    low INTEGER NOT NULL DEFAULT 0,
    wontfix INTEGER NOT NULL DEFAULT 0,
    fixed_total INTEGER NOT NULL DEFAULT 0,
    fixed_critical INTEGER NOT NULL DEFAULT 0,
    fixed_high INTEGER NOT NULL DEFAULT 0,
    fixed_medium INTEGER NOT NULL DEFAULT 0,
    fixed_low INTEGER NOT NULL DEFAULT 0,
    scan_metadata JSONB,                      -- Scanner version, config, etc.
    raw_output_path VARCHAR(500),             -- Path to full JSON/CSV output

    UNIQUE(image_id, scanner, scan_date)
);

CREATE INDEX idx_scans_image ON scans(image_id);
CREATE INDEX idx_scans_scanner ON scans(scanner);
CREATE INDEX idx_scans_date ON scans(scan_date DESC);
CREATE INDEX idx_scans_severity ON scans(critical, high);
```

**Example rows:**
```sql
INSERT INTO scans (image_id, scanner, total_cves, critical, high, medium, low) VALUES
  (1, 'grype', 127, 12, 35, 45, 35),  -- upstream Python
  (2, 'grype', 5, 0, 1, 2, 2);         -- Chainguard Python
```

---

### Table: `vulnerabilities`

Stores individual CVE details (optional, for detailed tracking).

```sql
CREATE TABLE vulnerabilities (
    id SERIAL PRIMARY KEY,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    cve_id VARCHAR(50) NOT NULL,              -- e.g., 'CVE-2024-1234'
    severity VARCHAR(50),                     -- 'Critical', 'High', etc.
    package_name VARCHAR(255),                -- Affected package
    package_version VARCHAR(100),             -- Affected version
    fixed_version VARCHAR(100),               -- Fixed in version (if available)
    description TEXT,
    cvss_score DECIMAL(3,1),                  -- CVSS base score
    epss_score DECIMAL(5,4),                  -- EPSS score (if enriched)
    in_cisa_kev BOOLEAN DEFAULT FALSE,        -- In CISA KEV catalog?
    metadata JSONB,                           -- Additional CVE details

    UNIQUE(scan_id, cve_id, package_name)
);

CREATE INDEX idx_vulns_cve ON vulnerabilities(cve_id);
CREATE INDEX idx_vulns_scan ON vulnerabilities(scan_id);
CREATE INDEX idx_vulns_severity ON vulnerabilities(severity);
CREATE INDEX idx_vulns_epss ON vulnerabilities(epss_score DESC);
```

**Example rows:**
```sql
INSERT INTO vulnerabilities (scan_id, cve_id, severity, package_name, package_version, cvss_score) VALUES
  (1, 'CVE-2024-1234', 'Critical', 'openssl', '3.0.0', 9.8),
  (1, 'CVE-2024-5678', 'High', 'curl', '7.88.0', 7.5);
```

---

### Table: `comparisons`

Stores predefined Chainguard vs. upstream comparisons.

```sql
CREATE TABLE comparisons (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,        -- e.g., 'Python 3.11', '.NET 8 Runtime'
    description TEXT,
    chainguard_image_id INTEGER REFERENCES images(id),
    upstream_image_id INTEGER REFERENCES images(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    config JSONB,                             -- Comparison configuration

    CHECK(chainguard_image_id != upstream_image_id)
);

CREATE INDEX idx_comparisons_name ON comparisons(name);
```

**Example rows:**
```sql
INSERT INTO comparisons (name, description, chainguard_image_id, upstream_image_id) VALUES
  ('Python 3.11', 'Python 3.11 runtime comparison', 2, 1);
```

---

### Table: `historical_snapshots`

Tracks historical "latest" tags at specific dates.

```sql
CREATE TABLE historical_snapshots (
    id SERIAL PRIMARY KEY,
    repository VARCHAR(255) NOT NULL,
    registry VARCHAR(255) NOT NULL,
    snapshot_date DATE NOT NULL,              -- Date of the snapshot (e.g., 6 months ago)
    tag VARCHAR(255),                         -- Tag that was "latest" at that date
    image_id INTEGER REFERENCES images(id),
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(repository, registry, snapshot_date)
);

CREATE INDEX idx_snapshots_repo ON historical_snapshots(repository, registry);
CREATE INDEX idx_snapshots_date ON historical_snapshots(snapshot_date);
```

**Example rows:**
```sql
INSERT INTO historical_snapshots (repository, registry, snapshot_date, tag, image_id) VALUES
  ('python', 'docker', '2024-05-18', '3.11.9', 3),     -- 6 months ago
  ('python', 'docker', '2023-11-18', '3.11.6', 4);     -- 1 year ago
```

---

### Table: `reports`

Tracks generated reports.

```sql
CREATE TABLE reports (
    id SERIAL PRIMARY KEY,
    report_type VARCHAR(100) NOT NULL,        -- 'comparison', 'trend', 'summary'
    customer_id VARCHAR(255),                 -- Customer identifier (if multi-tenant)
    generated_at TIMESTAMP DEFAULT NOW(),
    parameters JSONB,                         -- Report parameters (date range, images, etc.)
    output_path VARCHAR(500),                 -- Path to generated PDF/CSV
    output_format VARCHAR(50),                -- 'pdf', 'csv', 'html'
    share_token VARCHAR(255) UNIQUE,          -- For shareable links
    expires_at TIMESTAMP,                     -- Expiration for shared reports

    CHECK(output_format IN ('pdf', 'csv', 'html', 'json'))
);

CREATE INDEX idx_reports_customer ON reports(customer_id);
CREATE INDEX idx_reports_generated ON reports(generated_at DESC);
CREATE INDEX idx_reports_share ON reports(share_token);
```

---

## Views for Common Queries

### View: `latest_scans`

Get the most recent scan for each image/scanner combination.

```sql
CREATE VIEW latest_scans AS
SELECT DISTINCT ON (s.image_id, s.scanner)
    s.*,
    i.repository,
    i.tag,
    i.image_type
FROM scans s
JOIN images i ON s.image_id = i.id
ORDER BY s.image_id, s.scanner, s.scan_date DESC;
```

### View: `comparison_summary`

Summary of Chainguard vs. upstream comparisons.

```sql
CREATE VIEW comparison_summary AS
SELECT
    c.id,
    c.name,
    c.description,

    -- Chainguard image info
    cg_img.repository AS cg_repository,
    cg_img.tag AS cg_tag,
    cg_scan.total_cves AS cg_total_cves,
    cg_scan.critical AS cg_critical,
    cg_scan.high AS cg_high,
    cg_scan.medium AS cg_medium,
    cg_scan.low AS cg_low,
    cg_img.size_bytes AS cg_size,

    -- Upstream image info
    up_img.repository AS up_repository,
    up_img.tag AS up_tag,
    up_scan.total_cves AS up_total_cves,
    up_scan.critical AS up_critical,
    up_scan.high AS up_high,
    up_scan.medium AS up_medium,
    up_scan.low AS up_low,
    up_img.size_bytes AS up_size,

    -- Differentials
    (up_scan.total_cves - cg_scan.total_cves) AS cve_reduction,
    (up_scan.critical - cg_scan.critical) AS critical_reduction,
    (up_scan.high - cg_scan.high) AS high_reduction,
    (up_img.size_bytes - cg_img.size_bytes) AS size_reduction,

    -- Percentages
    ROUND(100.0 * (up_scan.total_cves - cg_scan.total_cves) / NULLIF(up_scan.total_cves, 0), 1) AS cve_reduction_pct

FROM comparisons c
JOIN images cg_img ON c.chainguard_image_id = cg_img.id
JOIN images up_img ON c.upstream_image_id = up_img.id
LEFT JOIN latest_scans cg_scan ON cg_scan.image_id = cg_img.id AND cg_scan.scanner = 'grype'
LEFT JOIN latest_scans up_scan ON up_scan.image_id = up_img.id AND up_scan.scanner = 'grype';
```

---

## Common Queries

### Get latest scan results for an image

```sql
SELECT *
FROM latest_scans
WHERE repository = 'python' AND tag = '3.11'
ORDER BY scanner;
```

### Compare Chainguard vs. upstream

```sql
SELECT
    name,
    cg_repository || ':' || cg_tag AS chainguard_image,
    up_repository || ':' || up_tag AS upstream_image,
    cve_reduction || ' (' || cve_reduction_pct || '%)' AS total_cve_reduction,
    critical_reduction AS critical_cve_reduction
FROM comparison_summary
ORDER BY cve_reduction DESC;
```

### Get historical trend for an image

```sql
SELECT
    scan_date,
    scanner,
    total_cves,
    critical,
    high,
    medium,
    low
FROM scans
WHERE image_id = (
    SELECT id FROM images
    WHERE repository = 'python' AND tag = '3.11' AND image_type = 'chainguard'
)
ORDER BY scan_date DESC
LIMIT 10;
```

### Find images with critical CVEs

```sql
SELECT
    i.repository,
    i.tag,
    i.image_type,
    s.scanner,
    s.critical,
    s.high
FROM scans s
JOIN images i ON s.image_id = i.id
WHERE s.critical > 0
ORDER BY s.critical DESC, s.high DESC;
```

---

## Data Ingestion Script (Pseudocode)

```python
# backend/scripts/ingest_scans.py

import csv
import psycopg2
from datetime import datetime

def ingest_csv(csv_file, conn):
    """Ingest CSV scan results into database"""

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # 1. Insert or update image
            image_id = upsert_image(
                registry=row['registry'],
                repository=row['image_name'],
                tag=row['image_tag'],
                image_type=row['image_type'],
                size_bytes=int(float(row['size_mb']) * 1024 * 1024),
                created_at=row['created_date'],
                conn=conn
            )

            # 2. Insert scan result
            insert_scan(
                image_id=image_id,
                scanner=row['scanner'],
                scan_date=row['scan_date'],
                total_cves=int(row['total']),
                critical=int(row['critical']),
                high=int(row['high']),
                medium=int(row['medium']),
                low=int(row['low']),
                wontfix=int(row['wontfix']),
                fixed_total=int(row['fixed_total']),
                fixed_critical=int(row['fixed_critical']),
                fixed_high=int(row['fixed_high']),
                fixed_medium=int(row['fixed_medium']),
                fixed_low=int(row['fixed_low']),
                conn=conn
            )

    conn.commit()
```

---

## Migration Path

1. **Create database:**
   ```bash
   createdb cve_scanner_dashboard
   ```

2. **Run schema creation:**
   ```bash
   psql cve_scanner_dashboard < backend/database/schema.sql
   ```

3. **Ingest existing scan results:**
   ```bash
   python backend/scripts/ingest_scans.py data/scans/scan_*_merged.csv
   ```

4. **Query data:**
   ```bash
   psql cve_scanner_dashboard -c "SELECT * FROM comparison_summary;"
   ```

---

## Backup & Maintenance

### Regular backups
```bash
pg_dump cve_scanner_dashboard > backup_$(date +%Y%m%d).sql
```

### Archive old scans (keep last 90 days of detailed data)
```sql
DELETE FROM scans
WHERE scan_date < NOW() - INTERVAL '90 days';
```

### Update statistics
```sql
VACUUM ANALYZE;
```

---

## Performance Considerations

1. **Indexes:** Already defined on frequently queried columns
2. **Partitioning:** Consider partitioning `scans` table by `scan_date` for large datasets
3. **Archival:** Move old detailed CVE data to archive tables
4. **Caching:** Cache `comparison_summary` view results in application layer
5. **Materialized views:** Convert `comparison_summary` to materialized view for better performance

---

## Security Considerations

1. **User authentication:** Add user management tables if multi-tenant
2. **API tokens:** Store hashed tokens for API access
3. **Row-level security:** Use PostgreSQL RLS for customer data isolation
4. **Encryption:** Encrypt sensitive fields (if storing customer data)
5. **Audit logging:** Add audit trail table for tracking changes
