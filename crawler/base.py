"""
Base registry crawler class
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
import re


@dataclass
class ImageTag:
    """Represents a container image tag with metadata"""
    name: str
    created: Optional[datetime] = None
    digest: Optional[str] = None
    size: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    def is_semver(self) -> bool:
        """Check if tag follows semantic versioning"""
        # Match patterns like: 1.2.3, v1.2.3, 1.2, etc.
        semver_pattern = r'^v?\d+(\.\d+)*'
        return bool(re.match(semver_pattern, self.name))

    def is_dev(self) -> bool:
        """Check if tag is a development/preview tag"""
        dev_patterns = [
            r'-dev$',
            r'-alpha',
            r'-beta',
            r'-rc',
            r'^sha256-',
            r'-r\d+$',  # Revision tags
            r'nightly',
            r'latest',
        ]
        for pattern in dev_patterns:
            if re.search(pattern, self.name, re.IGNORECASE):
                return True
        return False

    def __repr__(self) -> str:
        created_str = self.created.isoformat() if self.created else 'unknown'
        return f"ImageTag(name='{self.name}', created='{created_str}')"


class RegistryCrawler(ABC):
    """Abstract base class for registry crawlers"""

    def __init__(self, base_url: str, rate_limit_delay: float = 0.5):
        """
        Initialize crawler

        Args:
            base_url: Base URL for the registry
            rate_limit_delay: Delay between API requests in seconds
        """
        self.base_url = base_url
        self.rate_limit_delay = rate_limit_delay

    @abstractmethod
    def list_tags(self, repository: str, namespace: Optional[str] = None) -> List[ImageTag]:
        """
        List all tags for a repository

        Args:
            repository: Repository name (e.g., "python", "node")
            namespace: Optional namespace/organization (e.g., "library", "istio")

        Returns:
            List of ImageTag objects
        """
        pass

    @abstractmethod
    def get_tag_metadata(self, repository: str, tag: str, namespace: Optional[str] = None) -> ImageTag:
        """
        Get detailed metadata for a specific tag

        Args:
            repository: Repository name
            tag: Tag name
            namespace: Optional namespace/organization

        Returns:
            ImageTag object with metadata
        """
        pass

    def filter_tags(
        self,
        tags: List[ImageTag],
        include_dev: bool = False,
        only_semver: bool = False,
        pattern: Optional[str] = None,
    ) -> List[ImageTag]:
        """
        Filter tags based on criteria

        Args:
            tags: List of tags to filter
            include_dev: Include development tags (default: False)
            only_semver: Only include semantic version tags (default: False)
            pattern: Regex pattern to match tag names (default: None)

        Returns:
            Filtered list of tags
        """
        filtered = tags

        # Filter dev tags
        if not include_dev:
            filtered = [t for t in filtered if not t.is_dev()]

        # Filter semver
        if only_semver:
            filtered = [t for t in filtered if t.is_semver()]

        # Filter by pattern
        if pattern:
            regex = re.compile(pattern)
            filtered = [t for t in filtered if regex.search(t.name)]

        return filtered

    def sort_tags_by_date(self, tags: List[ImageTag], reverse: bool = True) -> List[ImageTag]:
        """
        Sort tags by creation date

        Args:
            tags: List of tags to sort
            reverse: Sort in descending order (newest first) (default: True)

        Returns:
            Sorted list of tags
        """
        # Tags without dates go to the end
        with_dates = [t for t in tags if t.created is not None]
        without_dates = [t for t in tags if t.created is None]

        with_dates.sort(key=lambda t: t.created, reverse=reverse)

        return with_dates + without_dates
