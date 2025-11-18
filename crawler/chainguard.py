"""
Chainguard registry crawler

Chainguard images are hosted at cgr.dev and use the OCI Distribution Spec.
This crawler uses the standard Docker Registry V2 API to fetch tag information.
"""

import requests
import time
from datetime import datetime
from typing import List, Optional
from .base import RegistryCrawler, ImageTag


class ChainguardCrawler(RegistryCrawler):
    """Crawler for Chainguard registry (cgr.dev)"""

    def __init__(self, rate_limit_delay: float = 1.0):
        """
        Initialize Chainguard crawler

        Args:
            rate_limit_delay: Delay between API requests (default: 1.0 sec for rate limits)
        """
        super().__init__("https://cgr.dev", rate_limit_delay)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CVE-Scanner-Dashboard/0.1.0'
        })

    def _get_auth_token(self, repository: str) -> Optional[str]:
        """
        Get authentication token for Chainguard registry

        Args:
            repository: Repository name (e.g., "chainguard/python")

        Returns:
            Bearer token or None if not needed
        """
        # Chainguard public images use anonymous token authentication
        auth_url = f"https://cgr.dev/token?scope=repository:{repository}:pull"

        try:
            response = self.session.get(auth_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('token')
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not get auth token for {repository}: {e}")
            return None

    def _parse_repository(self, repository: str) -> str:
        """
        Parse repository to ensure proper format

        Args:
            repository: Repository name (e.g., "python", "chainguard/python")

        Returns:
            Properly formatted repository name (e.g., "chainguard/python")
        """
        # If repository doesn't include namespace, assume "chainguard"
        if '/' not in repository:
            return f"chainguard/{repository}"
        return repository

    def list_tags(self, repository: str, namespace: Optional[str] = None) -> List[ImageTag]:
        """
        List all tags for a Chainguard repository using OCI Distribution API

        Args:
            repository: Repository name (e.g., "python", "node")
            namespace: Optional namespace (default: "chainguard")

        Returns:
            List of ImageTag objects
        """
        # Format repository with namespace
        if namespace:
            full_repo = f"{namespace}/{repository}"
        else:
            full_repo = self._parse_repository(repository)

        # Get auth token
        token = self._get_auth_token(full_repo)
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}'
            })

        # Use OCI Distribution API to list tags
        tags_url = f"{self.base_url}/v2/{full_repo}/tags/list"

        try:
            response = self.session.get(tags_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            tag_names = data.get('tags', [])
            if not tag_names:
                print(f"No tags found for {full_repo}")
                return []

            # Fetch metadata for each tag
            tags = []
            for tag_name in tag_names:
                # Rate limiting
                time.sleep(self.rate_limit_delay)

                tag = self.get_tag_metadata(repository, tag_name, namespace)
                if tag:
                    tags.append(tag)

            return tags

        except requests.exceptions.RequestException as e:
            print(f"Error fetching tags for {full_repo}: {e}")
            return []

    def get_tag_metadata(self, repository: str, tag: str, namespace: Optional[str] = None) -> ImageTag:
        """
        Get detailed metadata for a specific tag using OCI Distribution API

        Args:
            repository: Repository name
            tag: Tag name
            namespace: Optional namespace

        Returns:
            ImageTag object with metadata
        """
        # Format repository with namespace
        if namespace:
            full_repo = f"{namespace}/{repository}"
        else:
            full_repo = self._parse_repository(repository)

        # Get auth token
        token = self._get_auth_token(full_repo)
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}'
            })

        # Get manifest to extract creation date and size
        manifest_url = f"{self.base_url}/v2/{full_repo}/manifests/{tag}"

        try:
            # Request with Docker manifest v2 schema 2 acceptance
            headers = {
                'Accept': 'application/vnd.docker.distribution.manifest.v2+json'
            }
            response = self.session.get(manifest_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Get digest from response header
            digest = response.headers.get('Docker-Content-Digest')

            manifest = response.json()

            # Extract config digest to get creation date
            config_digest = manifest.get('config', {}).get('digest')
            created = None
            size = None

            if config_digest:
                # Fetch blob/config to get creation timestamp
                config_url = f"{self.base_url}/v2/{full_repo}/blobs/{config_digest}"
                config_response = self.session.get(config_url, timeout=30)

                if config_response.status_code == 200:
                    config_data = config_response.json()

                    # Get creation date from config
                    created_str = config_data.get('created')
                    if created_str:
                        try:
                            created = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            pass

                    # Calculate total size from layers
                    layers = manifest.get('layers', [])
                    if layers:
                        size = sum(layer.get('size', 0) for layer in layers)

            metadata = {
                'manifest_version': manifest.get('schemaVersion'),
                'media_type': manifest.get('mediaType'),
                'config_digest': config_digest,
            }

            return ImageTag(
                name=tag,
                created=created,
                digest=digest,
                size=size,
                metadata=metadata,
            )

        except requests.exceptions.RequestException as e:
            print(f"Error fetching metadata for {full_repo}:{tag}: {e}")
            # Return basic tag info even if we can't get full metadata
            return ImageTag(name=tag)

    def list_repositories(self, namespace: str = "chainguard", limit: int = 100) -> List[str]:
        """
        List repositories in Chainguard registry

        Note: The OCI Distribution API doesn't provide a standard way to list
        repositories, so this is a best-effort implementation.

        Args:
            namespace: Namespace to search (default: "chainguard")
            limit: Maximum number of repositories to return

        Returns:
            List of repository names
        """
        # The catalog endpoint may not be available on all registries
        catalog_url = f"{self.base_url}/v2/_catalog"

        try:
            response = self.session.get(catalog_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            repositories = data.get('repositories', [])

            # Filter by namespace if specified
            if namespace:
                repositories = [r for r in repositories if r.startswith(f"{namespace}/")]

            return repositories[:limit]

        except requests.exceptions.RequestException as e:
            print(f"Error fetching repository catalog: {e}")
            print("Note: Catalog endpoint may not be available. Use known image names instead.")
            return []
