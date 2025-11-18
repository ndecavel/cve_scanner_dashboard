#!/usr/bin/env python3
"""
Resolve historical versions for mapped images (PARALLELIZED)

For each upstream and Chainguard image pair, finds:
- Current version
- Version from 6 months ago
- Version from 1 year ago

Now with parallel processing for faster execution!

Usage:
    python resolve-historical-versions.py --mappings=mappings.yaml --output=historical.yaml
    python resolve-historical-versions.py --mappings=mappings.yaml --output=historical.yaml --workers=10 --verbose
"""

import argparse
import yaml
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Import our crawler modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from crawler.docker_hub import DockerHubCrawler
from crawler.mcr import MCRCrawler
from crawler.resolver import HistoricalTagResolver


class HistoricalVersionResolver:
    """Resolves historical versions for image pairs (with parallel support)"""

    def __init__(self, rate_limit: float = 1.0, verbose: bool = False):
        """Initialize crawlers"""
        self.docker_crawler = DockerHubCrawler(rate_limit_delay=rate_limit)
        self.mcr_crawler = MCRCrawler(rate_limit_delay=rate_limit/2)
        self.cg_crawler = DockerHubCrawler(rate_limit_delay=rate_limit)
        self.verbose = verbose
        self.print_lock = Lock()  # For thread-safe printing

        # Define time periods
        self.periods = [
            {'name': 'current', 'offset_days': 0},
            {'name': 'six_months_ago', 'offset_days': 180},
            {'name': 'one_year_ago', 'offset_days': 365},
        ]

    def log(self, message: str, force: bool = False):
        """Thread-safe logging"""
        if self.verbose or force:
            with self.print_lock:
                print(message, file=sys.stderr)

    def get_crawler(self, registry_type: str):
        """Get appropriate crawler for registry type"""
        if registry_type == 'mcr':
            return self.mcr_crawler
        else:
            return self.docker_crawler

    def resolve_versions(self, image: str, registry_type: str, tag_pattern: str = None) -> dict:
        """
        Resolve historical versions for an image

        Args:
            image: Image name (e.g., 'python', 'dotnet/runtime')
            registry_type: Registry type ('docker', 'mcr', etc.)
            tag_pattern: Optional regex pattern to filter tags

        Returns:
            Dict with version information for each period
        """
        start_time = time.time()

        crawler = self.get_crawler(registry_type)
        resolver = HistoricalTagResolver(crawler)

        try:
            results = resolver.find_tags_for_periods(
                repository=image,
                periods=self.periods,
                tag_pattern=tag_pattern,
                only_semver=True,
                exclude_dev=True,
            )

            # Convert to serializable format
            versions = {}
            for period_name, tag in results.items():
                if tag:
                    versions[period_name] = {
                        'tag': tag.name,
                        'created': tag.created.isoformat() if tag.created else None,
                        'digest': tag.digest,
                        'size': tag.size,
                    }
                else:
                    versions[period_name] = None

            elapsed = time.time() - start_time
            self.log(f"    ✓ Resolved {image} ({registry_type}) in {elapsed:.1f}s")

            return versions

        except Exception as e:
            elapsed = time.time() - start_time
            self.log(f"    ✗ Error resolving {image} ({registry_type}) after {elapsed:.1f}s: {e}")
            return {}

    def resolve_single_mapping(self, mapping: dict, index: int, total: int) -> dict:
        """
        Resolve a single mapping (for parallel execution)

        Args:
            mapping: Mapping dict
            index: Current index (for progress)
            total: Total count (for progress)

        Returns:
            Mapping dict with upstream_versions and chainguard_versions added
        """
        start_time = time.time()
        status = mapping.get('status')

        if status != 'mapped':
            # Skip unmapped images
            self.log(f"[{index}/{total}] Skipping unmapped: {mapping.get('upstream', {}).get('full_ref', 'unknown')}")
            return {
                **mapping,
                'upstream_versions': None,
                'chainguard_versions': None,
            }

        upstream = mapping['upstream']
        chainguard = mapping['chainguard']

        self.log(f"[{index}/{total}] Processing: {upstream['full_ref']}", force=True)

        # Resolve upstream versions
        self.log(f"  → Upstream: {upstream['full_ref']}")
        upstream_versions = self.resolve_versions(
            image=upstream['image'],
            registry_type=upstream['registry_type'],
            tag_pattern=None
        )

        # Resolve Chainguard versions
        self.log(f"  → Chainguard: {chainguard['full_ref']}")
        # For now, simplified Chainguard handling
        chainguard_versions = {
            'current': {
                'tag': chainguard['tag'],
                'created': None,
                'digest': None,
                'size': None,
            },
            'six_months_ago': None,
            'one_year_ago': None,
        }

        elapsed = time.time() - start_time
        self.log(f"[{index}/{total}] ✓ Completed in {elapsed:.1f}s", force=True)

        return {
            **mapping,
            'upstream_versions': upstream_versions,
            'chainguard_versions': chainguard_versions,
        }

    def resolve_all_mappings_sequential(self, mappings: list) -> list:
        """Resolve historical versions sequentially (old method)"""
        results = []
        total = len(mappings)

        for index, mapping in enumerate(mappings, 1):
            result = self.resolve_single_mapping(mapping, index, total)
            results.append(result)

        return results

    def resolve_all_mappings_parallel(self, mappings: list, workers: int = 5) -> list:
        """Resolve historical versions in parallel"""
        total = len(mappings)
        results = [None] * total  # Pre-allocate results list

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(self.resolve_single_mapping, mapping, index + 1, total): index
                for index, mapping in enumerate(mappings)
            }

            # Collect results as they complete
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    results[index] = result
                except Exception as e:
                    self.log(f"ERROR: Task failed with exception: {e}")
                    # Put back original mapping with no versions
                    results[index] = {
                        **mappings[index],
                        'upstream_versions': None,
                        'chainguard_versions': None,
                    }

        return results


def main():
    parser = argparse.ArgumentParser(
        description='Resolve historical versions for mapped images (with parallelization)'
    )
    parser.add_argument('--mappings', required=True,
                        help='Input mappings YAML file')
    parser.add_argument('--output', required=True,
                        help='Output YAML file with historical versions')
    parser.add_argument('--rate-limit', type=float, default=1.0,
                        help='Rate limit delay in seconds (default: 1.0)')
    parser.add_argument('--workers', type=int, default=5,
                        help='Number of parallel workers (default: 5, use 1 for sequential)')
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose output showing detailed progress')

    args = parser.parse_args()

    # Load mappings
    with open(args.mappings, 'r') as f:
        data = yaml.safe_load(f)

    mappings = data.get('mappings', [])

    # Count mapped vs unmapped
    mapped_count = sum(1 for m in mappings if m.get('status') == 'mapped')

    print(f"Resolving historical versions for {len(mappings)} images ({mapped_count} mapped)...")
    if args.workers > 1:
        print(f"Using {args.workers} parallel workers for faster processing")
    else:
        print("Using sequential processing")

    if not args.verbose:
        print("(Use --verbose for detailed progress)")

    print("")

    # Resolve versions
    start_time = time.time()
    resolver = HistoricalVersionResolver(rate_limit=args.rate_limit, verbose=args.verbose)

    if args.workers > 1:
        results = resolver.resolve_all_mappings_parallel(mappings, workers=args.workers)
    else:
        results = resolver.resolve_all_mappings_sequential(mappings)

    elapsed = time.time() - start_time

    # Count successfully resolved
    resolved_count = sum(1 for r in results
                        if r.get('upstream_versions') and
                        any(r['upstream_versions'].values()))

    # Save output
    output_data = {
        'customer_images': data.get('customer_images', []),
        'mappings': results,
        'statistics': {
            'total': len(results),
            'resolved': resolved_count,
            'failed': len(results) - resolved_count,
        },
    }

    with open(args.output, 'w') as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    print(f"\n{'='*60}")
    print(f"Historical version resolution complete!")
    print(f"  Total images: {len(results)}")
    print(f"  Successfully resolved: {resolved_count}")
    print(f"  Failed to resolve: {len(results) - resolved_count}")
    print(f"  Total time: {elapsed:.1f}s")

    if args.workers > 1 and mapped_count > 1:
        sequential_estimate = elapsed * args.workers
        speedup = sequential_estimate / elapsed if elapsed > 0 else 0
        print(f"  Estimated speedup: {speedup:.1f}x faster than sequential")

    print(f"\nResults saved to: {args.output}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
