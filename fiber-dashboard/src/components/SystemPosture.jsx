import React, { useState, useEffect, useRef } from 'react';

/**
 * SYSTEM POSTURE — The single declarative truth.
 * 
 * Posture overrides all metrics. It is:
 * - Slow to degrade (10s hysteresis)
 * - Slower to recover (30s cooldown)
 * - The only thing visible at a glance
 */

export const POSTURE = {
    SECURED: 'SECURED',
    CONTESTED: 'CONTESTED',
    COMPROMISED: 'COMPROMISED'
};

// Posture determination logic
function derivePosture(metrics) {
    if (!metrics || metrics.length === 0) return POSTURE.COMPROMISED;

    let criticalCount = 0;
    let degradedCount = 0;
    let blackoutCount = 0;

    metrics.forEach(m => {
        // Check for blackout (stale or no signal)
        const lastSeen = new Date(m.time);
        const now = new Date();
        const staleThreshold = 5 * 60 * 1000; // 5 minutes
        if (now - lastSeen > staleThreshold) {
            blackoutCount++;
            return;
        }

        // Check for critical
        if (m.packet_loss > 5 || m.latency_ms > 200) {
            criticalCount++;
            return;
        }

        // Check for degraded
        if (m.packet_loss > 1 || m.latency_ms > 100) {
            degradedCount++;
        }
    });

    // Posture rules
    if (blackoutCount > 0 || criticalCount >= 2) return POSTURE.COMPROMISED;
    if (criticalCount >= 1 || degradedCount >= 1) return POSTURE.CONTESTED;
    return POSTURE.SECURED;
}

export function SystemPosture({ metrics }) {
    const [displayPosture, setDisplayPosture] = useState(POSTURE.SECURED);
    const [rawPosture, setRawPosture] = useState(POSTURE.SECURED);
    const hysteresisTimer = useRef(null);

    // Derive raw posture from metrics
    useEffect(() => {
        const derived = derivePosture(metrics);
        setRawPosture(derived);
    }, [metrics]);

    // Apply hysteresis: slow to change
    useEffect(() => {
        // Clear any pending transition
        if (hysteresisTimer.current) {
            clearTimeout(hysteresisTimer.current);
        }

        const postureWeight = {
            [POSTURE.SECURED]: 0,
            [POSTURE.CONTESTED]: 1,
            [POSTURE.COMPROMISED]: 2
        };

        const currentWeight = postureWeight[displayPosture];
        const rawWeight = postureWeight[rawPosture];

        if (rawWeight > currentWeight) {
            // Degrading: 10 second delay
            hysteresisTimer.current = setTimeout(() => {
                setDisplayPosture(rawPosture);
            }, 10000);
        } else if (rawWeight < currentWeight) {
            // Recovering: 30 second cooldown
            hysteresisTimer.current = setTimeout(() => {
                setDisplayPosture(rawPosture);
            }, 30000);
        }

        return () => {
            if (hysteresisTimer.current) {
                clearTimeout(hysteresisTimer.current);
            }
        };
    }, [rawPosture, displayPosture]);

    // Posture styling
    const postureStyles = {
        [POSTURE.SECURED]: 'text-[hsl(var(--status-healthy))]',
        [POSTURE.CONTESTED]: 'text-[hsl(var(--status-degraded))]',
        [POSTURE.COMPROMISED]: 'text-[hsl(var(--status-critical))]'
    };

    return (
        <div className="flex items-center justify-center">
            <span className="text-[10px] text-zinc-600 uppercase tracking-[0.3em] font-bold mr-3">
                SYSTEM POSTURE:
            </span>
            <span
                className={`text-sm font-bold tracking-[0.2em] ${postureStyles[displayPosture]} transition-colors duration-700 linear`}
            >
                {displayPosture}
            </span>
        </div>
    );
}

export default SystemPosture;
