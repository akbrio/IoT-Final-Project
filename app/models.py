"""Pydantic models used by the REST API (and for self-documenting /docs)."""
from pydantic import BaseModel


class SensorMeta(BaseModel):
    key: str
    label: str
    unit: str
    color: str
    topic: str


class Reading(BaseModel):
    sensor: str
    value: float
    ts: int  # epoch milliseconds (UTC)


class HistoryResponse(BaseModel):
    sensor: str
    unit: str
    minutes: int
    points: list[Reading]
