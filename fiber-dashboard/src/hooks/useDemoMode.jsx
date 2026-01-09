import { useState, useEffect, useRef, useCallback } from 'react';

// TUNING CONSTANTS (The "10/10" Polish)
const JITTER_CAP_MINUTES = 5;
const FLAP_CAP_MINUTES = 10;
const DROP_CAP_MINUTES = 15;

const METRIC_HISTORY_LENGTH = 30; // 30 seconds of history for charts

export function useDemoMode(initialEnabled = false) {
    const [isDemoMode, setIsDemoMode] = useState(() => {
        return localStorage.getItem('fiber_demo_mode') === 'true' || initialEnabled;
    });

    // Anomaly State
    const lastAnomalyRef = useRef({
        jitter: parseInt(localStorage.getItem('last_anomaly_jitter') || '0'),
        flap: parseInt(localStorage.getItem('last_anomaly_flap') || '0'),
        drop: parseInt(localStorage.getItem('last_anomaly_drop') || '0'),
    });

    const [demoMetrics, setDemoMetrics] = useState([]);

    // Toggle Handler
    const toggleDemoMode = useCallback(() => {
        setIsDemoMode(prev => {
            const next = !prev;
            localStorage.setItem('fiber_demo_mode', String(next));
            // Reload to clear/reset state cleanly
            window.location.reload();
            return next;
        });
    }, []);

    // Synthetic Data Generator
    useEffect(() => {
        if (!isDemoMode) return;

        const interval = setInterval(() => {
            const now = Date.now();
            const metrics = generateBatch(now, lastAnomalyRef.current);
            setDemoMetrics(metrics);
        }, 1000); // 1Hz update

        return () => clearInterval(interval);
    }, [isDemoMode]);

    return { isDemoMode, toggleDemoMode, demoMetrics };
}

// --- REALISM ENGINE ---

const REGIONS = ['gh-accra', 'ng-lagos', 'ke-nairobi', 'za-capetown', 'eg-cairo'];

function generateBatch(timestamp, limits) {
    // Check for Anomaly Triggers
    const anomaly = determineAnomaly(timestamp, limits);

    return REGIONS.map((region, i) => {
        const baseLatency = 40 + (i * 10); // Geo-variance
        const id = `probe-${region}-0${i + 1}`;

        let latency = baseLatency + (Math.sin(timestamp / 5000) * 10) + (Math.random() * 5);
        let packetLoss = Math.random() < 0.98 ? 0 : Math.random() * 2;
        let uptime = 100;

        // Apply Anomaly
        if (anomaly.type === 'JITTER' && i === 0) { // Target Probe 0
            latency += 400 + (Math.random() * 200); // Spike
        } else if (anomaly.type === 'FLAP' && i === 1) { // Target Probe 1
            uptime = timestamp % 2000 > 1000 ? 0 : 100; // Flap every second
        } else if (anomaly.type === 'DROP' && i === 2) { // Target Probe 2
            packetLoss = 15 + (Math.random() * 10); // Heavy loss
        }

        return {
            node_id: id,
            region: region,
            country: region.split('-')[0].toUpperCase(),
            latency_ms: latency,
            uptime_pct: uptime,
            packet_loss: packetLoss,
            time: new Date(timestamp).toISOString(),
            status: uptime < 90 ? 'critical' : (latency > 150 ? 'degraded' : 'healthy')
        };
    });
}

function determineAnomaly(now, limits) {
    // 1. Jitter Storm
    if (now - limits.jitter > JITTER_CAP_MINUTES * 60 * 1000) {
        if (Math.random() < 0.05) { // 5% chance per second when eligible
            updateLimit('jitter', now, limits);
            return { type: 'JITTER' };
        }
    }

    // 2. Node Flap
    if (now - limits.flap > FLAP_CAP_MINUTES * 60 * 1000) {
        if (Math.random() < 0.02) {
            updateLimit('flap', now, limits);
            return { type: 'FLAP' };
        }
    }

    // 3. Packet Drop
    if (now - limits.drop > DROP_CAP_MINUTES * 60 * 1000) {
        if (Math.random() < 0.02) {
            updateLimit('drop', now, limits);
            return { type: 'DROP' };
        }
    }

    return { type: 'NONE' };
}

function updateLimit(type, now, limits) {
    limits[type] = now;
    localStorage.setItem(`last_anomaly_${type}`, String(now));
    console.log(`[DemoMode] Injecting Anomaly: ${type}`);
}
