import React, { useState, useMemo, Profiler } from 'react';
import { MetricChart } from './MetricChart';
import { Activity, CheckCircle, AlertTriangle } from 'lucide-react';
import { useThrottle } from '../hooks/useThrottle';

// Profiler Callback
function onRender(id, phase, actualDuration) {
    if (actualDuration > 16) {
        console.warn(`[Perf] ${id} slow render: ${actualDuration.toFixed(2)}ms`);
    }
}

/**
 * Derive trajectory from recent data.
 * Answers: "What happens if I do nothing?"
 */
function deriveTrajectory(data, dataKey) {
    if (!data || data.length < 10) return 'AWAITING';

    // Compare last 30% vs first 30% of data
    const recentCount = Math.floor(data.length * 0.3);
    const recent = data.slice(-recentCount);
    const earlier = data.slice(0, recentCount);

    const avgRecent = recent.reduce((sum, d) => sum + (d[dataKey] || 0), 0) / recent.length;
    const avgEarlier = earlier.reduce((sum, d) => sum + (d[dataKey] || 0), 0) / earlier.length;

    const delta = avgRecent - avgEarlier;
    const threshold = dataKey === 'latency' ? 5 : 0.5; // 5ms for latency, 0.5% for others

    if (Math.abs(delta) < threshold) return 'STABILIZING';

    // For latency and loss: higher is worse. For uptime: lower is worse.
    if (dataKey === 'uptime') {
        return delta < -threshold ? 'DEGRADING' : 'STABILIZING';
    } else {
        return delta > threshold ? 'DEGRADING' : 'STABILIZING';
    }
}

export function ChartsPanel({ metrics, loading }) {
    const [activeTab, setActiveTab] = useState('latency');

    // THROTTLE: Limit updates to 2 FPS (500ms) to prevent CPU spikes
    const throttledMetrics = useThrottle(metrics, 500);

    const chartData = useMemo(() => {
        if (!throttledMetrics) return [];
        // Limit data points and sort by time
        const MAX_POINTS = 300;
        const sliced = throttledMetrics.slice(-MAX_POINTS);
        return sliced
            .map(m => ({
                time: m.time,
                latency: m.latency_ms,
                uptime: m.uptime_pct,
                loss: m.packet_loss
            }))
            .sort((a, b) => new Date(a.time) - new Date(b.time));
    }, [throttledMetrics]);

    // Derive trajectory for the active metric
    const trajectory = useMemo(() => deriveTrajectory(chartData, activeTab), [chartData, activeTab]);

    if (loading && (!metrics || metrics.length === 0)) {
        return (
            <div className="matte-card h-full w-full p-5 flex flex-col">
                <div className="flex space-x-2 mb-4">
                    {[1, 2, 3].map(i => <div key={i} className="h-7 w-20 bg-zinc-900 rounded" />)}
                </div>
                <div className="flex-1 bg-zinc-900/50 rounded" />
            </div>
        );
    }

    const tabs = [
        { id: 'latency', label: 'INTEGRITY', icon: Activity, color: '#f2f2f2' },
        { id: 'uptime', label: 'CONTINUITY', icon: CheckCircle, color: 'hsl(var(--status-healthy))' },
        { id: 'loss', label: 'DEGRADATION', icon: AlertTriangle, color: 'hsl(var(--status-critical))' }
    ];

    const activeConfig = tabs.find(t => t.id === activeTab);

    // Trajectory styling
    const trajectoryStyles = {
        'STABILIZING': 'text-[hsl(var(--status-healthy))]',
        'DRIFTING': 'text-[hsl(var(--status-degraded))]',
        'DEGRADING': 'text-[hsl(var(--status-critical))]',
        'AWAITING': 'text-zinc-600'
    };

    return (
        <Profiler id="ChartsPanel" onRender={onRender}>
            <div className="matte-card h-full w-full p-5 flex flex-col relative overflow-hidden">
                {/* HEADER: Tabs + Trajectory */}
                <div className="flex justify-between items-center mb-4 z-10 relative">
                    <div className="flex space-x-2">
                        {tabs.map(tab => {
                            const isActive = activeTab === tab.id;
                            const Icon = tab.icon;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`
                                        flex items-center space-x-1.5 px-2.5 py-1 rounded text-[9px] uppercase font-bold tracking-[0.15em] transition-colors duration-700 linear border
                                        ${isActive
                                            ? 'bg-white text-black border-white'
                                            : 'bg-transparent text-zinc-600 border-zinc-800 hover:border-zinc-700'}
                                    `}
                                >
                                    <Icon size={10} className={isActive ? 'text-black' : 'text-zinc-700'} />
                                    <span>{tab.label}</span>
                                </button>
                            );
                        })}
                    </div>

                    {/* TRAJECTORY LABEL — Answers "What if I do nothing?" */}
                    <div className={`text-[9px] font-mono font-bold tracking-[0.2em] uppercase transition-colors duration-700 linear ${trajectoryStyles[trajectory]}`}>
                        {trajectory}
                    </div>
                </div>

                {/* CHART AREA */}
                <div className="flex-1 min-h-0 relative">
                    <MetricChart
                        data={chartData}
                        dataKey={activeTab}
                        title=""
                        unit={activeTab === 'latency' ? 'ms' : '%'}
                        color={activeConfig.color}
                        threshold={activeTab === 'loss' ? 1.0 : (activeTab === 'latency' ? 100 : null)}
                    />
                </div>
            </div>
        </Profiler>
    );
}

