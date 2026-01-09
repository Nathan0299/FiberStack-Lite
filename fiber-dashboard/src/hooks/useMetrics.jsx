import { useState, useEffect, useCallback } from 'react';
import { fetchMetrics } from '../services/api';

export function useMetrics(refreshInterval = 30000) {
    const [metrics, setMetrics] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    const refresh = useCallback(async () => {
        try {
            setLoading(true);
            // Fetch last 500 points (~4h window at 30s interval). 
            // Assumes probe emission interval is stable at ~30s in sandbox.
            // TODO: Replace with time-range query.
            const data = await fetchMetrics({ limit: 500 });
            // Guard against malformed response
            const metricsData = data?.data?.metrics ?? [];
            setMetrics(metricsData);
            setLastUpdated(new Date());
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
        const interval = setInterval(refresh, refreshInterval);
        return () => clearInterval(interval);
    }, [refresh, refreshInterval]);

    return { metrics, loading, error, lastUpdated, refresh };
}
