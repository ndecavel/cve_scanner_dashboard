#!/usr/bin/env python3
"""
CVE Scanner Dashboard - Registry Crawler CLI

Command-line interface for crawling container registries and finding historical tags.
"""

import argparse
import json
import yaml
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .docker_hub import DockerHubCrawler
from .mcr import MCRCrawler
from .resolver import HistoricalTagResolver


def list_tags_command(args):
    """List all tags for a repository"""
    # Select crawler
    if args.registry == 'docker':
        crawler = DockerHubCrawler(rate_limit_delay=args.rate_limit)
    elif args.registry == 'mcr':
        crawler = MCRCrawler(rate_limit_delay=args.rate_limit)
    else:
        print(f"Error: Unsupported registry: {args.registry}", file=sys.stderr)
        return 1

    # List tags
    print(f"Fetching tags for {args.repository}...", file=sys.stderr)
    tags = crawler.list_tags(args.repository, args.namespace)

    # Filter tags
    if args.filter:
        tags = crawler.filter_tags(
            tags,
            include_dev=not args.exclude_dev,
            only_semver=args.only_semver,
            pattern=args.pattern,
        )

    # Sort tags
    if args.sort_by_date:
        tags = crawler.sort_tags_by_date(tags, reverse=True)

    # Output
    if args.output_format == 'json':
        tag_list = [
            {
                'name': tag.name,
                'created': tag.created.isoformat() if tag.created else None,
                'digest': tag.digest,
                'size': tag.size,
            }
            for tag in tags
        ]
        print(json.dumps(tag_list, indent=2))
    else:
        # CSV format
        print("tag,created,digest,size")
        for tag in tags:
            created_str = tag.created.isoformat() if tag.created else 'unknown'
            digest_str = tag.digest or 'unknown'
            size_str = str(tag.size) if tag.size else 'unknown'
            print(f"{tag.name},{created_str},{digest_str},{size_str}")

    return 0


def find_historical_command(args):
    """Find historical tags for a repository"""
    # Select crawler
    if args.registry == 'docker':
        crawler = DockerHubCrawler(rate_limit_delay=args.rate_limit)
    elif args.registry == 'mcr':
        crawler = MCRCrawler(rate_limit_delay=args.rate_limit)
    else:
        print(f"Error: Unsupported registry: {args.registry}", file=sys.stderr)
        return 1

    # Create resolver
    resolver = HistoricalTagResolver(crawler)

    # Define periods
    periods = [
        {'name': 'current', 'offset_days': 0},
        {'name': '6_months_ago', 'offset_days': 180},
        {'name': '1_year_ago', 'offset_days': 365},
    ]

    # Custom periods from args
    if args.periods:
        try:
            periods = json.loads(args.periods)
        except json.JSONDecodeError as e:
            print(f"Error parsing periods JSON: {e}", file=sys.stderr)
            return 1

    # Find tags for periods
    print(f"Finding historical tags for {args.repository}...", file=sys.stderr)
    results = resolver.find_tags_for_periods(
        repository=args.repository,
        periods=periods,
        namespace=args.namespace,
        tag_pattern=args.pattern,
        only_semver=args.only_semver,
        exclude_dev=args.exclude_dev,
    )

    # Output
    if args.output_format == 'json':
        output = {}
        for period_name, tag in results.items():
            output[period_name] = {
                'tag': tag.name if tag else None,
                'created': tag.created.isoformat() if tag and tag.created else None,
            }
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"{'Period':<20} {'Tag':<30} {'Created':<30}")
        print("-" * 80)
        for period_name, tag in results.items():
            tag_name = tag.name if tag else 'NOT FOUND'
            created_str = tag.created.isoformat() if tag and tag.created else 'unknown'
            print(f"{period_name:<20} {tag_name:<30} {created_str:<30}")

    return 0


def generate_image_list_command(args):
    """Generate image list from comparisons config"""
    # Load comparisons config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        return 1

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    comparisons = config.get('comparisons', [])
    periods = config.get('historical', {}).get('periods', [
        {'name': 'current', 'offset_days': 0},
        {'name': '6_months_ago', 'offset_days': 180},
        {'name': '1_year_ago', 'offset_days': 365},
    ])

    print("# Generated image list for CVE scanning")
    print("# Format: image_reference,image_type")
    print("")

    for comparison in comparisons:
        name = comparison.get('name', 'Unknown')
        cg_config = comparison.get('chainguard', {})
        up_config = comparison.get('upstream', {})

        print(f"# {name}")

        for period in periods:
            period_name = period['name']

            # Chainguard image
            cg_registry = cg_config.get('registry', 'cgr.dev/chainguard')
            cg_image = cg_config.get('image', '')
            cg_tag = cg_config.get('tag', 'latest')

            cg_ref = f"{cg_registry}/{cg_image}:{cg_tag}"

            # Upstream image
            up_image = up_config.get('image', '')
            up_tag = up_config.get('tag', 'latest')

            # Handle registry prefix for upstream
            upstream_registry = up_config.get('registry', 'docker')
            if upstream_registry == 'docker':
                up_ref = f"{up_image}:{up_tag}"
            elif upstream_registry == 'mcr':
                up_ref = f"mcr.microsoft.com/{up_image}:{up_tag}"
            else:
                up_ref = f"{up_image}:{up_tag}"

            print(f"{cg_ref},chainguard  # {period_name}")
            print(f"{up_ref},upstream  # {period_name}")

        print("")  # Blank line between comparisons

    return 0


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='CVE Scanner Dashboard - Registry Crawler'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # list-tags command
    list_parser = subparsers.add_parser('list-tags', help='List all tags for a repository')
    list_parser.add_argument('repository', help='Repository name (e.g., python, dotnet/runtime)')
    list_parser.add_argument('--registry', choices=['docker', 'mcr'], default='docker',
                             help='Registry type (default: docker)')
    list_parser.add_argument('--namespace', help='Repository namespace (optional)')
    list_parser.add_argument('--pattern', help='Tag pattern (regex) to filter')
    list_parser.add_argument('--only-semver', action='store_true',
                             help='Only show semantic version tags')
    list_parser.add_argument('--exclude-dev', action='store_true',
                             help='Exclude dev/preview tags')
    list_parser.add_argument('--filter', action='store_true',
                             help='Apply filters (pattern, semver, dev)')
    list_parser.add_argument('--sort-by-date', action='store_true',
                             help='Sort by creation date (newest first)')
    list_parser.add_argument('--output-format', choices=['csv', 'json'], default='csv',
                             help='Output format (default: csv)')
    list_parser.add_argument('--rate-limit', type=float, default=1.0,
                             help='Rate limit delay in seconds (default: 1.0)')

    # find-historical command
    hist_parser = subparsers.add_parser('find-historical',
                                        help='Find historical tags at specific dates')
    hist_parser.add_argument('repository', help='Repository name')
    hist_parser.add_argument('--registry', choices=['docker', 'mcr'], default='docker',
                             help='Registry type (default: docker)')
    hist_parser.add_argument('--namespace', help='Repository namespace (optional)')
    hist_parser.add_argument('--pattern', help='Tag pattern (regex) to filter')
    hist_parser.add_argument('--only-semver', action='store_true', default=True,
                             help='Only consider semantic version tags (default: True)')
    hist_parser.add_argument('--exclude-dev', action='store_true', default=True,
                             help='Exclude dev/preview tags (default: True)')
    hist_parser.add_argument('--periods', help='JSON array of periods (e.g., [{"name":"current","offset_days":0}])')
    hist_parser.add_argument('--output-format', choices=['table', 'json'], default='table',
                             help='Output format (default: table)')
    hist_parser.add_argument('--rate-limit', type=float, default=1.0,
                             help='Rate limit delay in seconds (default: 1.0)')

    # generate-image-list command
    gen_parser = subparsers.add_parser('generate-image-list',
                                       help='Generate image list from comparisons config')
    gen_parser.add_argument('--config', default='config/image-comparisons.yaml',
                            help='Path to comparisons config (default: config/image-comparisons.yaml)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run command
    if args.command == 'list-tags':
        return list_tags_command(args)
    elif args.command == 'find-historical':
        return find_historical_command(args)
    elif args.command == 'generate-image-list':
        return generate_image_list_command(args)
    else:
        print(f"Error: Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
