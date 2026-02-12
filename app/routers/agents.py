from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import uuid4
from typing import Dict
from pydantic import BaseModel
from datetime import datetime
import asyncio
from app.database import get_db
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/agents", tags=["Agents"])

agent_tasks: Dict[str, dict] = {}


class AgentTaskRequest(BaseModel):
    deal_id: str
    flow_type: str
    document_id: str | None = None


class AgentTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class AgentTaskStatus(BaseModel):
    task_id: str
    status: str
    step: str | None = None
    step_number: int = 0
    total_steps: int = 0
    result: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str


async def run_agent_task_async(task_id: str, deal_id: str, flow_type: str, **kwargs):
    """Run agent flow asynchronously."""
    try:
        agent_tasks[task_id]["status"] = "running"
        agent_tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()

        from app.agents.orchestrator import run_agent_flow
        await run_agent_flow(task_id=task_id, deal_id=deal_id, flow_type=flow_type, **kwargs)

        agent_tasks[task_id]["status"] = "completed"
        agent_tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()

    except Exception as e:
        agent_tasks[task_id]["status"] = "failed"
        agent_tasks[task_id]["error"] = str(e)
        agent_tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()
        import traceback
        traceback.print_exc()


@router.post("/run", response_model=AgentTaskResponse)
async def run_agent_task(
    request: AgentTaskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Start an agent flow. Takes deal_id and flow_type.
    Creates a task_id, launches the appropriate agent as an async task.
    Returns AgentTaskResponse with task_id.
    """
    task_id = str(uuid4())

    agent_tasks[task_id] = {
        "task_id": task_id,
        "deal_id": request.deal_id,
        "flow_type": request.flow_type,
        "status": "queued",
        "step": "initializing",
        "step_number": 0,
        "total_steps": 0,
        "result": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    # Launch async task (not background_tasks which runs sync)
    kwargs = {}
    if request.document_id:
        kwargs["document_id"] = request.document_id
    asyncio.create_task(run_agent_task_async(task_id, request.deal_id, request.flow_type, **kwargs))

    return AgentTaskResponse(
        task_id=task_id,
        status="queued",
        message=f"Agent task {task_id} queued for flow_type={request.flow_type}",
    )


@router.get("/status/{task_id}", response_model=AgentTaskStatus)
def get_agent_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get status of a running agent task.
    Also checks the orchestrator task_store for real-time step info.
    """
    if task_id not in agent_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = agent_tasks[task_id]

    # Merge in orchestrator progress if available
    from app.agents.orchestrator import task_store
    orch_status = task_store.get(task_id, {})

    # Extract result data from orchestrator (has compliance_score, proposal_id, etc.)
    orch_data = orch_status.get("data", {})
    result_str = None
    if orch_data:
        import json
        try:
            result_str = json.dumps(orch_data)
        except Exception:
            result_str = str(orch_data)

    return AgentTaskStatus(
        task_id=task["task_id"],
        status=orch_status.get("status", task["status"]),
        step=orch_status.get("step", task.get("step")),
        step_number=orch_status.get("step_number", task.get("step_number", 0)),
        total_steps=orch_status.get("total_steps", task.get("total_steps", 0)),
        result=result_str or task.get("result"),
        error=task.get("error") or orch_status.get("message") if orch_status.get("status") == "failed" else task.get("error"),
        created_at=task["created_at"],
        updated_at=task["updated_at"],
    )
