"""
Knowledge API Routes
====================

API endpoints for knowledge vault operations.
Provides REST API for MCP knowledge tools.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from server.utils.logging import get_logger
from server.knowledge import VaultManager, ContextEngine

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Global instances
_vault_manager: Optional[VaultManager] = None
_context_engine: Optional[ContextEngine] = None


def init_knowledge():
    """Initialize knowledge layer."""
    global _vault_manager, _context_engine

    _vault_manager = VaultManager()
    _context_engine = ContextEngine(vault_manager=_vault_manager)

    logger.info("knowledge.routes.initialized")


class NoteCreate(BaseModel):
    """Request to create a note."""
    note_path: str
    content: str
    vault_type: str = "agents"
    title: Optional[str] = None
    tags: List[str] = []


class NoteResponse(BaseModel):
    """Response for a note."""
    path: str
    title: str
    content: str
    tags: List[str] = []
    links: List[str] = []
    modified_at: Optional[str] = None


class SearchResult(BaseModel):
    """Search result."""
    note_path: str
    title: str
    score: float
    matches: List[str] = []


@router.get("/notes")
async def list_notes(
    vault_type: str = Query("default", description="Vault type"),
    pattern: str = Query("*.md", description="Glob pattern"),
    limit: int = Query(50, ge=1, le=500)
):
    """List notes in a vault."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    notes = _vault_manager.list_notes(vault_type=vault_type, pattern=pattern, limit=limit)

    return {
        "notes": [
            {
                "path": n.path,
                "title": n.title,
                "tags": n.tags,
                "modified_at": n.modified_at.isoformat() if n.modified_at else None
            }
            for n in notes
        ],
        "count": len(notes),
        "vault_type": vault_type
    }


@router.get("/notes/{note_path:path}")
async def get_note(
    note_path: str,
    vault_type: str = Query("default", description="Vault type")
):
    """Get a specific note."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    note = _vault_manager.get_note(note_path, vault_type=vault_type)

    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_path}")

    return NoteResponse(
        path=note.path,
        title=note.title,
        content=note.content,
        tags=note.tags,
        links=note.links,
        modified_at=note.modified_at.isoformat() if note.modified_at else None
    )


@router.post("/notes")
async def create_note(request: NoteCreate):
    """Create or update a note."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    frontmatter = {}
    if request.title:
        frontmatter["title"] = request.title
    if request.tags:
        frontmatter["tags"] = request.tags

    success = _vault_manager.write_note(
        note_path=request.note_path,
        content=request.content,
        vault_type=request.vault_type,
        frontmatter=frontmatter if frontmatter else None
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to create note")

    return {
        "success": True,
        "path": request.note_path,
        "vault_type": request.vault_type
    }


@router.delete("/notes/{note_path:path}")
async def delete_note(
    note_path: str,
    vault_type: str = Query("default", description="Vault type")
):
    """Delete a note."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    success = _vault_manager.delete_note(note_path, vault_type=vault_type)

    if not success:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_path}")

    return {"success": True, "path": note_path}


@router.get("/search")
async def search_notes(
    query: str,
    vault_type: str = Query("default", description="Vault type"),
    limit: int = Query(10, ge=1, le=100)
):
    """Search notes by content."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    results = _vault_manager.search(query=query, vault_type=vault_type, limit=limit)

    return {
        "query": query,
        "results": [
            {
                "note_path": r.note.path,
                "title": r.note.title,
                "score": r.score,
                "matches": r.matches
            }
            for r in results
        ],
        "count": len(results),
        "vault_type": vault_type
    }


@router.get("/notes/{note_path:path}/related")
async def find_related(
    note_path: str,
    vault_type: str = Query("default", description="Vault type"),
    max_depth: int = Query(2, ge=1, le=5)
):
    """Find related notes via links."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    related = _vault_manager.find_related(note_path, vault_type=vault_type, max_depth=max_depth)

    return {
        "source": note_path,
        "related": [
            {
                "path": n.path,
                "title": n.title,
                "tags": n.tags
            }
            for n in related
        ],
        "count": len(related),
        "max_depth": max_depth
    }


@router.get("/stats")
async def get_stats(vault_type: str = Query("default", description="Vault type")):
    """Get vault statistics."""
    if not _vault_manager:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    return _vault_manager.get_stats(vault_type=vault_type)


@router.get("/context/{task_id}")
async def get_task_context(
    task_id: str,
    description: str = Query(..., description="Task description"),
    vault_type: str = Query("default", description="Vault type")
):
    """Get context for a task."""
    if not _context_engine:
        raise HTTPException(status_code=503, detail="Knowledge layer not initialized")

    context = await _context_engine.get_context_for_task(
        task_id=task_id,
        task_description=description,
        vault_type=vault_type
    )

    return {
        "task_id": task_id,
        "chunks": [
            {
                "source": c.source,
                "content": c.content[:500] + "..." if len(c.content) > 500 else c.content,
                "relevance_score": c.relevance_score
            }
            for c in context.chunks
        ],
        "sources": context.sources,
        "total_tokens": context.total_tokens
    }
