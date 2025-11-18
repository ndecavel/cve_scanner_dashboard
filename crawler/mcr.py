"""
Microsoft Container Registry (MCR) crawler
"""

import requests
import time
from datetime import datetime
from typing import List, Optional
from .base import RegistryCrawler, ImageTag


class MCRCrawler(RegistryCrawler):
    """Crawler for Microsoft Container Registry (MCR)"""

    def __init__(self, rate_limit_delay: float = 0.5):
        """
        Initialize MCR crawler

        Args:
            rate_limit_delay: Delay between API requests (default: 0.5 sec)
        """
        super().__init__("https://mcr.microsoft.com", rate_limit_delay)
        self.api_base = "https://mcr.microsoft.com/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CVE-Scanner-Dashboard/0.1.0'
        })
        self._token_cache = {}

    def _get_auth_token(self, repository: str) -> Optional[str]:
        """
        Get authentication token for MCR API

        Args:
            repository: Repository name (e.g., "dotnet/runtime")

        Returns:
            Bearer token or None
        """
        # Check cache
        if repository in self._token_cache:
            return self._token_cache[repository]

        # MCR uses OCI Distribution API with bearer token authentication
        # First, try to access the repository to get the auth challenge
        url = f"{self.api_base}/{repository}/tags/list"

        try:
            response = self.session.get(url, timeout=30)

            # If we get 401, extract the WWW-Authenticate header
            if response.status_code == 401:
                auth_header = response.headers.get('WWW-Authenticate', '')

                # Parse the challenge: Bearer realm="...",service="...",scope="..."
                if 'Bearer' in auth_header:
                    import re
                    realm_match = re.search(r'realm="([^"]+)"', auth_header)
                    service_match = re.search(r'service="([^"]+)"', auth_header)
                    scope_match = re.search(r'scope="([^"]+)"', auth_header)

                    if realm_match:
                        realm = realm_match.group(1)
                        params = {}

                        if service_match:
                            params['service'] = service_match.group(1)
                        if scope_match:
                            params['scope'] = scope_match.group(1)

                        # Request token from the auth server
                        token_response = self.session.get(realm, params=params, timeout=30)
                        if token_response.status_code == 200:
                            token_data = token_response.json()
                            token = token_data.get('token') or token_data.get('access_token')

                            if token:
                                self._token_cache[repository] = token
                                return token

            # If 200, no auth needed (unlikely for MCR, but handle it)
            elif response.status_code == 200:
                return None

        except requests.exceptions.RequestException as e:
            print(f"Error getting auth token for {repository}: {e}")

        return None

    def _get_headers(self, repository: str) -> dict:
        """
        Get headers with auth token

        Args:
            repository: Repository name

        Returns:
            Headers dict
        """
        headers = {
            'User-Agent': 'CVE-Scanner-Dashboard/0.1.0',
            'Accept': 'application/vnd.docker.distribution.manifest.v2+json',
        }

        token = self._get_auth_token(repository)
        if token:
            headers['Authorization'] = f'Bearer {token}'

        return headers

    def list_tags(self, repository: str, namespace: Optional[str] = None) -> List[ImageTag]:
        """
        List all tags for an MCR repository

        Args:
            repository: Repository name (e.g., "dotnet/runtime", "dotnet/sdk")
            namespace: Not used for MCR (repositories include namespace)

        Returns:
            List of ImageTag objects
        """
        tags = []

        # Get list of tag names
        url = f"{self.api_base}/{repository}/tags/list"
        headers = self._get_headers(repository)

        try:
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            tag_names = data.get('tags', [])

            # For each tag, get detailed metadata
            # Note: This can be slow for repositories with many tags
            # Consider batching or lazy loading for production
            for tag_name in tag_names:
                time.sleep(self.rate_limit_delay)
                tag = self.get_tag_metadata(repository, tag_name)
                tags.append(tag)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching tags for {repository}: {e}")

        return tags

    def get_tag_metadata(self, repository: str, tag: str, namespace: Optional[str] = None) -> ImageTag:
        """
        Get detailed metadata for a specific tag

        Args:
            repository: Repository name (e.g., "dotnet/runtime")
            tag: Tag name (e.g., "8.0")
            namespace: Not used for MCR

        Returns:
            ImageTag object with metadata
        """
        # Get manifest to extract creation date and other metadata
        url = f"{self.api_base}/{repository}/manifests/{tag}"
        headers = self._get_headers(repository)

        try:
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Get digest from response headers
            digest = response.headers.get('Docker-Content-Digest')

            manifest = response.json()

            # For schema v2, we need to fetch the config blob to get created date
            created = None
            size = None

            if manifest.get('schemaVersion') == 2:
                # Get config digest
                config = manifest.get('config', {})
                config_digest = config.get('digest')

                if config_digest:
                    # Fetch config blob
                    config_url = f"{self.api_base}/{repository}/blobs/{config_digest}"
                    config_response = self.session.get(config_url, headers=headers, timeout=30)

                    if config_response.status_code == 200:
                        config_data = config_response.json()

                        # Parse created date
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
                'schemaVersion': manifest.get('schemaVersion'),
                'mediaType': manifest.get('mediaType'),
            }

            return ImageTag(
                name=tag,
                created=created,
                digest=digest,
                size=size,
                metadata=metadata,
            )

        except requests.exceptions.RequestException as e:
            print(f"Error fetching tag {tag} for {repository}: {e}")
            return ImageTag(name=tag)

    def list_repositories(self, prefix: str = "dotnet") -> List[str]:
        """
        List repositories with a given prefix

        Note: MCR doesn't provide a catalog API, so this returns a known list

        Args:
            prefix: Repository prefix (e.g., "dotnet", "azure")

        Returns:
            List of known repository names
        """
        # MCR doesn't expose a catalog endpoint
        # Return known popular repositories by prefix

        known_repos = {
            'dotnet': [
                'dotnet/runtime',
                'dotnet/sdk',
                'dotnet/aspnet',
                'dotnet/runtime-deps',
                'dotnet/monitor',
            ],
            'azure': [
                'azure-cli',
                'azure-functions/dotnet',
                'azure-functions/node',
                'azure-functions/python',
            ],
            'windows': [
                'windows/servercore',
                'windows/nanoserver',
            ],
        }

        return known_repos.get(prefix, [])
