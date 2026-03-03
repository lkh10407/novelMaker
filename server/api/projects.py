"""Project CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..storage import create_project, list_projects, get_project, delete_project, update_meta

router = APIRouter()


class CreateProjectRequest(BaseModel):
    title: str
    logline: str
    total_chapters: int = 3


class UpdateProjectRequest(BaseModel):
    title: str | None = None
    logline: str | None = None


@router.get("")
async def list_all_projects():
    """List all projects."""
    return list_projects()


@router.post("")
async def create_new_project(req: CreateProjectRequest):
    """Create a new project."""
    return create_project(title=req.title, logline=req.logline, total_chapters=req.total_chapters)


@router.get("/{project_id}")
async def get_project_detail(project_id: str):
    """Get a project with its full state."""
    proj = get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.put("/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest):
    """Update project metadata."""
    updates = req.model_dump(exclude_none=True)
    result = update_meta(project_id, **updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.delete("/{project_id}")
async def delete_existing_project(project_id: str):
    """Delete a project."""
    if not delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}
