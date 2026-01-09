from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import re

class ProbeMetric(BaseModel):
    node_id: str = Field(..., description="Unique identifier for the probe node")
    country: str = Field(..., pattern="^[A-Z]{2}$", description="ISO 3166-1 alpha-2 country code")
    region: str = Field(..., description="Human-readable region name")
    latency_ms: float = Field(..., ge=0, le=10000, description="Round-trip latency in milliseconds")
    uptime_pct: float = Field(..., ge=0, le=100, description="Uptime percentage")
    packet_loss: float = Field(..., ge=0, le=100, description="Packet loss percentage")
    timestamp: datetime = Field(..., description="ISO 8601 timestamp (UTC)")
    target_host: Optional[str] = None
    probe_type: Optional[str] = "ping"
    metadata: Optional[Dict[str, Any]] = None

    @field_validator('node_id')
    def validate_node_id(cls, v):
        # Allow any valid string identifier (1-50 chars, alphanumeric with hyphens)
        if not v or len(v) > 50:
            raise ValueError('node_id must be 1-50 characters')
        return v

class Node(BaseModel):
    node_id: str = Field(..., description="Unique identifier for the probe node")
    status: str = Field(..., description="Lifecycle state: registered, reporting, inactive, deleted")
    country: str = Field(..., pattern="^[A-Z]{2}$")
    region: str
    lat: float
    lng: float
    last_seen: Optional[datetime] = None

    lat: float
    lng: float
    last_seen: Optional[datetime] = None

class AggregatedMetric(BaseModel):
    dimension: str = Field(..., description="Grouping key (Region name or Node ID)")
    avg_latency: float
    min_latency: float
    max_latency: float
    p95_latency: float
    avg_packet_loss: float
    downtime_intervals: int
    reporting_count: int
    availability_pct: float

class BatchPayload(BaseModel):
    """Batch of metrics from a probe."""
    node_id: str
    metrics: List[ProbeMetric]

class APIResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None
    meta: Optional[Dict[str, Any]] = None
