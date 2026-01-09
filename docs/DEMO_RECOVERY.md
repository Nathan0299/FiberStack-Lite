# Demo Recovery Procedures

**Document Status:** Frozen (v1.0.0-mvp)  
**Last Updated:** 2026-01-09

---

## Purpose

Quick recovery procedures for common demo failures. Keep this open during live demos.

---

## Issue: Probes Not Visible on Map

### Symptoms
- Map shows no markers
- Inventory table empty
- "Signal Lost" message

### Quick Fix (30 seconds)
```bash
# Check probe status
docker ps | grep probe

# If probes are down, restart them
docker-compose -f fiber-deploy/docker-compose.dev.yml up -d probe-gh probe-ng probe-ke

# Wait for data ingestion
sleep 30

# Refresh dashboard
```

### Fallback
- Switch demo focus to **Inventory Table** (scroll down)
- Explain: "The probes are initializing..."

---

## Issue: Map Not Loading (Blank Area)

### Symptoms
- White/grey area where map should be
- Console shows Leaflet errors

### Quick Fix (10 seconds)
```bash
# Hard refresh the page
# Mac: Cmd + Shift + R
# Windows: Ctrl + Shift + R
```

### Fallback
- Scroll to KPI cards and Inventory Table
- Say: "Let me show you the data view while the map loads..."

---

## Issue: API Errors (500s in Console)

### Symptoms
- Dashboard shows "Signal Lost"
- Console shows 500 errors

### Quick Fix (60 seconds)
```bash
# Check API health
curl http://localhost:8000/api/status

# Restart API if needed
docker-compose -f fiber-deploy/docker-compose.dev.yml restart fiber-api

# Wait for startup
sleep 10
```

### Fallback
- If API is down, show the **architecture diagram** from docs
- Explain the system while it recovers

---

## Issue: System Posture Stuck on "COMPROMISED"

### Explanation
This is **expected behavior** if probes have been recently restarted. The hysteresis (30s recovery cooldown) prevents flapping.

### Quick Fix
- Wait 30 seconds
- Explain: "Notice how the system uses hysteresis to prevent false positives..."

### Force Reset (if stuck)
```bash
# Restart all services
docker-compose -f fiber-deploy/docker-compose.dev.yml restart
```

---

## Issue: Dashboard Not Loading at All

### Symptoms
- ERR_CONNECTION_REFUSED at port 4000

### Quick Fix
```bash
# Check if dashboard container is running
docker ps | grep dashboard

# If not running, start it
docker-compose -f fiber-deploy/docker-compose.dev.yml up -d fiber-dashboard

# Or run locally
cd fiber-dashboard && npm run dev
```

---

## Pre-Demo Checklist

Run this 5 minutes before any demo:

```bash
# 1. Verify all containers
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Check API
curl -s http://localhost:8000/api/status | jq

# 3. Check probe count
curl -s http://localhost:8000/api/metrics | jq 'length'

# 4. Open dashboard
open http://localhost:4000

# 5. Click a probe on map to verify inspection works
```

---

## Emergency Contact

If all else fails during a live demo:
- Switch to **pre-recorded video** (if available)
- Show the **architecture documentation**
- Acknowledge: "We're experiencing some technical difficulties; let me show you the design..."
