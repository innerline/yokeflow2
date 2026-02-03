"""
YokeFlow Specification Generation Module
=========================================

This module provides AI-powered specification generation capabilities for YokeFlow projects.

Components:
- spec_generator: Generate specifications from natural language descriptions
- spec_validator: Validate markdown specifications for required sections
- context_manager: Manage context files for projects
- context_manifest: Generate and manage context file manifests
"""

from .spec_generator import SpecGenerator
from .spec_validator import SpecValidator
from .context_manager import ContextManager
from .context_manifest import ContextManifest

__all__ = [
    "SpecGenerator",
    "SpecValidator",
    "ContextManager",
    "ContextManifest"
]