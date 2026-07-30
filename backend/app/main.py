# Module purpose: Create and configure the FastAPI application.

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.api.routes.readiness import (
    router as readiness_router,
)
from app.observability.correlation import (
    correlation_context,
)
from app.observability.logging import (
    configure_task_logging,
)
from app.services.hardening.limits import (
    validate_startup_configuration,
)


validate_startup_configuration()
configure_task_logging(
    settings.task_log_level
)


app = FastAPI(
    title="RepoPilot API",
    description="AI Software Engineer Agent",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url.rstrip("/")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Content-Type",
        "X-CSRF-Token",
        "X-Correlation-ID",
        "X-Request-ID",
    ],
    expose_headers=[
        "X-Correlation-ID",
        "X-Error-Code",
        "X-Request-ID",
    ],
)


app.include_router(api_router)
app.include_router(readiness_router)


# Purpose: Add correlation id for the main workflow.
@app.middleware("http")
async def add_correlation_id(
    request: Request,
    call_next,
):
    incoming_correlation_id = request.headers.get(
        "X-Correlation-ID"
    )
    request_id = request.headers.get(
        "X-Request-ID"
    )

    with correlation_context(
        correlation_id=incoming_correlation_id,
        request_id=request_id,
    ) as correlation_id:
        response = await call_next(
            request
        )
        response.headers[
            "X-Correlation-ID"
        ] = correlation_id
        return response


# Purpose: Report current main readiness.
@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
