import React, { useMemo, Profiler } from 'react';
import { useDashboard } from '../context/DashboardContext';
import { StatusBadge } from './StatusBadge';
import { resolveNodeState, getTimeSince, NODE_STATE } from '../logic/nodeState';
import { List } from 'react-window';
import { AutoSizer } from 'react-virtualized-auto-sizer';

// Severity Weight for Sorting
const MAGNITUDE = {
    [NODE_STATE.DOWN]: 4,
    [NODE_STATE.CRITICAL]: 3,
    [NODE_STATE.DEGRADED]: 2,
    [NODE_STATE.STALE]: 1,
    [NODE_STATE.HEALTHY]: 0
};

// Profiler Callback
function onRender(id, phase, actualDuration) {
    if (actualDuration > 16) {
        console.warn(`[Perf] ${id} slow render: ${actualDuration.toFixed(2)}ms`);
    }
}

export function MetricsTable({ metrics, loading }) {
    const { regionFilter, statusFilter, enterInspectMode } = useDashboard();

    // 1. PROCESS DATA (Filter & Sort)
    const processedNodes = useMemo(() => {
        // Dedup by node_id (show latest only for inventory list)
        const unique = new Map();
        metrics.forEach(m => {
            if (!unique.has(m.node_id)) unique.set(m.node_id, m);
        });

        return Array.from(unique.values())
            .map(node => ({
                ...node,
                state: resolveNodeState(node, node)
            }))
            .filter(node => {
                if (regionFilter !== 'ALL' && node.country !== regionFilter) return false;
                if (statusFilter !== 'ALL' && node.state !== statusFilter) return false;
                return true;
            })
            .sort((a, b) => {
                const scoreA = MAGNITUDE[a.state];
                const scoreB = MAGNITUDE[b.state];
                if (scoreA !== scoreB) return scoreB - scoreA;
                return a.node_id.localeCompare(b.node_id);
            });
    }, [metrics, regionFilter, statusFilter]);

    if (loading && metrics.length === 0) {
        return <div className="text-zinc-500 text-xs font-mono p-4 animate-pulse">SCANNING INVENTORY...</div>;
    }

    // Standard Row Component
    const Row = ({ node, index }) => {
        const isOdd = index % 2 !== 0;

        return (
            <div
                role="row"
                onClick={() => enterInspectMode(node.node_id)}
                className={`flex items-center cursor-pointer border-b border-zinc-900 transition-colors duration-200 hover:bg-zinc-800/50 h-10 ${isOdd ? 'bg-zinc-900/20' : ''}`}
            >
                {/* 1. NODE ID (Smart Format) */}
                <div role="cell" className="flex-1 px-4 py-2 font-mono text-xs text-zinc-300 truncate">
                    {/* Mobile: Strip 'probe-' prefix. Desktop: Full ID */}
                    <span className="md:hidden">{node.node_id.replace(/^probe-/, '')}</span>
                    <span className="hidden md:inline">{node.node_id.slice(0, 8)}</span>
                </div>

                {/* 2. REGION (Hidden on Mobile) */}
                <div role="cell" className="flex-1 px-4 py-2 text-xs text-zinc-500 truncate hidden md:block">
                    {node.region}
                </div>

                {/* 3. STATUS */}
                <div role="cell" className="flex-1 px-4 py-2 hidden sm:block">
                    <StatusBadge status={node.state} className="scale-75 origin-left" />
                </div>

                {/* 4. LATENCY */}
                <div role="cell" className="flex-1 px-4 py-2 text-right font-mono-num text-xs tabular-nums">
                    <span className={node.latency_ms > 100 ? 'text-[hsl(var(--status-degraded))]' : 'text-zinc-400'}>
                        {node.latency_ms.toFixed(0)}
                    </span>
                    <span className="text-zinc-600 ml-1 text-[10px]">ms</span>
                </div>

                {/* 5. LOSS */}
                <div role="cell" className="flex-1 px-4 py-2 text-right font-mono-num text-xs tabular-nums">
                    <span className={node.packet_loss > 0 ? 'text-[hsl(var(--status-critical))] font-bold' : 'text-zinc-500'}>
                        {node.packet_loss.toFixed(1)}%
                    </span>
                </div>

                {/* 6. LAST SEEN */}
                <div role="cell" className="flex-1 px-4 py-2 text-right text-zinc-600 font-mono text-[10px] hidden lg:block">
                    {getTimeSince(node.time)}
                </div>
            </div>
        );
    };

    // DEBUG: Check data flow
    console.log('[MetricsTable] Render:', {
        totalMetrics: metrics.length,
        processedCount: processedNodes.length,
        sampleNode: processedNodes[0]
    });

    return (
        <Profiler id="MetricsTable" onRender={onRender}>
            <div className="flex flex-col h-full w-full" role="table" aria-label="Node Inventory">

                {/* Sticky Header (Outside Virtual List) */}
                <div className="flex items-center bg-[#0e0e11] border-b border-zinc-800 z-10 sticky top-0" role="rowgroup">
                    <HeaderCell>Node ID</HeaderCell>
                    <HeaderCell className="hidden md:block">Region</HeaderCell>
                    <HeaderCell className="hidden sm:block">Status</HeaderCell>
                    <HeaderCell align="right">Latency</HeaderCell>
                    <HeaderCell align="right">Loss</HeaderCell>
                    <HeaderCell align="right" className="hidden lg:block">Last Seen</HeaderCell>
                </div>

                {/* Standard Scrollable Body (Reliable) */}
                <div className="flex-1 w-full min-h-0 relative bg-[#050505] overflow-y-auto custom-scrollbar">
                    {processedNodes.length > 0 ? (
                        <div className="w-full">
                            {processedNodes.map((node, index) => (
                                <Row key={node.node_id} node={node} index={index} />
                            ))}
                        </div>
                    ) : (
                        <div className="flex items-center justify-center h-full text-zinc-600 text-[10px] font-mono tracking-widest uppercase opacity-50">
                            // INVENTORY SIGNAL LOST //
                        </div>
                    )}
                </div>
            </div>
        </Profiler>
    );
}

function HeaderCell({ children, align = 'left', className = '' }) {
    return (
        <div
            role="columnheader"
            className={`flex-1 py-3 px-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest text-${align} ${className}`}
        >
            {children}
        </div>
    );
}
