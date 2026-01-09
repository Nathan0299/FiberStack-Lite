# Sandbox Cluster Simulation

## Quick Start

```bash
# 1. Generate keypair (one-time)
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem

# 2. Generate JWT tokens for each probe
# Use jwt.io or a script with the private key

# 3. Set environment variables
export JWT_PUBLIC_KEY=$(cat public.pem)
export JWT_TOKEN_GH="<token with sub=probe-accra-01, region=gh-accra>"
export JWT_TOKEN_NG="<token with sub=probe-lagos-01, region=ng-lagos>"
export JWT_TOKEN_KE="<token with sub=probe-nairobi-01, region=ke-nairobi>"

# 4. Run simulation (15 minutes)
docker-compose -f cluster-simulation.yml up -d

# 5. Monitor
docker-compose -f cluster-simulation.yml logs -f

# 6. Stop
docker-compose -f cluster-simulation.yml down -v
```

## Test Scenarios

| Test | Command |
|------|---------|
| Happy Path | All probes running |
| Wrong Region Token | Set JWT_TOKEN_NG with region=gh-accra |
| Expired Token | Set JWT_TOKEN_KE with exp=past |
| Probe Failure | `docker stop probe-ng` |
| ETL Backpressure | `docker pause fiber-etl` then `docker unpause fiber-etl` |
| Replay Test | `docker restart probe-gh` |

## Validation

1. **API Logs**: Check for 202 responses per probe
2. **ETL Logs**: Confirm batch processing
3. **Redis**: `redis-cli LRANGE fiber:etl:queue 0 -1`
4. **Aggregates**: `psql -c "SELECT * FROM aggregates_5m_region LIMIT 10"`
5. **Grafana**: http://localhost:3000 → Region toggle
