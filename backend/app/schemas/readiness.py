from pydantic import BaseModel


class ReadinessComponent(BaseModel):
    status: str
    details: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, ReadinessComponent]
