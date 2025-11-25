from fastapi import APIRouter, Request, HTTPException, Depends
from .models import ProbeMetric, APIResponse
import logging
import json
import uuid

router = APIRouter()
logger = logging.getLogger("fiber-api")

async def get_redis(request: Request):
    return request.app.state.redis

@router.get("/status", response_model=APIResponse)
async def get_status(redis = Depends(get_redis)):
    """Check API and dependency health."""
    status_data = {"api": "ok", "redis": "unknown"}
    
    try:
        await redis.ping()
        status_data["redis"] = "ok"
    except Exception as e:
        status_data["redis"] = "error"
        logger.error(f"Redis health check failed: {e}")
        
    return APIResponse(status="ok", data=status_data)

@router.post("/push", response_model=APIResponse, status_code=202)
async def push_metrics(metric: ProbeMetric, redis = Depends(get_redis)):
    """Receive metrics from probe and enqueue for ETL."""
    try:
        payload = metric.model_dump(mode='json')
        message_id = str(uuid.uuid4())
        
        # Enqueue to Redis Stream or List
        # Using List for simplicity in MVP, Stream is better for production
        await redis.rpush("fiber:etl:queue", json.dumps(payload))
        
        logger.info(f"Queued metric from {metric.node_id}", extra={"node_id": metric.node_id})
        
        return APIResponse(
            status="accepted", 
            message="Metric queued for processing",
            data={"message_id": message_id}
        )
    except Exception as e:
        logger.error(f"Failed to enqueue metric: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
