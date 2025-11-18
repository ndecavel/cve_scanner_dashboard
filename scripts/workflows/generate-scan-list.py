#!/usr/bin/env python3
"""
Generate scan list from historical version data

Takes the historical versions YAML and creates a flat text file
suitable for input to the scan orchestrator.

Usage:
    python generate-scan-list.py --input=historical.yaml --output=scan-list.txt
"""

import argparse
import yaml
import sys
from datetime import datetime


def generate_scan_list(historical_data: dict, customer_name: str = None) -> str:
    """
    Generate scan list text from historical version data

    Returns formatted text suitable for scanner input
    """
    lines = []

    # Header
    lines.append("# CVE Scanner Dashboard - Scan List")
    if customer_name:
        lines.append(f"# Customer: {customer_name}")
    lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("#")
    lines.append("# Format: image_reference,image_type")
    lines.append("#")
    lines.append("")

    mappings = historical_data.get('mappings', [])
    total_scans = 0

    for mapping in mappings:
        status = mapping.get('status')

        # Skip unmapped images
        if status != 'mapped':
            upstream = mapping.get('upstream', {})
            lines.append(f"# SKIPPED: {upstream.get('full_ref', 'unknown')} - {mapping.get('message', 'unmapped')}")
            if mapping.get('alternative'):
                lines.append(f"#   Alternative: {mapping['alternative']}")
            lines.append("")
            continue

        upstream = mapping.get('upstream', {})
        chainguard = mapping.get('chainguard', {})
        upstream_versions = mapping.get('upstream_versions', {})
        chainguard_versions = mapping.get('chainguard_versions', {})

        # Section header
        image_name = upstream.get('image', 'unknown')
        lines.append(f"# {image_name.upper()}")
        lines.append(f"# Upstream: {upstream.get('full_ref', 'unknown')}")
        lines.append(f"# Chainguard: {chainguard.get('full_ref', 'unknown')}")
        lines.append("")

        # Add images for each time period
        periods = [
            ('current', 'Current'),
            ('six_months_ago', '6 Months Ago'),
            ('one_year_ago', '1 Year Ago'),
        ]

        for period_key, period_label in periods:
            lines.append(f"# {period_label}")

            # Upstream version
            upstream_version = upstream_versions.get(period_key)
            if upstream_version:
                up_registry = upstream.get('registry', '')
                up_image = upstream.get('image', '')
                up_tag = upstream_version.get('tag', 'unknown')

                # Build full reference
                if up_registry:
                    full_ref = f"{up_registry}/{up_image}:{up_tag}"
                else:
                    full_ref = f"{up_image}:{up_tag}"

                created = upstream_version.get('created', 'unknown')
                if created and created != 'unknown':
                    created_date = created[:10]  # Just the date part
                    lines.append(f"{full_ref},upstream  # Created: {created_date}")
                else:
                    lines.append(f"{full_ref},upstream")

                total_scans += 1
            else:
                lines.append(f"# Upstream version not found for {period_label}")

            # Chainguard version
            cg_version = chainguard_versions.get(period_key)
            if cg_version:
                cg_tag = cg_version.get('tag', 'latest')
                cg_image = chainguard.get('registry', 'cgr.dev/chainguard')
                cg_name = chainguard.get('image', '')

                full_ref = f"{cg_image}/{cg_name}:{cg_tag}"

                created = cg_version.get('created')
                if created:
                    created_date = created[:10]
                    lines.append(f"{full_ref},chainguard  # Created: {created_date}")
                else:
                    lines.append(f"{full_ref},chainguard")

                total_scans += 1
            else:
                # Use current tag as fallback
                cg_tag = chainguard.get('tag', 'latest')
                cg_full_ref = chainguard.get('full_ref', f"cgr.dev/chainguard/{cg_tag}")
                lines.append(f"{cg_full_ref},chainguard  # Using current version")
                total_scans += 1

            lines.append("")

        lines.append("")  # Blank line between images

    # Footer
    lines.append(f"# Total images to scan: {total_scans}")
    lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate scan list from historical version data'
    )
    parser.add_argument('--input', required=True,
                        help='Input historical versions YAML file')
    parser.add_argument('--output', required=True,
                        help='Output scan list text file')
    parser.add_argument('--customer', default=None,
                        help='Customer name for header')

    args = parser.parse_args()

    # Load historical data
    with open(args.input, 'r') as f:
        data = yaml.safe_load(f)

    # Generate scan list
    scan_list = generate_scan_list(data, args.customer)

    # Save output
    with open(args.output, 'w') as f:
        f.write(scan_list)

    # Count total scans
    scan_count = sum(1 for line in scan_list.split('\n')
                    if line and not line.startswith('#') and ',' in line)

    print(f"Scan list generated!")
    print(f"  Total images to scan: {scan_count}")
    print(f"  Output saved to: {args.output}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
