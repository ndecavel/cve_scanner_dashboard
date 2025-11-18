"""
Docker Hub registry crawler
"""

import requests
import time
from datetime import datetime
from typing import List, Optional
from .base import RegistryCrawler, ImageTag


class DockerHubCrawler(RegistryCrawler):
    """Crawler for Docker Hub registry"""

    def __init__(self, rate_limit_delay: float = 1.0):
        """
        Initialize Docker Hub crawler

        Args:
            rate_limit_delay: Delay between API requests (default: 1.0 sec for rate limits)
        """
        super().__init__("https://hub.docker.com", rate_limit_delay)
        self.api_base = "https://hub.docker.com/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CVE-Scanner-Dashboard/0.1.0'
        })

    def _get_namespace(self, repository: str, namespace: Optional[str] = None) -> tuple:
        """
        Parse namespace and repository

        Args:
            repository: Repository name (can include namespace like "library/python")
            namespace: Explicit namespace (overrides repository namespace)

        Returns:
            Tuple of (namespace, repository)
        """
        if namespace:
            return namespace, repository

        # Check if repository includes namespace
        if '/' in repository:
            parts = repository.split('/')
            return parts[0], parts[1]

        # Official images use 'library' namespace
        return 'library', repository

    def list_tags(self, repository: str, namespace: Optional[str] = None) -> List[ImageTag]:
        """
        List all tags for a Docker Hub repository

        Args:
            repository: Repository name (e.g., "python", "node")
            namespace: Optional namespace (default: "library" for official images)

        Returns:
            List of ImageTag objects
        """
        ns, repo = self._get_namespace(repository, namespace)

        tags = []
        page = 1
        page_size = 100

        while True:
            url = f"{self.api_base}/repositories/{ns}/{repo}/tags"
            params = {
                'page': page,
                'page_size': page_size,
            }

            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                results = data.get('results', [])
                if not results:
                    break

                for tag_data in results:
                    tag = self._parse_tag(tag_data)
                    tags.append(tag)

                # Check if there's a next page
                if not data.get('next'):
                    break

                page += 1

                # Rate limiting
                time.sleep(self.rate_limit_delay)

            except requests.exceptions.RequestException as e:
                print(f"Error fetching tags for {ns}/{repo}: {e}")
                break

        return tags

    def get_tag_metadata(self, repository: str, tag: str, namespace: Optional[str] = None) -> ImageTag:
        """
        Get detailed metadata for a specific tag

        Args:
            repository: Repository name
            tag: Tag name
            namespace: Optional namespace

        Returns:
            ImageTag object with metadata
        """
        ns, repo = self._get_namespace(repository, namespace)

        url = f"{self.api_base}/repositories/{ns}/{repo}/tags/{tag}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            tag_data = response.json()

            return self._parse_tag(tag_data)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching tag {tag} for {ns}/{repo}: {e}")
            return ImageTag(name=tag)

    def _parse_tag(self, tag_data: dict) -> ImageTag:
        """
        Parse tag data from Docker Hub API response

        Args:
            tag_data: Tag data from API

        Returns:
            ImageTag object
        """
        name = tag_data.get('name', 'unknown')

        # Parse creation date
        created = None
        last_updated = tag_data.get('last_updated') or tag_data.get('tag_last_pushed')
        if last_updated:
            try:
                # Docker Hub uses ISO 8601 format
                created = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        # Get digest (from first image in images array)
        digest = None
        images = tag_data.get('images', [])
        if images and len(images) > 0:
            digest = images[0].get('digest')

        # Get size (sum of all layers)
        size = None
        if images:
            total_size = sum(img.get('size', 0) for img in images)
            if total_size > 0:
                size = total_size

        # Additional metadata
        metadata = {
            'full_size': tag_data.get('full_size'),
            'v2': tag_data.get('v2', True),
            'images': len(images),
        }

        return ImageTag(
            name=name,
            created=created,
            digest=digest,
            size=size,
            metadata=metadata,
        )

    def get_official_repositories(self, limit: int = 100) -> List[str]:
        """
        Get list of official Docker Hub repositories

        Args:
            limit: Maximum number of repositories to return

        Returns:
            List of repository names
        """
        repositories = []
        page = 1
        page_size = min(limit, 100)

        while len(repositories) < limit:
            url = f"{self.api_base}/repositories/library"
            params = {
                'page': page,
                'page_size': page_size,
            }

            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                results = data.get('results', [])
                if not results:
                    break

                for repo_data in results:
                    repo_name = repo_data.get('name')
                    if repo_name:
                        repositories.append(repo_name)

                if not data.get('next') or len(repositories) >= limit:
                    break

                page += 1
                time.sleep(self.rate_limit_delay)

            except requests.exceptions.RequestException as e:
                print(f"Error fetching official repositories: {e}")
                break

        return repositories[:limit]
