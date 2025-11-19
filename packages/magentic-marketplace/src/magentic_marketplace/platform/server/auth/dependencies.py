"""Authentication dependencies for routes."""

from fastapi import HTTPException, Request

from .service import AuthService


async def get_current_agent_id(fastapi_request: Request) -> str:
    """Extract and validate the agent ID from the X-Agent-Id header."""
    agent_id = fastapi_request.headers.get("x-agent-id")

    if not agent_id:
        raise HTTPException(status_code=401, detail="X-Agent-Id header required")

    # Get auth service from app state
    auth_service: AuthService = fastapi_request.app.state.auth_service
    is_valid = await auth_service.validate_agent_id(agent_id)

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid agent ID")

    return agent_id
