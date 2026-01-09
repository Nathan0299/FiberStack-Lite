# FiberStack-Lite Low-Resource Deployment Guide (Edge/IoT)

**Version:** 1.0 (Day 89)
**Target Hardware:** Raspberry Pi 4 / Zero 2 W, Rockchip equivalents.

---

## 1. Hardware Constraints

| Resource | Constraint | Tuning Action |
|----------|------------|---------------|
| **RAM** | < 512 MB | Reduce `MAX_QUEUE_SIZE` in Probe to 1000. Disable GUI. |
| **CPU** | ARMv7/v8 | Use `python:3.11-slim` images. Avoid complex regex in collectors. |
| **Disk** | SD Card | Minimize logging. Use `json-file` rotation (Max 10MB). |
| **Network**| 3G/LTE | Enable Batching. Set `request_timeout=30s`. |

---

## 2. Network Hardening (Intermittent Connectivity)

### Store-and-Forward Logic
The `fiber-probe` agent uses a local deque to buffer metrics when the Uplink is down.

**Configuration (`probe.yaml`):**
```yaml
# Buffer up to 1 hour of data at 1 sample/sec
max_buffer_size: 3600 
batch_size: 50
retry_backoff_max: 300 # 5 minutes
```

**Behavior**:
1. Probe detects Uplink Failure (Timeout/DNS Error).
2. Metrics queued in memory (`deque`).
3. Uplink restored -> Batch Flush (LIFO or FIFO depending on config).
4. **Invariant**: Oldest data dropped if buffer full (Preserve current state).

---

## 3. Security Hardening

> [!WARNING]
> IoT devices are physically accessible. Assume "Evil Maid" attacks are possible.

### 1. Identity Assurance
- **Per-Probe Tokens**: NEVER share tokens. Issue unique JWT per node.
- **Token Rotation**:
    - Central pushes new Token via `X-Refresh-Token` header (Phase 2).
    - Current: Manual rotation via Ansible/SSH.

### 2. TLS/SSL
- **Strict HTTPS**: Do not allow HTTP.
- **Cert Pinning**: (Optional) Pin Central API CA certificate in Probe image.

### 3. Disk Encryption
- Use LUKS for root partition if storing sensitive logs.
- Ideally: **Stateless**. Dont store anything sensitive on disk.

---

## 4. Operational Soak Testing

Before deploying 100+ nodes, run a 24h Soak Test on a representative device.

**Metrics to Watch**:
1. **Memory Leak**: RSS usage should not grow > 5% after initial warmup.
2. **Thermal Throttling**: CPU Temp < 70°C.
   - Command: `vcgencmd measure_temp` (RasPi).
3. **SD Card Wear**:
   - Check IOPS: `iostat -x 1`.
   - Goal: < 1 write/sec (Batch logs).

---

## 5. Deployment Example (Docker Compose)

Save as `docker-compose.edge.yml`:

```yaml
version: "3.8"
services:
  fiber-probe:
    image: ghcr.io/fiberstack/fiber-probe:v1.5-arm64
    restart: always
    environment:
      - NODE_ID=probe-gh-05
      - REGION=Ghana
      - API_ENDPOINT=https://api.fiberstack.io/api/push
      - TOKEN=${PROBE_TOKEN}
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    # Hardware Limits
    deploy:
      resources:
        limits:
          cpus: "0.50"
          memory: 128M
```
