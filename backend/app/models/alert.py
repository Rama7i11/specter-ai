from typing import Any
from pydantic import BaseModel


class AlertIn(BaseModel):
    type: str
    ip: str
    severity: int
    timestamp: str
    raw_request: str
    matched_pattern: str


class CommandIn(BaseModel):
    command: int
    args: dict[str, Any] = {}
