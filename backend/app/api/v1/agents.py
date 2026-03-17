"""Agent template and execution endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import structlog

from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.agent import AgentTemplate, AgentExecution, AgentStatus
from app.services.agent_executor import execute_agent

logger = structlog.get_logger()
router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRunRequest(BaseModel):
    input: str = Field(..., min_length=1, description="User input for the agent")
    model: str | None = Field(default=None, description="Model override")


class AgentTemplateCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    category: str = "general"
    system_prompt: str
    default_model: str | None = None
    constraints: dict | None = None


@router.get("/templates")
async def list_templates(
    category: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available agent templates."""
    stmt = select(AgentTemplate).where(
        AgentTemplate.enabled == True,
        (AgentTemplate.org_id == tenant.org_id) | (AgentTemplate.is_system == True),
    )
    if category:
        stmt = stmt.where(AgentTemplate.category == category)
    stmt = stmt.order_by(AgentTemplate.name)

    result = await db.execute(stmt)
    templates = result.scalars().all()

    return {
        "data": [
            {
                "id": str(t.id),
                "name": t.name,
                "slug": t.slug,
                "description": t.description,
                "category": t.category,
                "default_model": t.default_model,
                "constraints": t.constraints,
                "is_system": t.is_system,
            }
            for t in templates
        ]
    }


@router.get("/templates/{slug}")
async def get_template(
    slug: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent template details."""
    result = await db.execute(
        select(AgentTemplate).where(
            AgentTemplate.slug == slug,
            AgentTemplate.enabled == True,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Agent template not found")

    return {
        "data": {
            "id": str(template.id),
            "name": template.name,
            "slug": template.slug,
            "description": template.description,
            "category": template.category,
            "system_prompt": template.system_prompt,
            "tools": template.tools,
            "constraints": template.constraints,
            "default_model": template.default_model,
        }
    }


@router.post("/templates", status_code=201)
async def create_template(
    req: AgentTemplateCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom agent template (org-specific)."""
    template = AgentTemplate(
        org_id=tenant.org_id,
        name=req.name,
        slug=req.slug,
        description=req.description,
        category=req.category,
        system_prompt=req.system_prompt,
        default_model=req.default_model,
        constraints=req.constraints or {},
        created_by=tenant.user_id,
    )
    db.add(template)
    await db.flush()

    return {"data": {"id": str(template.id), "slug": template.slug, "name": template.name}}


@router.post("/run/{slug}")
async def run_agent(
    slug: str,
    req: AgentRunRequest,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an agent template."""
    # Find template
    result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.slug == slug, AgentTemplate.enabled == True)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Agent template not found")

    # Get model router
    from app.main import model_router

    execution, agent_result = await execute_agent(
        db=db,
        model_router=model_router,
        template=template,
        user_input=req.input,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        model_override=req.model,
    )

    await db.commit()

    return {
        "data": {
            "execution_id": str(execution.id),
            "status": execution.status.value,
            "output": agent_result.output,
            "steps": agent_result.steps,
            "usage": {
                "total_tokens": agent_result.total_tokens,
                "total_cost_usd": round(agent_result.total_cost, 6),
                "duration_ms": agent_result.duration_ms,
                "model": agent_result.model_id,
            },
        }
    }


@router.get("/executions")
async def list_executions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's agent executions."""
    stmt = select(AgentExecution).where(
        AgentExecution.org_id == tenant.org_id,
        AgentExecution.user_id == tenant.user_id,
    )
    if status:
        stmt = stmt.where(AgentExecution.status == AgentStatus(status))
    stmt = stmt.order_by(desc(AgentExecution.created_at)).offset(offset).limit(limit)

    result = await db.execute(stmt)
    executions = result.scalars().all()

    # Get template names
    template_ids = {e.template_id for e in executions}
    template_names = {}
    if template_ids:
        tmpl_result = await db.execute(
            select(AgentTemplate.id, AgentTemplate.name).where(AgentTemplate.id.in_(template_ids))
        )
        template_names = {r.id: r.name for r in tmpl_result.all()}

    return {
        "data": [
            {
                "id": str(e.id),
                "template_name": template_names.get(e.template_id, "Unknown"),
                "status": e.status.value,
                "total_tokens": e.total_tokens,
                "duration_ms": e.duration_ms,
                "created_at": e.created_at.isoformat(),
                "output_preview": (e.output_data or {}).get("result", "")[:200] if e.output_data else None,
            }
            for e in executions
        ]
    }


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full execution details."""
    result = await db.execute(
        select(AgentExecution).where(
            AgentExecution.id == execution_id,
            AgentExecution.org_id == tenant.org_id,
        )
    )
    e = result.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "data": {
            "id": str(e.id),
            "template_id": str(e.template_id),
            "status": e.status.value,
            "input_data": e.input_data,
            "output_data": e.output_data,
            "steps": e.steps,
            "total_tokens": e.total_tokens,
            "duration_ms": e.duration_ms,
            "error": e.error,
            "model_id": e.model_id,
            "created_at": e.created_at.isoformat(),
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        }
    }
