"""Agent execution service — runs agent templates with governance."""

import uuid
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.agent import AgentTemplate, AgentExecution, AgentStatus
from app.services.model_router import ModelRouter
from app.services.providers.base import ChatMessage, ChatResponse
from app.services.content_safety import check_content_safety

logger = structlog.get_logger()


@dataclass
class AgentStep:
    step_index: int
    action: str
    input_text: str | None = None
    output_text: str | None = None
    tokens_used: int = 0
    duration_ms: int = 0
    error: str | None = None


@dataclass
class AgentResult:
    success: bool
    output: str
    steps: list[dict]
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_ms: int = 0
    model_id: str | None = None


async def execute_agent(
    db: AsyncSession,
    model_router: ModelRouter,
    template: AgentTemplate,
    user_input: str,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    model_override: str | None = None,
) -> tuple[AgentExecution, AgentResult]:
    """
    Execute an agent template with the given input.
    Returns the execution record and result.
    """
    model_id = model_override or template.default_model
    constraints = template.constraints or {}
    max_tokens = constraints.get("max_tokens", 8192)
    max_steps = constraints.get("max_steps", 5)

    # Create execution record
    execution = AgentExecution(
        org_id=org_id,
        user_id=user_id,
        template_id=template.id,
        status=AgentStatus.running,
        input_data={"user_input": user_input},
        model_id=model_id,
    )
    db.add(execution)
    await db.flush()

    start_time = time.monotonic()
    steps = []
    total_tokens = 0
    total_cost = 0.0
    final_output = ""

    try:
        # Content safety check on input
        safety = check_content_safety(user_input)
        if not safety.safe:
            execution.status = AgentStatus.failed
            execution.error = "Input blocked by content safety"
            execution.completed_at = datetime.now(timezone.utc)
            await db.flush()
            return execution, AgentResult(
                success=False,
                output="Input was blocked by content safety policy.",
                steps=[{"step": 0, "action": "safety_check", "result": "blocked", "flags": safety.flags}],
            )

        # Build messages
        messages = [
            ChatMessage(role="system", content=template.system_prompt),
            ChatMessage(role="user", content=user_input),
        ]

        # Execute main model call
        step_start = time.monotonic()
        response = await model_router.chat(messages, model_id, max_tokens=max_tokens, temperature=0.7)

        step_duration = int((time.monotonic() - step_start) * 1000)
        step_tokens = response.input_tokens + response.output_tokens
        total_tokens += step_tokens

        # Calculate cost
        try:
            _, _, defn = model_router.resolve_model(model_id)
            cost = (response.input_tokens / 1000 * defn.input_cost_per_1k) + (response.output_tokens / 1000 * defn.output_cost_per_1k)
            total_cost += cost
        except Exception:
            cost = 0

        steps.append({
            "step": 1,
            "action": "model_call",
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost_usd": round(cost, 6),
            "duration_ms": step_duration,
        })

        final_output = response.content

        # Success
        duration_ms = int((time.monotonic() - start_time) * 1000)
        execution.status = AgentStatus.completed
        execution.output_data = {"result": final_output}
        execution.steps = steps
        execution.total_tokens = total_tokens
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(timezone.utc)
        await db.flush()

        return execution, AgentResult(
            success=True,
            output=final_output,
            steps=steps,
            total_tokens=total_tokens,
            total_cost=total_cost,
            duration_ms=duration_ms,
            model_id=model_id,
        )

    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        execution.status = AgentStatus.failed
        execution.error = str(e)
        execution.steps = steps
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(timezone.utc)
        await db.flush()

        logger.error("agent_execution_failed", template=template.slug, error=str(e))
        return execution, AgentResult(
            success=False,
            output=f"Agent execution failed: {str(e)}",
            steps=steps,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
