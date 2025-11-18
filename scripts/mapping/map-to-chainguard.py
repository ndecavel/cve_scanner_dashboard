#!/usr/bin/env python3
"""
Map upstream container images to Chainguard equivalents

Usage:
    python map-to-chainguard.py --input=customer-images.txt --output=mappings.yaml
"""

import argparse
import re
import yaml
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


class ChainGuardMapper:
    """Maps upstream images to Chainguard equivalents"""

    def __init__(self, mappings_file: str):
        """Load mappings configuration"""
        with open(mappings_file, 'r') as f:
            self.config = yaml.safe_load(f)

        self.image_mappings = self.config.get('image_mappings', {})
        self.tag_mappings = self.config.get('tag_mappings', {})
        self.registry_mappings = self.config.get('registry_mappings', {})
        self.special_cases = self.config.get('special_cases', {})
        self.defaults = self.config.get('defaults', {})

    def parse_image_ref(self, image_ref: str) -> Tuple[str, str, str]:
        """
        Parse image reference into registry, image, tag

        Examples:
            python:3.11 → ('', 'python', '3.11')
            docker.io/python:3.11 → ('docker.io', 'python', '3.11')
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
            tag = self.defaults.get('default_tag', 'latest')

        return registry, image, tag

    def map_image_name(self, image: str) -> Optional[str]:
        """Map upstream image name to Chainguard equivalent"""
        # Direct lookup
        if image in self.image_mappings:
            return self.image_mappings[image]

        # Try base name (for namespaced images like dotnet/runtime)
        base_name = image.split('/')[-1]
        if base_name in self.image_mappings:
            return self.image_mappings[base_name]

        return None

    def map_tag(self, image: str, tag: str) -> str:
        """Map upstream tag to Chainguard equivalent"""
        # Get tag mapping for this image
        tag_mapping = self.tag_mappings.get(image, {})

        # Direct lookup
        if tag in tag_mapping:
            return tag_mapping[tag]

        # Pattern-based replacement
        if 'pattern' in tag_mapping and 'replacement' in tag_mapping:
            pattern = tag_mapping['pattern']
            replacement = tag_mapping['replacement']

            match = re.match(pattern, tag)
            if match:
                return re.sub(pattern, replacement, tag)

        # Default: keep tag as-is
        return tag

    def get_registry_type(self, registry: str) -> str:
        """Get registry type (docker, mcr, quay, etc.)"""
        return self.registry_mappings.get(registry, 'unknown')

    def is_unsupported(self, image: str) -> bool:
        """Check if image is in unsupported list"""
        unsupported = self.special_cases.get('unsupported', [])
        return image in unsupported

    def get_alternative(self, image: str) -> Optional[str]:
        """Get alternative suggestion for unsupported images"""
        alternatives = self.special_cases.get('alternatives', {})
        return alternatives.get(image)

    def map_image(self, image_ref: str) -> Dict:
        """
        Map complete image reference to Chainguard equivalent

        Returns dict with mapping information
        """
        # Parse image reference
        registry, image, tag = self.parse_image_ref(image_ref)

        # Get registry type
        registry_type = self.get_registry_type(registry)

        # Check if unsupported
        if self.is_unsupported(image):
            alternative = self.get_alternative(image)
            return {
                'upstream': {
                    'full_ref': image_ref,
                    'registry': registry,
                    'registry_type': registry_type,
                    'image': image,
                    'tag': tag,
                },
                'chainguard': None,
                'status': 'unsupported',
                'message': f"No Chainguard equivalent for {image}",
                'alternative': alternative,
            }

        # Map image name
        cg_image = self.map_image_name(image)

        if not cg_image:
            return {
                'upstream': {
                    'full_ref': image_ref,
                    'registry': registry,
                    'registry_type': registry_type,
                    'image': image,
                    'tag': tag,
                },
                'chainguard': None,
                'status': 'not_found',
                'message': f"No mapping found for {image}",
                'alternative': None,
            }

        # Map tag
        base_image = image.split('/')[-1]  # For tag mapping lookup
        cg_tag = self.map_tag(base_image, tag)

        # Build Chainguard reference
        cg_full_ref = f"{cg_image}:{cg_tag}"

        return {
            'upstream': {
                'full_ref': image_ref,
                'registry': registry,
                'registry_type': registry_type,
                'image': image,
                'tag': tag,
            },
            'chainguard': {
                'full_ref': cg_full_ref,
                'registry': 'cgr.dev/chainguard',
                'image': cg_image.replace('cgr.dev/chainguard/', ''),
                'tag': cg_tag,
            },
            'status': 'mapped',
            'message': f"Mapped {image_ref} → {cg_full_ref}",
            'alternative': None,
        }


def main():
    parser = argparse.ArgumentParser(
        description='Map upstream images to Chainguard equivalents'
    )
    parser.add_argument('--input', required=True,
                        help='Input file with customer image list')
    parser.add_argument('--output', required=True,
                        help='Output YAML file with mappings')
    parser.add_argument('--mappings', default='config/chainguard-mappings.yaml',
                        help='Chainguard mappings config file')
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Load mapper
    mapper = ChainGuardMapper(args.mappings)

    # Read customer images
    with open(args.input, 'r') as f:
        lines = f.readlines()

    # Parse images (skip comments and empty lines)
    images = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            images.append(line)

    print(f"Mapping {len(images)} customer images to Chainguard equivalents...")

    # Map each image
    mappings = []
    stats = {'mapped': 0, 'unsupported': 0, 'not_found': 0}

    for image_ref in images:
        result = mapper.map_image(image_ref)
        mappings.append(result)

        status = result['status']
        stats[status] = stats.get(status, 0) + 1

        if args.verbose or status != 'mapped':
            print(f"  {result['message']}")
            if result['alternative']:
                print(f"    → Alternative: {result['alternative']}")

    # Write output
    output_data = {
        'customer_images': images,
        'mappings': mappings,
        'statistics': stats,
    }

    with open(args.output, 'w') as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    print(f"\nMapping complete!")
    print(f"  Mapped: {stats.get('mapped', 0)}")
    print(f"  Unsupported: {stats.get('unsupported', 0)}")
    print(f"  Not found: {stats.get('not_found', 0)}")
    print(f"\nMappings saved to: {args.output}")

    # Exit with error if any images couldn't be mapped
    if stats.get('not_found', 0) > 0 or stats.get('unsupported', 0) > 0:
        print("\nWARNING: Some images could not be mapped. Review output file.")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
