# Module purpose: Define validated readiness API payload schemas.

from pydantic import BaseModel


# Purpose: Validate and represent readiness component data.
class ReadinessComponent(BaseModel):
    status: str
    details: str | None = None


# Purpose: Validate and represent readiness response data.
class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, ReadinessComponent]
