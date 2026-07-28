from fastapi import FastAPI

app = FastAPI(
    title="RepoPilot API",
    description="AI Software Engineer Agent",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "name": "RepoPilot",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }