"""
Historical tag resolver - finds the "latest" tag at a specific point in time
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
from .base import ImageTag, RegistryCrawler


class HistoricalTagResolver:
    """Resolves historical tags for container images"""

    def __init__(self, crawler: RegistryCrawler):
        """
        Initialize resolver

        Args:
            crawler: Registry crawler instance
        """
        self.crawler = crawler

    def find_latest_at_date(
        self,
        repository: str,
        target_date: datetime,
        namespace: Optional[str] = None,
        tag_pattern: Optional[str] = None,
        only_semver: bool = True,
        exclude_dev: bool = True,
    ) -> Optional[ImageTag]:
        """
        Find the latest tag that existed at a specific date

        Args:
            repository: Repository name
            target_date: Target date to find latest tag for
            namespace: Optional namespace
            tag_pattern: Optional regex pattern to filter tags
            only_semver: Only consider semantic version tags (default: True)
            exclude_dev: Exclude dev/preview tags (default: True)

        Returns:
            ImageTag object or None if no matching tag found
        """
        # Get all tags
        all_tags = self.crawler.list_tags(repository, namespace)

        # Filter tags
        filtered_tags = self.crawler.filter_tags(
            all_tags,
            include_dev=not exclude_dev,
            only_semver=only_semver,
            pattern=tag_pattern,
        )

        # Filter by date: only tags created before or at target date
        historical_tags = [
            tag for tag in filtered_tags
            if tag.created and tag.created <= target_date
        ]

        if not historical_tags:
            return None

        # Sort by date (newest first) and return the first one
        sorted_tags = self.crawler.sort_tags_by_date(historical_tags, reverse=True)

        return sorted_tags[0] if sorted_tags else None

    def find_tags_for_periods(
        self,
        repository: str,
        periods: List[Dict[str, any]],
        namespace: Optional[str] = None,
        tag_pattern: Optional[str] = None,
        only_semver: bool = True,
        exclude_dev: bool = True,
    ) -> Dict[str, Optional[ImageTag]]:
        """
        Find latest tags for multiple time periods

        Args:
            repository: Repository name
            periods: List of period configs with 'name' and 'offset_days'
                Example: [
                    {'name': 'current', 'offset_days': 0},
                    {'name': '6_months_ago', 'offset_days': 180},
                    {'name': '1_year_ago', 'offset_days': 365},
                ]
            namespace: Optional namespace
            tag_pattern: Optional regex pattern to filter tags
            only_semver: Only consider semantic version tags (default: True)
            exclude_dev: Exclude dev/preview tags (default: True)

        Returns:
            Dict mapping period name to ImageTag (or None if not found)
        """
        results = {}

        for period in periods:
            period_name = period['name']
            offset_days = period['offset_days']

            # Calculate target date (timezone-aware UTC)
            target_date = datetime.now(timezone.utc) - timedelta(days=offset_days)

            # Find latest tag at that date
            tag = self.find_latest_at_date(
                repository=repository,
                target_date=target_date,
                namespace=namespace,
                tag_pattern=tag_pattern,
                only_semver=only_semver,
                exclude_dev=exclude_dev,
            )

            results[period_name] = tag

        return results

    def compare_chainguard_vs_upstream(
        self,
        chainguard_repo: str,
        upstream_repo: str,
        upstream_crawler: RegistryCrawler,
        periods: List[Dict[str, any]],
        chainguard_namespace: Optional[str] = None,
        upstream_namespace: Optional[str] = None,
        chainguard_pattern: Optional[str] = None,
        upstream_pattern: Optional[str] = None,
    ) -> Dict[str, Dict[str, Optional[ImageTag]]]:
        """
        Compare Chainguard and upstream images across time periods

        Args:
            chainguard_repo: Chainguard repository name
            upstream_repo: Upstream repository name
            upstream_crawler: Crawler for upstream registry (Docker Hub, MCR, etc.)
            periods: Time periods to check
            chainguard_namespace: Optional Chainguard namespace
            upstream_namespace: Optional upstream namespace
            chainguard_pattern: Tag pattern for Chainguard images
            upstream_pattern: Tag pattern for upstream images

        Returns:
            Dict with structure:
            {
                'period_name': {
                    'chainguard': ImageTag or None,
                    'upstream': ImageTag or None,
                },
                ...
            }
        """
        # Find Chainguard tags
        cg_tags = self.find_tags_for_periods(
            repository=chainguard_repo,
            periods=periods,
            namespace=chainguard_namespace,
            tag_pattern=chainguard_pattern,
        )

        # Find upstream tags
        upstream_tags = HistoricalTagResolver(upstream_crawler).find_tags_for_periods(
            repository=upstream_repo,
            periods=periods,
            namespace=upstream_namespace,
            tag_pattern=upstream_pattern,
        )

        # Combine results
        comparison = {}
        for period in periods:
            period_name = period['name']
            comparison[period_name] = {
                'chainguard': cg_tags.get(period_name),
                'upstream': upstream_tags.get(period_name),
            }

        return comparison

    def generate_image_list(
        self,
        comparisons: List[Dict[str, any]],
        periods: List[Dict[str, any]],
        output_format: str = 'csv',
    ) -> str:
        """
        Generate an image list for scanning based on comparisons

        Args:
            comparisons: List of comparison configs (from image-comparisons.yaml)
            periods: List of time period configs
            output_format: Output format ('csv' or 'yaml')

        Returns:
            Formatted image list as string
        """
        lines = []

        if output_format == 'csv':
            lines.append("# Generated image list for CVE scanning")
            lines.append("# Format: image_reference,image_type")
            lines.append("")

        for comparison in comparisons:
            name = comparison.get('name', 'Unknown')
            cg_config = comparison.get('chainguard', {})
            up_config = comparison.get('upstream', {})

            if output_format == 'csv':
                lines.append(f"# {name}")

            # For each period, add the resolved tags
            for period in periods:
                period_name = period['name']

                # Chainguard image
                cg_registry = cg_config.get('registry', '')
                cg_image = cg_config.get('image', '')
                cg_tag = cg_config.get('tag', 'latest')  # Placeholder - should be resolved

                cg_ref = f"{cg_registry}/{cg_image}:{cg_tag}"

                # Upstream image
                up_image = up_config.get('image', '')
                up_tag = up_config.get('tag', 'latest')  # Placeholder - should be resolved

                # Handle registry prefix for upstream
                upstream_registry = up_config.get('registry', 'docker')
                if upstream_registry == 'docker':
                    up_ref = f"{up_image}:{up_tag}"
                elif upstream_registry == 'mcr':
                    up_ref = f"mcr.microsoft.com/{up_image}:{up_tag}"
                else:
                    up_ref = f"{up_image}:{up_tag}"

                if output_format == 'csv':
                    lines.append(f"{cg_ref},chainguard  # {period_name}")
                    lines.append(f"{up_ref},upstream  # {period_name}")

            if output_format == 'csv':
                lines.append("")  # Blank line between comparisons

        return '\n'.join(lines)
