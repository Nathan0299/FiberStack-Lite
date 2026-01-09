import { useMemo } from 'react';

export function useKPIStats(metrics) {
    return useMemo(() => {
        if (!metrics || metrics.length === 0) {
            return {
                avgLatency: 0,
                avgUptime: 0,
                avgLoss: 0,
                nodeCount: 0
            };
        }

        // Get unique active nodes in the current window
        const uniqueNodes = new Set(metrics.map(m => m.node_id)).size;

        // Calculate averages
        const totalLatency = metrics.reduce((acc, m) => acc + (m.latency_ms || 0), 0);
        const totalUptime = metrics.reduce((acc, m) => acc + (m.uptime_pct || 0), 0);
        const totalLoss = metrics.reduce((acc, m) => acc + (m.packet_loss || 0), 0);

        const count = metrics.length;

        return {
            avgLatency: count ? Math.round(totalLatency / count) : 0,
            avgUptime: count ? parseFloat((totalUptime / count).toFixed(1)) : 0,
            avgLoss: count ? parseFloat((totalLoss / count).toFixed(2)) : 0,
            nodeCount: uniqueNodes
        };
    }, [metrics]);
}
