# Module purpose: Define readiness HTTP API routes.

from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.readiness import (
    ReadinessResponse,
)
from app.services.hardening.readiness import (
    ReadinessService,
)


router = APIRouter(
    tags=["readiness"],
)


# Purpose: Report current HTTP API readiness.
@router.get(
    "/ready",
    response_model=ReadinessResponse,
)
async def ready(
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await ReadinessService().check(
        db=db
    )

    if result["status"] != "ready":
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return result
