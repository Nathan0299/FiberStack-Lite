import React, { useState, useRef, useEffect } from 'react';
import {
    LineChart, Line, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, ReferenceLine
} from 'recharts';

export function MetricChart({ data, dataKey, title, unit, color, threshold }) {
    const [focusedIndex, setFocusedIndex] = useState(null);
    const chartRef = useRef(null);

    // Dynamic Aria Label
    const latestValue = data && data.length > 0 ? data[data.length - 1][dataKey] : 0;
    const trend = data && data.length > 1 && data[data.length - 1][dataKey] > data[data.length - 2][dataKey] ? 'rising' : 'falling';
    const ariaLabel = `Line Chart for ${dataKey}. Current value: ${latestValue?.toFixed(1)}${unit}, trend is ${trend}. Use Left/Right arrow keys to navigate data points.`;

    // Keyboard Navigation
    const handleKeyDown = (e) => {
        if (!data || data.length === 0) return;

        if (e.key === 'ArrowRight') {
            setFocusedIndex(prev => (prev === null || prev >= data.length - 1 ? 0 : prev + 1));
            e.preventDefault();
        } else if (e.key === 'ArrowLeft') {
            setFocusedIndex(prev => (prev === null || prev <= 0 ? data.length - 1 : prev - 1));
            e.preventDefault();
        } else if (e.key === 'Escape') {
            setFocusedIndex(null);
            chartRef.current?.blur();
        }
    };

    // Responsive Tick Interval
    const [tickInterval, setTickInterval] = useState('preserveStartEnd');
    useEffect(() => {
        const updateTicks = () => {
            const width = window.innerWidth;
            if (width < 320) setTickInterval(100); // effectively min/max
            else if (width < 400) setTickInterval(50);
            else setTickInterval('preserveStartEnd');
        };
        window.addEventListener('resize', updateTicks);
        updateTicks();
        return () => window.removeEventListener('resize', updateTicks);
    }, []);

    if (!data || data.length === 0) {
        return (
            <div className="h-48 bg-[#050505] border border-zinc-900 rounded flex items-center justify-center">
                <span className="text-zinc-600 text-[10px] font-mono tracking-widest uppercase italic">Signal Unavailable</span>
            </div>
        );
    }

    return (
        <div
            className="focus:ring-1 focus:ring-zinc-700 outline-none transition-shadow h-full"
            tabIndex="0"
            role="application"
            aria-label={ariaLabel}
            onKeyDown={handleKeyDown}
            ref={chartRef}
        >
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    {title}
                </h3>
                {focusedIndex !== null && (
                    <span className="text-[10px] font-mono text-white bg-zinc-800 px-2 py-0.5 rounded border border-zinc-700 tabular-nums">
                        SCAN: {new Date(data[focusedIndex].time).toLocaleTimeString()} • {data[focusedIndex][dataKey].toFixed(1)}{unit}
                    </span>
                )}
            </div>

            <ResponsiveContainer width="100%" height={160}>
                <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#ffffff10" vertical={false} />
                    <XAxis
                        dataKey="time"
                        tick={{ fill: '#52525b', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' }}
                        tickFormatter={(t) => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        interval={tickInterval}
                        axisLine={false}
                        tickLine={false}
                    />
                    <YAxis
                        tick={{ fill: '#52525b', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' }}
                        domain={['auto', 'auto']}
                        axisLine={false}
                        tickLine={false}
                        width={40}
                    />
                    <Tooltip
                        contentStyle={{
                            background: '#0e0e11',
                            border: '1px solid #27272a',
                            borderRadius: '2px',
                            boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
                            padding: '8px 12px'
                        }}
                        labelStyle={{ color: '#71717a', marginBottom: '4px', fontSize: '10px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.1em' }}
                        itemStyle={{ fontSize: '11px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: 'white' }}
                        labelFormatter={(t) => new Date(t).toLocaleString()}
                        formatter={(value) =>
                            value != null
                                ? [`${Number(value).toFixed(2)} ${unit}`, 'VALUE']
                                : ['—', 'VALUE']
                        }
                        cursor={{ stroke: '#ffffff20', strokeWidth: 1 }}
                        active={focusedIndex !== null}
                        payload={focusedIndex !== null ? [data[focusedIndex]] : undefined}
                        coordinate={focusedIndex !== null ? { x: 0, y: 0 } : undefined}
                    />
                    <Line
                        type="stepAfter"
                        dataKey={dataKey}
                        stroke={color}
                        strokeWidth={1.5}
                        dot={focusedIndex !== null ? ((props) => {
                            if (props.index === focusedIndex) return <circle cx={props.cx} cy={props.cy} r={4} fill="white" />;
                            return <></>;
                        }) : false}
                        activeDot={{ r: 3, fill: 'white', strokeWidth: 0 }}
                        isAnimationActive={false}
                    />
                    {threshold !== undefined && (
                        <ReferenceLine
                            y={threshold}
                            stroke="#ff003c"
                            strokeDasharray="4 4"
                            strokeOpacity={0.5}
                            label={{
                                value: `LIMIT: ${threshold}${unit}`,
                                fill: '#ff003c',
                                fontSize: 8,
                                position: 'insideTopRight',
                                fontWeight: 'bold',
                                opacity: 0.8
                            }}
                        />
                    )}

                    {focusedIndex !== null && (
                        <ReferenceLine x={data[focusedIndex].time} stroke="#ffffff30" />
                    )}
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
