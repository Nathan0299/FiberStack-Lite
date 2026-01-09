import React, { createContext, useContext, useState, useMemo, useEffect } from 'react';

// Time Window Contracts
export const TIME_RANGES = {
    LIVE: 'LIVE',
    MIN_5: '5m',
    HOUR_1: '1h'
};

// Breakpoint
const DESKTOP_BREAKPOINT = 1024;

const DashboardContext = createContext();

export function DashboardProvider({ children }) {
    // 1. Control Surface State
    const [timeRange, setTimeRange] = useState(TIME_RANGES.LIVE);
    const [regionFilter, setRegionFilter] = useState('ALL');
    const [statusFilter, setStatusFilter] = useState('ALL');

    // 2. Inspection Authority (Lock Mode)
    const [inspectNodeId, setInspectNodeId] = useState(null);
    const [isInspectLocked, setIsInspectLocked] = useState(false);

    // 3. Sidebar State (Responsive)
    const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
        // Check localStorage first
        const saved = localStorage.getItem('sidebarOpen');
        if (saved !== null) return saved === 'true';
        // Default: open on desktop
        return typeof window !== 'undefined' && window.innerWidth >= DESKTOP_BREAKPOINT;
    });

    const [isDesktop, setIsDesktop] = useState(
        typeof window !== 'undefined' && window.innerWidth >= DESKTOP_BREAKPOINT
    );

    // Viewport listener
    useEffect(() => {
        const handleResize = () => {
            const desktop = window.innerWidth >= DESKTOP_BREAKPOINT;
            setIsDesktop(desktop);
            // Auto-open sidebar on desktop, close on mobile
            if (desktop && !isSidebarOpen) setIsSidebarOpen(true);
        };
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, [isSidebarOpen]);

    // Persist sidebar preference
    useEffect(() => {
        localStorage.setItem('sidebarOpen', String(isSidebarOpen));
    }, [isSidebarOpen]);

    const toggleSidebar = () => setIsSidebarOpen(prev => !prev);
    const closeSidebar = () => setIsSidebarOpen(false);

    // Actions
    const enterInspectMode = (nodeId) => {
        setInspectNodeId(nodeId);
        setIsInspectLocked(true);
    };

    const exitInspectMode = () => {
        setInspectNodeId(null);
        setIsInspectLocked(false);
    };



    // 4. Demo Mode (Day 90 Polish)
    const [isDemoMode, setIsDemoMode] = useState(() => {
        // Priority: 1. URL Param (?demo=true), 2. LocalStorage
        if (typeof window !== 'undefined') {
            const params = new URLSearchParams(window.location.search);
            if (params.get('demo') === 'true') {
                localStorage.setItem('fiber_demo_mode', 'true');
                return true;
            }
        }
        return localStorage.getItem('fiber_demo_mode') === 'true';
    });

    const toggleDemoMode = () => {
        const next = !isDemoMode;
        setIsDemoMode(next);
        localStorage.setItem('fiber_demo_mode', String(next));
        window.location.reload();
    };

    // Hotkey Listener (Alt+D)
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.altKey && e.code === 'KeyD') {
                e.preventDefault();
                toggleDemoMode();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isDemoMode]); // Dependency needed to ensure toggle gets current state or functional update is used (which it is not above, wait - toggleDemoMode closes over isDemoMode)

    const value = useMemo(() => ({
        // Controls
        timeRange, setTimeRange,
        regionFilter, setRegionFilter,
        statusFilter, setStatusFilter,

        // Inspection State
        inspectNodeId,
        isInspectLocked,
        enterInspectMode,
        exitInspectMode,

        // Sidebar (Responsive)
        isSidebarOpen,
        isDesktop,
        toggleSidebar,
        closeSidebar,

        // Demo Mode
        isDemoMode,
        toggleDemoMode
    }), [timeRange, regionFilter, statusFilter, inspectNodeId, isInspectLocked, isSidebarOpen, isDesktop, isDemoMode]);

    return (
        <DashboardContext.Provider value={value}>
            {children}
        </DashboardContext.Provider>
    );
}

export function useDashboard() {
    const context = useContext(DashboardContext);
    if (!context) throw new Error('useDashboard must be used within DashboardProvider');
    return context;
}

