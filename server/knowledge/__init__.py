"""
Knowledge Layer
===============

Integration with Obsidian vaults and knowledge management.

Components:
- vault_manager: Manage and query Obsidian vaults
- context_engine: Semantic search and context retrieval
- auto_docs: Auto-documentation for generated projects
"""

from server.knowledge.vault_manager import VaultManager
from server.knowledge.context_engine import ContextEngine
from server.knowledge.auto_docs import AutoDocumenter

__all__ = [
    "VaultManager",
    "ContextEngine",
    "AutoDocumenter",
]
