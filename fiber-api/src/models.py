from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
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
    def validate_uuid(cls, v):
        # Simple UUID-like check
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', v):
            raise ValueError('node_id must be a valid UUID')
        return v

class APIResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None
