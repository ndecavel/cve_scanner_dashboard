#!/usr/bin/env python3
"""
Parse manual image mappings from CSV file

Instead of automatic mapping, this script accepts a CSV file where
the user manually specifies upstream → Chainguard pairs.

CSV Format:
    upstream_image,chainguard_image
    python:3.11,cgr.dev/chainguard/python:latest
    node:20,cgr.dev/chainguard/node:20
    nginx:latest,cgr.dev/chainguard/nginx:latest

Usage:
    python parse-manual-mappings.py --input=mappings.csv --output=mappings.yaml
"""

import argparse
import csv
import yaml
import sys
from typing import Tuple


def parse_image_ref(image_ref: str) -> Tuple[str, str, str]:
    """
    Parse image reference into registry, image, tag

    Examples:
        python:3.11 → ('', 'python', '3.11')
        cgr.dev/chainguard/python:latest → ('cgr.dev/chainguard', 'python', 'latest')
        mcr.microsoft.com/dotnet/runtime:8.0 → ('mcr.microsoft.com', 'dotnet/runtime', '8.0')
    """
    # Split registry from image
    if '/' in image_ref and '.' in image_ref.split('/')[0]:
        # Has registry prefix
        parts = image_ref.split('/', 1)
        registry = parts[0]
        rest = parts[1]
    else:
        # No registry (Docker Hub)
        registry = ''
        rest = image_ref

    # Split image from tag
    if ':' in rest:
        image, tag = rest.rsplit(':', 1)
    else:
        image = rest
        tag = 'latest'

    return registry, image, tag


def get_registry_type(registry: str) -> str:
    """Determine registry type"""
    registry_mappings = {
        '': 'docker',
        'docker.io': 'docker',
        'mcr.microsoft.com': 'mcr',
        'quay.io': 'quay',
        'gcr.io': 'gcr',
        'ghcr.io': 'ghcr',
    }
    return registry_mappings.get(registry, 'unknown')


def parse_mapping_row(upstream_ref: str, chainguard_ref: str) -> dict:
    """
    Parse a single mapping row into structured format

    Returns dict compatible with automatic mapper output
    """
    # Parse upstream image
    up_registry, up_image, up_tag = parse_image_ref(upstream_ref)
    up_registry_type = get_registry_type(up_registry)

    # Parse Chainguard image
    cg_registry, cg_image, cg_tag = parse_image_ref(chainguard_ref)

    # Build structured mapping
    mapping = {
        'upstream': {
            'full_ref': upstream_ref,
            'registry': up_registry if up_registry else '',
            'registry_type': up_registry_type,
            'image': up_image,
            'tag': up_tag,
        },
        'chainguard': {
            'full_ref': chainguard_ref,
            'registry': cg_registry,
            'image': cg_image,
            'tag': cg_tag,
        },
        'status': 'mapped',
        'message': f"Manually mapped {upstream_ref} → {chainguard_ref}",
        'alternative': None,
    }

    return mapping


def main():
    parser = argparse.ArgumentParser(
        description='Parse manual image mappings from CSV'
    )
    parser.add_argument('--input', required=True,
                        help='Input CSV file with mappings')
    parser.add_argument('--output', required=True,
                        help='Output YAML file')
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Read CSV file
    mappings = []
    customer_images = []

    print(f"Parsing manual mappings from: {args.input}")

    with open(args.input, 'r') as f:
        reader = csv.reader(f)

        for row_num, row in enumerate(reader, 1):
            # Skip empty lines
            if not row or not any(row):
                continue

            # Skip header row (if it looks like a header)
            if row_num == 1 and 'upstream' in row[0].lower() and 'chainguard' in row[1].lower():
                if args.verbose:
                    print(f"  Skipping header row: {row}")
                continue

            # Skip comments (lines starting with #)
            if row[0].strip().startswith('#'):
                continue

            # Expect exactly 2 columns
            if len(row) < 2:
                print(f"WARNING: Line {row_num} has fewer than 2 columns, skipping")
                continue

            upstream_ref = row[0].strip()
            chainguard_ref = row[1].strip()

            if not upstream_ref or not chainguard_ref:
                print(f"WARNING: Line {row_num} has empty values, skipping")
                continue

            # Parse mapping
            mapping = parse_mapping_row(upstream_ref, chainguard_ref)
            mappings.append(mapping)
            customer_images.append(upstream_ref)

            if args.verbose:
                print(f"  {mapping['message']}")

    # Save output
    output_data = {
        'customer_images': customer_images,
        'mappings': mappings,
        'statistics': {
            'mapped': len(mappings),
            'unsupported': 0,
            'not_found': 0,
        },
    }

    with open(args.output, 'w') as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    print(f"\nManual mapping complete!")
    print(f"  Total mappings: {len(mappings)}")
    print(f"  Output saved to: {args.output}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
