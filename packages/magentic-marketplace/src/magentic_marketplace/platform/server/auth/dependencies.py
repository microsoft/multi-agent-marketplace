"""Authentication dependencies for routes."""

from fastapi import HTTPException, Request

from .service import AuthService


async def get_current_agent_id(fastapi_request: Request) -> str:
    """Extract and validate the agent ID from the Authorization header."""
    authorization = fastapi_request.headers.get("authorization")

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Invalid authorization format. Use 'Bearer <token>'"
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    # Get auth service from app state
    auth_service: AuthService = fastapi_request.app.state.auth_service
    agent_id = await auth_service.validate_token(token)

    if not agent_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return agent_id
