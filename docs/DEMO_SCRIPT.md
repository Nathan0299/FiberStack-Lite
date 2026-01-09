# Demo Script — FiberStack-Lite v1.0.0-mvp

**Duration:** ~10 minutes  
**Audience:** Internal stakeholders / Investors / Technical reviewers

---

## Pre-Demo Setup (5 min before)

```bash
# Verify stack is running
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check API health
curl -s http://localhost:8000/api/status | jq

# Verify probes
curl -s http://localhost:8000/api/metrics | jq 'length'
# Should return 3

# Open dashboard
open http://localhost:4000
```

---

## Act 1: The Command Interface (2 min)

### Opening Statement
> "FiberStack-Lite is a distributed network monitoring system for critical infrastructure across Africa. What you're looking at is the Command-Grade interface — designed for war rooms, not dashboards."

### Highlight System Posture
- Point to **SYSTEM POSTURE** in the top bar
- Explain: "This is the single source of truth. SECURED, CONTESTED, or COMPROMISED."
- Note: "It uses hysteresis — 10 seconds to degrade, 30 seconds to recover. Command systems don't panic."

### Show Sidebar Controls
- **Time Scope**: LIVE / 5m / 1h
- **Region Filter**: Global / Ghana / Nigeria / Kenya
- **Control Status**: SECURED / CONTESTED / COMPROMISED filters

---

## Act 2: Territory Control (3 min)

### The Map
> "This isn't just a map — it's a territory control visualization."

- Point to the **glowing markers** on West/East Africa
- Explain: "Green glow = territory secured. The opacity fades as control degrades."
- Click on **Accra probe** → Show the Details Panel
  - Node ID
  - Status badge
  - Latency / Loss / Uptime
  - "RESUME LIVE VIEW" button

### Geographic Coverage
- Ghana (Accra)
- Nigeria (Lagos)
- Kenya (Nairobi)
- > "MVP covers the core African corridor — the foundation for continental expansion."

---

## Act 3: Operational Intelligence (2 min)

### KPI Cards
- **Response Integrity**: Average latency across probes
- **Continuity Index**: Uptime percentage
- **Signal Degradation**: Packet loss

> "These aren't just numbers — they're thresholds. Cross them, and the system changes posture."

### The Chart
- Show **INTEGRITY / CONTINUITY / DEGRADATION** tabs
- Point to the **Trajectory label** (STABILIZING / DEGRADING)

> "The chart answers one question: 'What happens if I do nothing?'"

---

## Act 4: Failure Scenario (2 min)

### Trigger a Failure
```bash
# In a terminal (keep dashboard visible)
docker stop probe-ke
```

### Observe Response
1. Watch the **Kenya marker** fade on the map
2. Watch **System Posture** shift (after hysteresis)
3. Show the **Inventory Table** — Kenya shows BLACKOUT

> "The system detected the failure. No alerts, no popups — just a clear status change."

### Recovery
```bash
docker start probe-ke
```

> "And just as calmly, it recovers."

---

## Act 5: Architecture Overview (1 min)

Open the **SYSTEM_BLUEPRINT.md** or show the diagram:

```
Probe → API → Redis → ETL → TimescaleDB → Dashboard
```

> "Six microservices. Designed for federation across multiple countries. This is MVP — built to scale."

---

## Closing (30 sec)

> "FiberStack-Lite transforms network monitoring from a dashboard into a command interface. 
> It's not about seeing data — it's about understanding control.
> Questions?"

---

## Backup Slides

If demo environment fails:
1. Show pre-recorded video (if available)
2. Show architecture diagrams from `/docs/`
3. Walk through `RELEASE_NOTES.md` capabilities

---

## Performance Baseline (for reference)

| Metric | Expected | Threshold |
|--------|----------|-----------|
| API Latency | < 50ms | < 100ms |
| Probe Count | 3 | ≥ 1 |
| Dashboard TTI | < 2s | < 4s |
