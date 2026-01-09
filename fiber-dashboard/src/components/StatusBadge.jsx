import React, { useState, useEffect } from 'react';
import { NODE_STATE } from '../logic/nodeState';

/**
 * StatusBadge (Command-Grade)
 * 
 * Authority Language:
 * - HEALTHY    → SECURED
 * - DEGRADED   → CONTESTED
 * - CRITICAL   → COMPROMISED
 * - DOWN/STALE → BLACKOUT
 * 
 * Visual Discipline:
 * - No blinking (command systems do not panic)
 * - Slow transitions only
 * - Hysteresis maintained
 */
export function StatusBadge({ status: rawStatus, className = '' }) {
    const [displayStatus, setDisplayStatus] = useState(rawStatus);

    // HYSTERESIS: Slow to recover from COMPROMISED
    useEffect(() => {
        if (rawStatus === NODE_STATE.CRITICAL || rawStatus === NODE_STATE.DOWN) {
            // Immediate degradation
            setDisplayStatus(rawStatus);
        } else if (displayStatus === NODE_STATE.CRITICAL || displayStatus === NODE_STATE.DOWN) {
            // Hold COMPROMISED for 5 seconds before allowing recovery
            const timer = setTimeout(() => setDisplayStatus(rawStatus), 5000);
            return () => clearTimeout(timer);
        } else {
            setDisplayStatus(rawStatus);
        }
    }, [rawStatus, displayStatus]);

    // Authority Language Mapping
    const getAuthorityLabel = (state) => {
        switch (state) {
            case NODE_STATE.HEALTHY: return 'SECURED';
            case NODE_STATE.DEGRADED: return 'CONTESTED';
            case NODE_STATE.CRITICAL:
            case NODE_STATE.DOWN: return 'COMPROMISED';
            case NODE_STATE.STALE: return 'BLACKOUT';
            default: return 'UNKNOWN';
        }
    };

    // Styling by authority state
    const getStyleClasses = (state) => {
        switch (state) {
            case NODE_STATE.HEALTHY:
                return 'text-[hsl(var(--status-healthy))] bg-[hsla(var(--status-healthy)/0.08)] border-[hsla(var(--status-healthy)/0.15)]';
            case NODE_STATE.DEGRADED:
                return 'text-[hsl(var(--status-degraded))] bg-[hsla(var(--status-degraded)/0.08)] border-[hsla(var(--status-degraded)/0.15)]';
            case NODE_STATE.CRITICAL:
            case NODE_STATE.DOWN:
                return 'text-[hsl(var(--status-critical))] bg-[hsla(var(--status-critical)/0.08)] border-[hsla(var(--status-critical)/0.15)]';
            case NODE_STATE.STALE:
                return 'text-zinc-500 bg-zinc-900 border-zinc-800';
            default:
                return 'text-zinc-600 bg-zinc-900 border-zinc-800';
        }
    };

    const label = getAuthorityLabel(displayStatus);
    const styleClasses = getStyleClasses(displayStatus);

    return (
        <div className={`inline-flex items-center px-2 py-0.5 rounded border text-[9px] font-bold tracking-[0.15em] uppercase transition-colors duration-700 linear ${styleClasses} ${className}`}>
            <span
                className={`w-1.5 h-1.5 rounded-full mr-1.5 transition-colors duration-700 linear ${displayStatus === NODE_STATE.HEALTHY ? 'bg-[hsl(var(--status-healthy))]' :
                        displayStatus === NODE_STATE.DEGRADED ? 'bg-[hsl(var(--status-degraded))]' :
                            (displayStatus === NODE_STATE.CRITICAL || displayStatus === NODE_STATE.DOWN) ? 'bg-[hsl(var(--status-critical))]' :
                                'bg-zinc-600'
                    }`}
            />
            {label}
        </div>
    );
}

