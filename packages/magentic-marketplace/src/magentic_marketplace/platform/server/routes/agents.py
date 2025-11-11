"""Agent-related routes."""

import sqlite3
import uuid
from datetime import UTC, datetime

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from ...database.base import DatabaseTooBusyError
from ...database.models import AgentRow
from ...database.queries.base import RangeQueryParams
from ...shared.models import (
    AgentGetResponse,
    AgentListResponse,
    AgentProfile,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
)
from ..server import get_auth_service, get_database

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/register", response_model=AgentRegistrationResponse)
async def register_agent(
    request: AgentRegistrationRequest, fastapi_request: Request
) -> AgentRegistrationResponse:
    """Register a new agent."""
    db = get_database(fastapi_request)
    get_auth_service(fastapi_request)

    try:
        # Generate auth token before creating agent
        token = str(uuid.uuid4())

        db_agent = AgentRow(
            id=request.agent.id,  # Use the provided agent ID
            created_at=datetime.now(UTC),
            data=request.agent,
            auth_token=token,  # Include token during creation
        )
        created_db_agent = await db.agents.create(db_agent)

        # Return the agent with the generated ID and token
        request.agent.id = created_db_agent.id
        return AgentRegistrationResponse(agent=request.agent, token=token)
    except DatabaseTooBusyError as e:
        raise HTTPException(
            status_code=429, detail=f"Database too busy: {e.message}"
        ) from e
    except (sqlite3.IntegrityError, asyncpg.UniqueViolationError) as e:
        raise HTTPException(
            status_code=409,
            detail=f"Agent with ID '{request.agent.id}' already exists",
        ) from e


@router.get("", response_model=AgentListResponse)
async def get_agents(
    fastapi_request: Request,
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1),
) -> AgentListResponse:
    """Get all agents with optional pagination."""
    db = get_database(fastapi_request)
    try:
        query_params = RangeQueryParams(offset=offset, limit=limit)
        db_agents = await db.agents.get_all(query_params)
        total = await db.agents.count()
        has_more = limit is not None and len(db_agents) == limit

        # Extract agents from db agents with IDs
        agents = [AgentProfile.model_validate(db_agent.data) for db_agent in db_agents]

        return AgentListResponse(
            items=agents, total=total, offset=offset, limit=limit, has_more=has_more
        )
    except DatabaseTooBusyError as e:
        raise HTTPException(
            status_code=429, detail=f"Database too busy: {e.message}"
        ) from e


@router.get("/{agent_id}", response_model=AgentGetResponse)
async def get_agent(agent_id: str, fastapi_request: Request) -> AgentGetResponse:
    """Get a specific agent by ID."""
    db = get_database(fastapi_request)

    try:
        db_agent = await db.agents.get_by_id(agent_id)
        if not db_agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent = AgentProfile.model_validate(db_agent.data)
        return AgentGetResponse(agent=agent)
    except DatabaseTooBusyError as e:
        raise HTTPException(
            status_code=429, detail=f"Database too busy: {e.message}"
        ) from e
