import os
import json
import logging
import uuid
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

# Prometheus Metrics (if client available)
try:
    from prometheus_client import Counter, Histogram, Gauge
    ALERTS_GENERATED_TOTAL = Counter('alerts_generated_total', 'Total alerts generated', ['node_id', 'severity'])
    ALERTS_SENT_TOTAL = Counter('alerts_sent_total', 'Total alerts successfully dispatched', ['severity'])
    ALERTS_DROPPED_TOTAL = Counter('alerts_dropped_total', 'Alerts dropped', ['reason'])
    WEBHOOK_FAILURES_TOTAL = Counter('webhook_failures_total', 'Webhook dispatch failures')
    ALERTS_DLQ_TOTAL = Counter('alerts_dlq_total', 'Alerts sent to DLQ')
except ImportError:
    class MockMetric:
        def labels(self, **kwargs): return self
        def inc(self, amount=1): pass
    ALERTS_GENERATED_TOTAL = MockMetric()
    ALERTS_SENT_TOTAL = MockMetric()
    ALERTS_DROPPED_TOTAL = MockMetric()
    WEBHOOK_FAILURES_TOTAL = MockMetric()
    ALERTS_DLQ_TOTAL = MockMetric()

# Configure Logger
logger = logging.getLogger("fiber-etl")

# --- Configuration ---
# Thresholds (Environment Aware)
ALERT_LATENCY_WARN = float(os.getenv("ALERT_LATENCY_WARN", "200.0"))
ALERT_LATENCY_CRIT = float(os.getenv("ALERT_LATENCY_CRIT", "500.0"))
ALERT_LOSS_WARN = float(os.getenv("ALERT_LOSS_WARN", "1.0"))
ALERT_LOSS_CRIT = float(os.getenv("ALERT_LOSS_CRIT", "5.0"))
ALERT_UPTIME_WARN = float(os.getenv("ALERT_UPTIME_WARN", "95.0"))

# Settings
ALERT_LOOP_COOLDOWN_SEC = int(os.getenv("ALERT_LOOP_COOLDOWN_SEC", "900")) # 15 mins
GLOBAL_RATE_LIMIT = int(os.getenv("ALERT_GLOBAL_RATE_LIMIT", "100")) # per hour
NODE_RATE_LIMIT = int(os.getenv("ALERT_NODE_RATE_LIMIT", "5")) # per hour

class Severity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"

class Alert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str
    severity: Severity
    metric_name: str
    value: float
    threshold: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: str

    def get_dedup_key(self) -> str:
        """Unique key for deduplication: node:metric:severity"""
        return f"alert:dedup:{self.node_id}:{self.metric_name}:{self.severity.value}"

# --- Rules ---

class AlertRule(ABC):
    @abstractmethod
    def evaluate(self, metric: dict) -> List[Alert]:
        pass

class ThresholdRule(AlertRule):
    def __init__(self, metric_key: str, operator: str, threshold: float, severity: Severity, msg_template: str):
        self.metric_key = metric_key
        self.operator = operator
        self.threshold = threshold
        self.severity = severity
        self.msg_template = msg_template

    def evaluate(self, metric: dict) -> List[Alert]:
        value = metric.get(self.metric_key)
        if value is None:
            return []

        triggered = False
        if self.operator == ">" and value > self.threshold:
            triggered = True
        elif self.operator == "<" and value < self.threshold:
            triggered = True
        
        if triggered:
            # Metric Inc
            ALERTS_GENERATED_TOTAL.labels(node_id=metric.get("node_id", "unknown"), severity=self.severity.value).inc()
            
            return [Alert(
                node_id=metric.get("node_id", "unknown"),
                severity=self.severity,
                metric_name=self.metric_key,
                value=value,
                threshold=self.threshold,
                message=self.msg_template.format(id=metric.get("node_id"), val=value, limit=self.threshold)
            )]
        return []

# --- Dispatch ---

class AlertDispatcher(ABC):
    @abstractmethod
    async def dispatch(self, alert: Alert):
        pass

class LogDispatcher(AlertDispatcher):
    async def dispatch(self, alert: Alert):
        logger.warning(json.dumps({
            "event": "alert_fired",
            "source": "LogDispatcher",
            "alert": alert.model_dump()
        }))
        ALERTS_SENT_TOTAL.labels(severity=alert.severity.value).inc()

class WebhookDispatcher(AlertDispatcher):
    def __init__(self, url: str):
        self.url = url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def dispatch(self, alert: Alert):
        color = "#EF4444" if alert.severity == Severity.CRITICAL else "#F59E0B"
        payload = {
            "attachments": [{
                "color": color,
                "blocks": [
                     {
                         "type": "section", 
                         "text": {"type": "mrkdwn", "text": f"🚨 *{alert.severity.upper()}*: {alert.message}"}
                     },
                     {
                         "type": "context", 
                         "elements": [{"type": "mrkdwn", "text": f"Node: `{alert.node_id}` | Time: {alert.timestamp}"}]
                     }
                ]
            }]
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.url, json=payload, timeout=5) as resp:
                    if resp.status >= 400:
                        raise Exception(f"HTTP {resp.status}")
                ALERTS_SENT_TOTAL.labels(severity=alert.severity.value).inc()
            except Exception as e:
                WEBHOOK_FAILURES_TOTAL.inc()
                raise e

# --- Engine ---

class AlertEngine:
    def __init__(self, redis_client: redis.Redis, dispatcher: AlertDispatcher = None):
        self.redis = redis_client
        self.dispatcher = dispatcher or LogDispatcher()
        self.rules = self._load_default_rules()
        
        # Load Lua Script
        try:
            with open(os.path.join(os.path.dirname(__file__), 'scripts', 'token_bucket.lua'), 'r') as f:
                self.token_bucket_lua = self.redis.register_script(f.read())
        except Exception as e: 
            logger.warning(f"Failed to load token_bucket.lua: {e}")
            self.token_bucket_lua = None

    def _load_default_rules(self) -> List[AlertRule]:
        return [
            ThresholdRule("latency_ms", ">", ALERT_LATENCY_CRIT, Severity.CRITICAL, "CRITICAL LATENCY on {id}: {val}ms"),
            ThresholdRule("latency_ms", ">", ALERT_LATENCY_WARN, Severity.WARNING, "High Latency on {id}: {val}ms"),
            ThresholdRule("packet_loss", ">", ALERT_LOSS_CRIT, Severity.CRITICAL, "CRITICAL PACKET LOSS on {id}: {val}%"),
            ThresholdRule("packet_loss", ">", ALERT_LOSS_WARN, Severity.WARNING, "Packet Loss Detected on {id}: {val}%"),
            ThresholdRule("uptime_pct", "<", ALERT_UPTIME_WARN, Severity.WARNING, "Low Uptime on {id}: {val}%")
        ]

    async def process(self, metric: dict):
        """Evaluate and dispatch."""
        alerts = []
        for rule in self.rules:
            alerts.extend(rule.evaluate(metric))
        
        for alert in alerts:
            # 1. Deduplication
            if await self._is_duplicate(alert):
                ALERTS_DROPPED_TOTAL.labels(reason="dedup").inc()
                continue

            # 2. Rate Limiting
            if not await self._check_rate_limits(alert):
                # Counter handled within check
                continue

            # 3. Dispatch with DLQ Fallback
            try:
                await self.dispatcher.dispatch(alert)
            except Exception:
                # If retry failed (Tenacity raised), dump to DLQ
                await self._send_to_dlq(alert)

    async def _is_duplicate(self, alert: Alert) -> bool:
        """Check valid Redis dedup key."""
        key = alert.get_dedup_key()
        # setnx returns True if key was set (new alert)
        # Returns False if key existed (duplicate)
        # So is_duplicate is NOT was_set
        was_set = await self.redis.set(key, "1", ex=ALERT_LOOP_COOLDOWN_SEC, nx=True)
        return not was_set

    async def _check_rate_limits(self, alert: Alert) -> bool:
        """Check Node Quota + Global Token Bucket."""
        
        # A. Per-Node Quota (Fixed Window)
        node_key = f"alerts:quota:node:{alert.node_id}"
        node_count = await self.redis.incr(node_key)
        if node_count == 1: 
            await self.redis.expire(node_key, 3600)
        
        if node_count > NODE_RATE_LIMIT:
            ALERTS_DROPPED_TOTAL.labels(reason="node_quota").inc()
            return False

        # B. Global Token Bucket (Lua)
        if self.token_bucket_lua:
            # REFILL RATE: GLOBAL_RATE_LIMIT per hour -> Limit / 3600 per sec
            refill_rate = GLOBAL_RATE_LIMIT / 3600.0
            capacity = 10 # small burst capacity
            now = int(datetime.now(timezone.utc).timestamp())
            
            allowed = await self.token_bucket_lua(
                keys=["alerts:quota:global"], 
                args=[refill_rate, capacity, now]
            )
            if not allowed:
                 ALERTS_DROPPED_TOTAL.labels(reason="global_limit").inc()
                 return False

        return True

    async def _send_to_dlq(self, alert: Alert):
        """Push failed alert to Dead Letter Queue."""
        try:
            ALERTS_DLQ_TOTAL.inc()
            await self.redis.lpush("alerts:dlq", alert.model_dump_json())
            logger.error(f"Alert {alert.alert_id} sent to DLQ")
        except Exception as e:
            logger.error(f"Failed to push to DLQ: {e}")
