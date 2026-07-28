from fastapi import FastAPI

from app.api.router import api_router


app = FastAPI(
    title="RepoPilot API",
    description="AI Software Engineer Agent",
    version="0.1.0",
)


app.include_router(api_router)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }