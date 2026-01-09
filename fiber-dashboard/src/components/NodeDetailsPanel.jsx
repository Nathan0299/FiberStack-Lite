import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { StatusBadge } from './StatusBadge';
import { resolveNodeState, getTimeSince } from '../logic/nodeState';

export function NodeDetailsPanel({ node, metrics }) {
    const { isInspectLocked, exitInspectMode } = useDashboard();

    // In a real app, we'd memoize metrics at lock-time. 
    // For MVP, we trust the parent passes the correct slice based on lock state.

    // Latest metric slice
    const latest = metrics[0] || {};
    const state = resolveNodeState(node, latest);

    if (!node) return null;

    return (
        <div className="absolute top-4 right-4 w-96 bg-[#1f1f2e] border border-gray-800 shadow-2xl rounded-lg overflow-hidden z-[1000] animate-in slide-in-from-right-4 fade-in duration-200">
            {/* HEADER */}
            <div className="p-4 bg-[#0f111a] border-b border-gray-800 flex justify-between items-start">
                <div>
                    <h2 className="text-lg font-bold text-white font-mono tracking-tight">{node.node_id}</h2>
                    <div className="flex items-center space-x-2 mt-1">
                        <span className="text-xs text-gray-500 uppercase">{node.region} / {node.country}</span>
                        {isInspectLocked && (
                            <span className="px-1.5 py-0.5 bg-purple-900/50 text-purple-400 text-[10px] rounded border border-purple-500/20 font-mono">
                                LOCKED
                            </span>
                        )}
                    </div>
                </div>
                <button
                    onClick={exitInspectMode}
                    className="text-gray-500 hover:text-white transition-colors"
                >
                    ✕
                </button>
            </div>

            {/* STATUS AUTHORITY */}
            <div className="p-6 flex items-center justify-between border-b border-gray-800/50">
                <StatusBadge status={state} className="scale-125 origin-left" />
                <span className="text-xs text-gray-600 font-mono">
                    Last Seen: {getTimeSince(latest.time)}
                </span>
            </div>

            {/* VITALS GRID */}
            <div className="grid grid-cols-3 divide-x divide-gray-800/50 border-b border-gray-800/50">
                <Vital label="Latency" value={`${latest.latency_ms?.toFixed(1) || '--'}ms`} />
                <Vital label="Loss" value={`${latest.packet_loss?.toFixed(2) || '--'}%`} />
                <Vital label="Uptime" value={`${latest.uptime_pct?.toFixed(1) || '--'}%`} />
            </div>

            {/* CONTEXT */}
            <div className="p-4 space-y-4">
                <div className="space-y-1">
                    <h4 className="text-[10px] uppercase text-gray-500 tracking-widest font-bold">Topology</h4>
                    <div className="text-sm text-gray-300 font-mono">
                        Role: <span className="text-purple-400">Primary Edge</span>
                    </div>
                    <div className="text-sm text-gray-300 font-mono">
                        Target: <span className="text-gray-500">None</span>
                    </div>
                </div>

                <div className="pt-2">
                    {isInspectLocked ? (
                        <button
                            onClick={exitInspectMode}
                            className="w-full py-2 bg-gray-800 hover:bg-gray-700 text-xs text-white uppercase tracking-wider rounded transition-colors font-bold"
                        >
                            Resume Live View
                        </button>
                    ) : (
                        <div className="text-center text-[10px] text-gray-600 italic">
                            Live Data Streaming...
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function Vital({ label, value }) {
    return (
        <div className="p-4 text-center">
            <div className="text-[10px] uppercase text-gray-500 mb-1">{label}</div>
            <div className="text-xl font-mono text-white font-light">{value}</div>
        </div>
    );
}
