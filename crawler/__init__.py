"""
CVE Scanner Dashboard - Registry Crawler

Multi-registry crawler for finding historical image tags.
Supports Docker Hub, Microsoft Container Registry (MCR), Quay.io, and more.
"""

from .base import RegistryCrawler, ImageTag
from .docker_hub import DockerHubCrawler
from .mcr import MCRCrawler
from .resolver import HistoricalTagResolver

__all__ = [
    'RegistryCrawler',
    'ImageTag',
    'DockerHubCrawler',
    'MCRCrawler',
    'HistoricalTagResolver',
]

__version__ = '0.1.0'
