import React, { useMemo, useState, useEffect, Suspense, lazy } from 'react';
import { Sidebar } from './components/Layout/Sidebar';
import { MetricsTable } from './components/MetricsTable';
import { ChartsPanel } from './components/ChartsPanel';
import { NodeDetailsPanel } from './components/NodeDetailsPanel';
import { KPICard } from './components/KPICard';
import { useMetrics } from './hooks/useMetrics';
import { useKPIStats } from './hooks/useKPIStats';
import { AuthProvider } from './context/AuthContext';
import { DashboardProvider, useDashboard } from './context/DashboardContext';
import { Menu, RefreshCw } from 'lucide-react';
import { useDemoMode } from './hooks/useDemoMode';
import { SystemPosture } from './components/SystemPosture';

// LAZY LOAD MAP (Code Splitting)
const ProbeMap = lazy(() => {
  // Lazy CSS load to prevent render blocking
  import('leaflet/dist/leaflet.css');
  return import('./components/ProbeMap');
});

// Map Loading Skeleton
const MapSkeleton = () => (
  <div className="w-full h-full bg-[#0a0a0f] animate-pulse flex items-center justify-center">
    <span className="text-xs text-gray-600 font-mono tracking-widest">LOADING SATELLITE FEED...</span>
  </div>
);

function DashboardLayout() {
  const {
    inspectNodeId,
    timeRange,
    isSidebarOpen,
    isDesktop,
    toggleSidebar,
    isDemoMode
  } = useDashboard();

  // 1. DATA INGESTION
  // Live Data
  const { metrics: liveMetrics, loading: liveLoading, error: liveError, lastUpdated: liveUpdated } = useMetrics(30000);

  // Demo Data (Day 90)
  const { demoMetrics } = useDemoMode(isDemoMode);

  // MUX: Choose Source
  const metrics = isDemoMode ? demoMetrics : liveMetrics;
  const loading = isDemoMode ? false : liveLoading;
  const error = isDemoMode ? null : liveError;
  const lastUpdated = isDemoMode ? new Date() : liveUpdated;

  // 2. AGGREGATES
  const stats = useKPIStats(metrics);

  // 3. ADAPTIVE MAP PREFETCH
  // Only prefetch map assets when we have valid metric data (application is ready)
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (metrics.length > 0 && !mapReady) {
      // Adaptive Prefetch Strategy
      const prefetch = () => {
        import('./components/ProbeMap');
        import('leaflet/dist/leaflet.css');
        setMapReady(true);
      };

      // Use idle callback if available, else fallback to small timeout
      if (window.requestIdleCallback) {
        window.requestIdleCallback(prefetch);
      } else {
        setTimeout(prefetch, 500);
      }
    }
  }, [metrics, mapReady]);


  // 4. FAILURE MODES
  if (error && !isDemoMode) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#050505]">
        <div className="text-center p-8 matte-card border-red-900/50">
          <h1 className="text-2xl font-bold text-red-500 mb-2 font-mono tracking-widest text-[hsl(var(--status-critical))]">SIGNAL LOST</h1>
          <p className="text-zinc-500 font-mono mb-4 text-xs tabular-nums">{error}</p>
          <button onClick={() => window.location.reload()} className="px-6 py-2 bg-red-900/20 text-red-200 uppercase text-[10px] tracking-widest rounded hover:bg-red-900/40 border border-red-500/20 transition-all">
            Reconnect Sequence
          </button>
        </div>
      </div>
    );
  }

  const inspectNode = metrics.find(m => m.node_id === inspectNodeId);
  // Dynamic margin: sidebar width on desktop, none on mobile
  const mainMargin = isDesktop ? 'ml-64' : 'ml-0';

  return (
    <div className="flex h-screen bg-[#050505] text-zinc-300 font-sans overflow-hidden selection:bg-white/20">
      {/* LEFT: CONTROL (Sidebar) */}
      <Sidebar />

      {/* RIGHT: CONTENT PANE */}
      <main className={`flex-1 ${mainMargin} flex flex-col h-screen overflow-hidden transition-all duration-300 ease-out bg-[#050505]`}>

        {/* DEMO BANNER (Safety) */}
        {isDemoMode && (
          <div className="flex-none h-6 bg-amber-500/10 border-b border-amber-500/20 flex items-center justify-center">
            <div className="text-[10px] font-bold text-amber-500 uppercase tracking-widest flex items-center space-x-2 font-mono">
              <span className="w-1.5 h-1.5 bg-amber-500 rounded-full animate-pulse" />
              <span>DEMO MODE ACTIVE • SIMULATED DATA</span>
            </div>
          </div>
        )}

        {/* COMMAND BAR — System Posture is the only truth */}
        <header className="flex-none h-12 flex items-center justify-between px-4 lg:px-6 bg-[#050505] border-b border-zinc-900/50 z-10">

          {/* LEFT: Mobile Menu + Sync Status */}
          <div className="flex items-center space-x-4 w-1/4">
            {!isDesktop && (
              <button
                onClick={toggleSidebar}
                className="w-8 h-8 flex items-center justify-center rounded bg-zinc-900 border border-zinc-800 text-zinc-500 hover:text-white transition-colors duration-700 linear"
              >
                <Menu size={14} />
              </button>
            )}
            {loading && (
              <div className="flex items-center space-x-2 text-zinc-600">
                <RefreshCw size={10} className="animate-spin" />
                <span className="text-[9px] font-mono tracking-widest uppercase">SYNC</span>
              </div>
            )}
          </div>

          {/* CENTER: System Posture — The Declarative Truth */}
          <div className="flex-1 flex justify-center">
            <SystemPosture metrics={metrics} />
          </div>

          {/* RIGHT: Timestamp (minimal) */}
          <div className="w-1/4 flex justify-end">
            {lastUpdated && (
              <div className="text-right opacity-40">
                <div className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest tabular-nums">
                  {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            )}
          </div>
        </header>

        {/* WORKSPACE - Scrollable Container */}
        <div className="flex-1 p-4 lg:p-6 flex flex-col gap-4 lg:gap-6 overflow-y-auto">

          {/* 1. MAP (Fixed Height) */}
          <div className="flex-none h-[400px] lg:h-[450px] w-full relative matte-card p-0 overflow-hidden group">
            <Suspense fallback={<MapSkeleton />}>
              <ProbeMap metrics={metrics} loading={loading} />
            </Suspense>

            {/* Title Overlay */}
            <div className="absolute top-4 left-4 pointer-events-none z-[400]">
              <h3 className="text-[10px] uppercase tracking-[0.2em] font-bold text-zinc-500 bg-[#050505] px-2 py-1 border border-zinc-800">
                Live Federation Map
              </h3>
            </div>

            {inspectNodeId && (
              <NodeDetailsPanel node={inspectNode} metrics={metrics.filter(m => m.node_id === inspectNodeId)} />
            )}
          </div>

          {/* 2. ANALYTICS ROW */}
          <div className="flex-none h-auto w-full flex flex-col lg:flex-row gap-4 lg:gap-6">

            {/* KPI COL */}
            <div className="w-full lg:w-64 flex flex-col gap-5">
              <KPICard
                title="RESPONSE INTEGRITY"
                value={stats.avgLatency}
                unit="ms"
                type={stats.avgLatency > 150 ? 'critical' : (stats.avgLatency > 100 ? 'degraded' : 'healthy')}
                loading={loading}
              />
              <KPICard
                title="CONTINUITY INDEX"
                value={stats.avgUptime}
                unit="%"
                type={stats.avgUptime < 98 ? 'critical' : (stats.avgUptime < 99.5 ? 'degraded' : 'healthy')}
                loading={loading}
              />
              <KPICard
                title="SIGNAL DEGRADATION"
                value={stats.avgLoss}
                unit="%"
                type={stats.avgLoss > 2 ? 'critical' : (stats.avgLoss > 0.5 ? 'degraded' : 'neutral')}
                loading={loading}
              />
            </div>

            {/* CHART COL */}
            <div className="flex-1 min-w-0">
              <ChartsPanel metrics={metrics} loading={loading} />
            </div>
          </div>

          {/* 3. INVENTORY TABLE */}
          <div className="flex-none h-[400px] min-h-[150px] overflow-hidden matte-card p-0 flex flex-col">
            <div className="px-4 py-3 border-b border-zinc-900 flex justify-between items-center bg-[#0e0e11]">
              <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em]">
                Active Node Inventory
              </h3>
              <span className="text-[9px] font-mono text-zinc-600 tracking-widest tabular-nums">
                {metrics.length.toString().padStart(3, '0')} // DETECTED
              </span>
            </div>
            <div className="flex-1 overflow-hidden">
              <MetricsTable metrics={metrics} loading={loading} />
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}

export default function App() {
  // Force dark mode class on root for Tailwind
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  return (
    <AuthProvider>
      <DashboardProvider>
        <DashboardLayout />
      </DashboardProvider>
    </AuthProvider>
  );
}
