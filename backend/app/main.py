from fastapi import (
    FastAPI,
    Request,
)

from app.api.router import api_router
from app.api.routes.readiness import (
    router as readiness_router,
)
from app.observability.correlation import (
    correlation_context,
)
from app.services.hardening.limits import (
    validate_startup_configuration,
)


validate_startup_configuration()


app = FastAPI(
    title="RepoPilot API",
    description="AI Software Engineer Agent",
    version="0.1.0",
)


app.include_router(api_router)
app.include_router(readiness_router)


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


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
