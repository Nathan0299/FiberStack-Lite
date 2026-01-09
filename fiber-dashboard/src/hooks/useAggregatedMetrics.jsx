import { useMemo } from 'react';

/**
 * Aggregate metrics by node, keeping latest per node.
 * Metrics are already sorted by time DESC, so first occurrence is latest.
 */
export function useAggregatedMetrics(metrics) {
    return useMemo(() => {
        const byNode = {};

        for (const m of metrics) {
            if (!byNode[m.node_id]) {
                byNode[m.node_id] = m;
            }
        }

        return Object.values(byNode);
    }, [metrics]);
}
