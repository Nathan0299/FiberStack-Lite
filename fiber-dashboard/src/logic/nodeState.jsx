/**
 * Black Signal State Authority
 * Single Source of Truth for Node Status
 */

export const NODE_STATE = {
    HEALTHY: 'HEALTHY',   // Green
    DEGRADED: 'DEGRADED', // Yellow
    CRITICAL: 'CRITICAL', // Neon Red
    STALE: 'STALE',       // Grey
    DOWN: 'DOWN'          // Neon Red (Blinking)
};

// Thresholds (Black Signal Standard)
const THRESHOLDS = {
    LATENCY: {
        WARNING: 100, // ms
        CRITICAL: 200 // ms
    },
    PACKET_LOSS: {
        WARNING: 1.0, // %
        CRITICAL: 5.0 // %
    },
    STALE_TIMEOUT: 30000 // 30s (approx 1 missed beat)
};

/**
 * Resolves the canonical state of a node based on telemetry.
 * @param {Object} node - Node data object
 * @param {Object} metrics - Latest metrics for the node
 * @param {Date} now - Current time (for pure function behavior)
 * @returns {string} NODE_STATE enum value
 */
export function resolveNodeState(node, metrics, now = new Date()) {
    if (!metrics) return NODE_STATE.STALE;

    // 1. Check Staleness
    const lastSeenTime = new Date(metrics.time).getTime();
    const timeSinceLastSeen = now.getTime() - lastSeenTime;

    if (timeSinceLastSeen > THRESHOLDS.STALE_TIMEOUT) {
        return NODE_STATE.STALE;
    }

    // 2. Check Use-Case Specific "Down" (e.g., explicit error codes in future)
    // For now, excessive packet loss implies effectively down/critical.

    // 3. Resolve Performance State
    const { latency_ms, packet_loss } = metrics;

    const isCritical =
        latency_ms > THRESHOLDS.LATENCY.CRITICAL ||
        packet_loss > THRESHOLDS.PACKET_LOSS.CRITICAL;

    if (isCritical) return NODE_STATE.CRITICAL;

    const isDegraded =
        latency_ms > THRESHOLDS.LATENCY.WARNING ||
        packet_loss > THRESHOLDS.PACKET_LOSS.WARNING;

    if (isDegraded) return NODE_STATE.DEGRADED;

    return NODE_STATE.HEALTHY;
}

/**
 * Helper to get time elapsed string for tooltips
 */
export function getTimeSince(isoString, now = new Date()) {
    if (!isoString) return 'Never';
    const diff = now.getTime() - new Date(isoString).getTime();
    const seconds = Math.floor(diff / 1000);

    if (seconds < 60) return `${seconds}s ago`;
    return `${Math.floor(seconds / 60)}m ago`;
}
