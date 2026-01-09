import React, { useState } from 'react';
import { useDashboard, TIME_RANGES } from '../../context/DashboardContext';
import { NODE_STATE } from '../../logic/nodeState';
import { ChevronDown, ChevronRight, Info } from 'lucide-react';

export function Sidebar() {
    const {
        timeRange, setTimeRange,
        regionFilter, setRegionFilter,
        statusFilter, setStatusFilter,
        isSidebarOpen,
        isDesktop,
        closeSidebar
    } = useDashboard();

    // Classes based on responsive state
    const sidebarClasses = isDesktop
        ? 'w-64 h-screen fixed left-0 top-0 z-[9999]'
        : `w-64 h-screen fixed left-0 top-0 z-[9999] transform transition-transform duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`;

    // Focus Trap / Accessibility
    // If hidden (mobile closed), we should hide from screen readers
    const ariaHidden = !isDesktop && !isSidebarOpen;

    return (
        <>
            {/* Backdrop (Mobile Only) */}
            {!isDesktop && isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/60 z-[9998] backdrop-blur-sm"
                    onClick={closeSidebar}
                    aria-label="Close sidebar"
                    role="button"
                    tabIndex="0"
                />
            )}

            <aside
                className={`${sidebarClasses} bg-[#0a0b10] border-r border-[#1f1f2e] flex flex-col`}
                aria-hidden={ariaHidden}
            >
                {/* 1. BRAND & ENV */}
                <div className="p-6 border-b border-zinc-900">
                    <h1 className="text-lg font-bold text-white tracking-widest uppercase mb-2">
                        FiberStack
                        <span className="text-zinc-500 text-xs ml-1 align-top">LITE</span>
                    </h1>
                    <div className="flex items-center space-x-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_var(--status-healthy)]" />
                        <span className="text-[10px] text-zinc-500 font-mono tracking-widest uppercase">
                            ENV: SANDBOX
                        </span>
                    </div>
                </div>

                {/* 2. CONTROL SURFACE */}
                <div className="flex-1 overflow-y-auto p-4 space-y-8">

                    {/* SCOPE: TIME */}
                    <ControlGroup label="Time Scope">
                        <div className="grid grid-cols-3 gap-1 bg-zinc-900/50 p-1 rounded border border-zinc-800" role="group" aria-label="Select Time Range">
                            {Object.values(TIME_RANGES).map(range => (
                                <button
                                    key={range}
                                    onClick={() => setTimeRange(range)}
                                    className={`
                                        min-h-[44px] text-[10px] font-mono py-2 rounded transition-all focus:ring-1 focus:ring-zinc-700 focus:outline-none
                                        ${timeRange === range
                                            ? 'bg-white text-black font-bold shadow-lg'
                                            : 'text-zinc-500 hover:text-zinc-300'}
                                    `}
                                    aria-pressed={timeRange === range}
                                >
                                    {range}
                                </button>
                            ))}
                        </div>
                    </ControlGroup>

                    {/* SCOPE: REGION */}
                    <ControlGroup label="Region">
                        <select
                            value={regionFilter}
                            onChange={(e) => setRegionFilter(e.target.value)}
                            className="w-full min-h-[44px] bg-[#0e0e11] text-zinc-300 text-xs p-2 rounded border border-zinc-800 focus:border-zinc-600 outline-none font-mono focus:ring-1 focus:ring-zinc-700"
                            aria-label="Filter by Region"
                        >
                            <option value="ALL">GLOBAL (ALL)</option>
                            <option value="GH">GHANA (GH)</option>
                            <option value="NG">NIGERIA (NG)</option>
                            <option value="KE">KENYA (KE)</option>
                        </select>
                    </ControlGroup>

                    {/* FILTER: STATUS */}
                    <ControlGroup label="Control Status">
                        <div className="space-y-2" role="group" aria-label="Filter by Status">
                            <StatusToggle
                                label="SECURED"
                                color="emerald"
                                active={statusFilter === 'ALL' || statusFilter === NODE_STATE.HEALTHY}
                                onClick={() => setStatusFilter(statusFilter === NODE_STATE.HEALTHY ? 'ALL' : NODE_STATE.HEALTHY)}
                            />
                            <StatusToggle
                                label="CONTESTED"
                                color="amber"
                                active={statusFilter === 'ALL' || statusFilter === NODE_STATE.DEGRADED}
                                onClick={() => setStatusFilter(statusFilter === NODE_STATE.DEGRADED ? 'ALL' : NODE_STATE.DEGRADED)}
                            />
                            <StatusToggle
                                label="COMPROMISED"
                                color="red"
                                active={statusFilter === 'ALL' || statusFilter === NODE_STATE.CRITICAL}
                                onClick={() => setStatusFilter(statusFilter === NODE_STATE.CRITICAL ? 'ALL' : NODE_STATE.CRITICAL)}
                            />
                        </div>
                    </ControlGroup>

                    {/* FOOTER SPACER */}
                    <div className="flex-1" />

                </div>

                {/* 3. FOOTER */}
                <div className="p-4 border-t border-zinc-900">
                    <div className="text-[10px] text-zinc-700 font-mono text-center tracking-widest">
                        v1.0.0 (BLACK SIGNAL)
                    </div>
                </div>
            </aside>
        </>
    );
}

function ControlGroup({ label, children }) {
    return (
        <div className="space-y-3">
            <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-[0.2em] font-sans">
                {label}
            </h3>
            {children}
        </div>
    );
}

function Accordion({ label, children }) {
    const [isOpen, setIsOpen] = useState(false);
    return (
        <div>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between text-[10px] font-bold text-zinc-600 uppercase tracking-[0.2em] hover:text-white transition-colors focus:outline-none"
                aria-expanded={isOpen}
            >
                <div className="flex items-center space-x-2">
                    <Info size={12} />
                    <span>{label}</span>
                </div>
                {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {isOpen && (
                <div className="animate-in slide-in-from-top-1 fade-in duration-200">
                    {children}
                </div>
            )}
        </div>
    );
}

function StatusToggle({ label, color, active, onClick }) {
    const colorMap = {
        emerald: { bg: 'bg-[hsl(var(--status-healthy))]', border: 'border-[hsla(var(--status-healthy)/0.2)]', bgFade: 'bg-[hsla(var(--status-healthy)/0.05)]' },
        amber: { bg: 'bg-[hsl(var(--status-degraded))]', border: 'border-[hsla(var(--status-degraded)/0.2)]', bgFade: 'bg-[hsla(var(--status-degraded)/0.05)]' },
        red: { bg: 'bg-[hsl(var(--status-critical))]', border: 'border-[hsla(var(--status-critical)/0.2)]', bgFade: 'bg-[hsla(var(--status-critical)/0.05)]' }
    };
    const c = colorMap[color] || colorMap.emerald;

    return (
        <button
            onClick={onClick}
            className={`
                w-full min-h-[44px] flex items-center justify-between px-3 py-2 rounded text-[10px] font-mono border transition-all focus:outline-none
                ${active
                    ? `${c.border} ${c.bgFade} text-zinc-200`
                    : 'border-transparent text-zinc-600 hover:text-zinc-400'}
            `}
            aria-pressed={active}
        >
            <span className="tracking-widest">{label}</span>
            <span className={`w-2 h-2 rounded-full ${active ? c.bg : 'bg-zinc-800'}`} />
        </button>
    );
}
