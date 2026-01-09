import React from 'react';
import { Activity, CheckCircle, AlertTriangle, ArrowUpRight, ArrowDownRight } from 'lucide-react';

export function KPICard({ title, value, unit, trend, type = 'neutral', loading = false }) {
    if (loading) {
        return (
            <div className="matte-card p-5 h-32 w-full flex flex-col justify-between animate-pulse">
                <div className="h-3 w-20 bg-zinc-800 rounded mb-4" />
                <div className="h-8 w-16 bg-zinc-800 rounded" />
            </div>
        );
    }

    const semantics = getSemantics(type);

    return (
        <div className={`matte-card p-5 flex flex-col justify-between hover:bg-[#12121a] transition-colors relative overflow-hidden group border-l-4 ${semantics.border}`}>

            {/* Header: Label */}
            <div className="flex justify-between items-start mb-1">
                <span className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 font-bold font-sans">
                    {title}
                </span>
                {/* Optional Status Icon (Subtle) */}
                <div className={`${semantics.text} opacity-50`}>
                    <semantics.icon size={14} />
                </div>
            </div>

            {/* Main Value: Large Mono */}
            <div className="flex items-baseline space-x-1.5 mt-2">
                <span className="text-3xl font-bold text-white font-mono-num tracking-tight tabular-nums">
                    {value}
                </span>
                <span className="text-[11px] text-zinc-500 font-mono uppercase">
                    {unit}
                </span>
            </div>

            {/* Trend / Context */}
            {trend && (
                <div className="flex items-center text-[10px] mt-2 space-x-1.5 font-mono">
                    <span className={`flex items-center ${trend > 0 ? 'text-emerald-500' : 'text-zinc-500'}`}>
                        {trend > 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                        {Math.abs(trend)}%
                    </span>
                    <span className="text-zinc-600">vs 1h avg</span>
                </div>
            )}
        </div>
    );
}

function getSemantics(type) {
    switch (type) {
        case 'healthy':
            return {
                border: 'border-l-[hsl(var(--status-healthy))]',
                text: 'text-[hsl(var(--status-healthy))]',
                icon: CheckCircle
            };
        case 'degraded':
            return {
                border: 'border-l-[hsl(var(--status-degraded))]',
                text: 'text-[hsl(var(--status-degraded))]',
                icon: AlertTriangle
            };
        case 'critical':
            return {
                border: 'border-l-[hsl(var(--status-critical))]',
                text: 'text-[hsl(var(--status-critical))]',
                icon: AlertTriangle
            };
        case 'neutral':
        default:
            return {
                border: 'border-l-zinc-700',
                text: 'text-zinc-500',
                icon: Activity
            };
    }
}
