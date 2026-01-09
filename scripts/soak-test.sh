#!/bin/bash
# soak-test.sh — 4-hour stability test
# Usage: ./scripts/soak-test.sh [duration_hours]

set -e

DURATION_HOURS="${1:-4}"
DURATION_SECONDS=$((DURATION_HOURS * 3600))
INTERVAL=60  # Check every minute
START=$(date +%s)
FAILURES=0

echo "🔥 Starting ${DURATION_HOURS}-hour soak test"
echo "=========================================="
echo "Start time: $(date)"
echo "Duration: ${DURATION_SECONDS} seconds"
echo ""

while [ $(($(date +%s) - START)) -lt $DURATION_SECONDS ]; do
    ELAPSED=$(($(date +%s) - START))
    REMAINING=$((DURATION_SECONDS - ELAPSED))
    
    # 1. Check API health
    if ! curl -sf http://localhost:8000/api/status > /dev/null 2>&1; then
        echo "❌ $(date '+%H:%M:%S') API health check failed!"
        FAILURES=$((FAILURES + 1))
        if [ $FAILURES -gt 5 ]; then
            echo "💀 Too many failures ($FAILURES). Aborting soak test."
            exit 1
        fi
    else
        # 2. Check probe count
        PROBE_COUNT=$(curl -s http://localhost:8000/api/metrics 2>/dev/null | jq 'length' 2>/dev/null || echo "0")
        
        if [ "$PROBE_COUNT" -lt 1 ]; then
            echo "⚠️  $(date '+%H:%M:%S') Probe count low: $PROBE_COUNT"
        else
            # 3. Get average latency
            AVG_LATENCY=$(curl -s http://localhost:8000/api/metrics 2>/dev/null | jq '[.[].latency_ms] | add / length | floor' 2>/dev/null || echo "N/A")
            
            # Log checkpoint
            printf "✅ %s | Probes: %3d | Avg Latency: %4s ms | Remaining: %dm\n" \
                "$(date '+%H:%M:%S')" "$PROBE_COUNT" "$AVG_LATENCY" "$((REMAINING / 60))"
        fi
    fi
    
    sleep $INTERVAL
done

echo ""
echo "=========================================="
echo "🎉 Soak test completed successfully!"
echo "End time: $(date)"
echo "Total failures: $FAILURES"
echo ""

if [ $FAILURES -eq 0 ]; then
    echo "✅ PASS: System stable for ${DURATION_HOURS} hours"
    exit 0
else
    echo "⚠️  WARN: System had $FAILURES intermittent failures"
    exit 0
fi
