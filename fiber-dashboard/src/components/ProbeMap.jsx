import React, { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, useMap } from 'react-leaflet';
import { divIcon } from 'leaflet';
import { getCoords } from '../data/regions';
import { resolveNodeState, NODE_STATE } from '../logic/nodeState';
import { useDashboard } from '../context/DashboardContext';
import { Circle, HelpCircle, ChevronDown } from 'lucide-react';
import 'leaflet/dist/leaflet.css';

const MAP_CENTER = [6.0, 10.0]; // Center on West Africa
const MAP_ZOOM_DESKTOP = 4;
const MAP_ZOOM_MOBILE = 3;

/**
 * TERRITORY MARKER FACTORY (Command-Grade)
 * 
 * Infrastructure is geopolitical. Maps show:
 * - Zones of influence (glow radius)
 * - Control decay (opacity)
 * - No panic animations
 */
const createTerritoryIcon = (state, isSelected) => {
    // Core size: Small central point
    const coreSize = isSelected ? 12 : 8;
    // Influence size: Larger glow representing zone of control
    const influenceSize = isSelected ? 40 : 28;

    let coreColor = '';
    let glowColor = '';
    let opacity = 1;

    switch (state) {
        case NODE_STATE.HEALTHY:
            coreColor = 'hsl(var(--status-healthy))';
            glowColor = '0, 255, 157';
            opacity = 1;
            break;
        case NODE_STATE.DEGRADED:
            coreColor = 'hsl(var(--status-degraded))';
            glowColor = '255, 183, 0';
            opacity = 0.8;
            break;
        case NODE_STATE.CRITICAL:
        case NODE_STATE.DOWN:
            coreColor = 'hsl(var(--status-critical))';
            glowColor = '255, 0, 60';
            opacity = 0.6;
            break;
        case NODE_STATE.STALE:
        default:
            coreColor = 'hsl(var(--status-stale))';
            glowColor = '60, 60, 60';
            opacity = 0.3;
            break;
    }

    // Territory visualization: Core point with zone-of-influence glow
    // No blinking. Command systems do not panic.
    const html = `
        <div style="
            position: relative;
            width: ${influenceSize}px;
            height: ${influenceSize}px;
            display: flex;
            align-items: center;
            justify-content: center;
        ">
            <!-- Zone of Influence (glow) -->
            <div style="
                position: absolute;
                width: ${influenceSize}px;
                height: ${influenceSize}px;
                background: radial-gradient(circle, rgba(${glowColor}, ${opacity * 0.4}) 0%, rgba(${glowColor}, 0) 70%);
                border-radius: 50%;
                transition: all 0.7s linear;
            "></div>
            <!-- Core (solid) -->
            <div style="
                width: ${coreSize}px;
                height: ${coreSize}px;
                background-color: ${coreColor};
                border: 1px solid #050505;
                border-radius: 50%;
                opacity: ${opacity};
                z-index: 10;
                transition: all 0.7s linear;
            "></div>
        </div>
    `;

    return divIcon({
        className: 'bg-transparent border-none',
        html: html,
        iconSize: [influenceSize, influenceSize],
        iconAnchor: [influenceSize / 2, influenceSize / 2],
        popupAnchor: [0, -influenceSize / 2]
    });
};

function Legend({ isMobile }) {
    const [collapsed, setCollapsed] = useState(isMobile);

    useEffect(() => {
        setCollapsed(isMobile);
    }, [isMobile]);

    if (collapsed) {
        return (
            <div className="leaflet-bottom leaflet-right m-4 pointer-events-auto">
                <button
                    onClick={() => setCollapsed(false)}
                    className="bg-[#0e0e11] border border-zinc-800 p-2 rounded shadow-xl text-zinc-500 hover:text-white transition-colors duration-700"
                >
                    <HelpCircle size={16} />
                </button>
            </div>
        );
    }

    return (
        <div className="leaflet-bottom leaflet-right m-4 pointer-events-auto">
            <div className="matte-card p-3 min-w-[130px]">
                <div className="flex justify-between items-center mb-2 border-b border-zinc-800 pb-2">
                    <span className="text-[9px] font-bold uppercase tracking-[0.2em] text-zinc-500">Territory</span>
                    <button onClick={() => setCollapsed(true)}>
                        <ChevronDown size={12} className="text-zinc-600 hover:text-white transition-colors duration-700" />
                    </button>
                </div>
                <div className="space-y-1.5">
                    <LegendItem color="hsl(var(--status-healthy))" label="SECURED" />
                    <LegendItem color="hsl(var(--status-degraded))" label="CONTESTED" />
                    <LegendItem color="hsl(var(--status-critical))" label="COMPROMISED" />
                    <LegendItem color="hsl(var(--status-stale))" label="BLACKOUT" />
                </div>
            </div>
        </div>
    );
}

const LegendItem = ({ color, label }) => (
    <div className="flex items-center space-x-2">
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
        <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">{label}</span>
    </div>
);

export default function ProbeMap({ metrics, loading }) {
    const {
        enterInspectMode,
        inspectNodeId,
        regionFilter,
        statusFilter,
        isDesktop
    } = useDashboard();

    // 1. FILTERING
    const filteredMetrics = useMemo(() => metrics.filter(m => {
        if (regionFilter !== 'ALL') {
            const code = m.country || getCoords(m.region)?.country;
            if (code !== regionFilter) return false;
        }
        const state = resolveNodeState(m, m);
        if (statusFilter !== 'ALL' && state !== statusFilter) return false;
        return true;
    }), [metrics, regionFilter, statusFilter]);

    if (loading && metrics.length === 0) {
        return (
            <div className="w-full h-full rounded bg-[#050505] border border-zinc-900 flex items-center justify-center">
                <span className="text-zinc-700 font-mono text-[9px] tracking-[0.3em] uppercase">AWAITING SIGNAL</span>
            </div>
        );
    }

    return (
        <div className="w-full h-full rounded overflow-hidden probe-map-container relative border border-zinc-900 bg-[#050505]">
            <MapContainer
                center={MAP_CENTER}
                zoom={isDesktop ? MAP_ZOOM_DESKTOP : MAP_ZOOM_MOBILE}
                className="h-full w-full bg-[#050505]"
                scrollWheelZoom={isDesktop}
                dragging={isDesktop}
                touchZoom={true}
                zoomControl={false}
                attributionControl={false}
            >
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                />

                {filteredMetrics.map((m) => {
                    const coords = getCoords(m.region);
                    if (!coords) return null;

                    const state = resolveNodeState(m, m);
                    const isSelected = inspectNodeId === m.node_id;

                    return (
                        <Marker
                            key={m.node_id}
                            position={[coords.lat, coords.lng]}
                            icon={createTerritoryIcon(state, isSelected)}
                            eventHandlers={{
                                click: () => enterInspectMode(m.node_id),
                            }}
                            title={`Territory ${m.node_id}`}
                        />
                    );
                })}

                <Legend isMobile={!isDesktop} />

            </MapContainer>
        </div>
    );
}
