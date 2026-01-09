import React, { useState, useEffect } from 'react';
import { fetchNodes, createNode, deleteNode } from '../services/api';
import { usePermission, PERMISSIONS } from '../hooks/usePermission';

export function AdminPanel({ onClose }) {
    const [nodes, setNodes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Permissions
    const canCreate = usePermission(PERMISSIONS.CREATE_NODE);
    const canDelete = usePermission(PERMISSIONS.DELETE_NODE);

    // Form State
    const [formData, setFormData] = useState({
        node_id: crypto.randomUUID(),
        country: 'GH',
        region: 'Accra',
        lat: 5.6037,
        lng: -0.1870
    });

    useEffect(() => {
        loadNodes();
    }, []);

    async function loadNodes() {
        try {
            setLoading(true);
            const data = await fetchNodes();
            setNodes(data.data || []);
            setError(null);
        } catch (err) {
            setError('Failed to load nodes');
        } finally {
            setLoading(false);
        }
    }

    async function handleAdd(e) {
        e.preventDefault();
        try {
            await createNode({ ...formData, status: 'registered' });
            await loadNodes();
            // Reset ID for next node
            setFormData(prev => ({ ...prev, node_id: crypto.randomUUID() }));
        } catch (err) {
            alert('Failed to add node: ' + err.message);
        }
    }

    async function handleDelete(nodeId) {
        if (!window.confirm('Are you sure you want to soft-delete this node?')) return;
        try {
            await deleteNode(nodeId);
            await loadNodes();
        } catch (err) {
            alert('Failed to delete node: ' + (err.message || 'Permission denied'));
        }
    }

    // Health Logic
    function getHealthStatus(lastSeen) {
        if (!lastSeen) return 'unknown';
        const diff = (new Date() - new Date(lastSeen)) / 1000; // seconds
        return diff < 300 ? 'healthy' : 'unhealthy';
    }

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl h-[80vh] flex flex-col shadow-2xl">

                {/* Header */}
                <div className="p-6 border-b border-slate-700 flex justify-between items-center bg-slate-800/50">
                    <div>
                        <h2 className="text-xl font-bold text-white">Node Management</h2>
                        <p className="text-slate-400 text-sm">Control Plane (Day 43) • RBAC Enforced</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-white px-3 py-1 hover:bg-white/10 rounded"
                    >
                        Close [ESC]
                    </button>
                </div>

                <div className="flex-1 overflow-hidden flex">

                    {/* Sidebar Form */}
                    <div className="w-1/3 p-6 border-r border-slate-700 bg-slate-800/20 overflow-y-auto">
                        <h3 className="text-purple-300 font-semibold mb-4">Register New Node</h3>

                        {canCreate ? (
                            <form onSubmit={handleAdd} className="space-y-4">
                                <div>
                                    <label className="block text-xs text-slate-400 mb-1">Node UUID</label>
                                    <div className="flex space-x-2">
                                        <input
                                            type="text"
                                            value={formData.node_id}
                                            readOnly
                                            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-300"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setFormData(p => ({ ...p, node_id: crypto.randomUUID() }))}
                                            className="text-xs bg-slate-700 px-2 rounded hover:bg-slate-600 text-white"
                                        >
                                            ↻
                                        </button>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Country</label>
                                        <select
                                            value={formData.country}
                                            onChange={e => setFormData({ ...formData, country: e.target.value })}
                                            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm text-white"
                                        >
                                            <option value="GH">Ghana (GH)</option>
                                            <option value="NG">Nigeria (NG)</option>
                                            <option value="KE">Kenya (KE)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Region</label>
                                        <input
                                            type="text"
                                            value={formData.region}
                                            onChange={e => setFormData({ ...formData, region: e.target.value })}
                                            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm text-white"
                                        />
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Lat</label>
                                        <input
                                            type="number" step="any"
                                            value={formData.lat}
                                            onChange={e => setFormData({ ...formData, lat: parseFloat(e.target.value) })}
                                            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Lng</label>
                                        <input
                                            type="number" step="any"
                                            value={formData.lng}
                                            onChange={e => setFormData({ ...formData, lng: parseFloat(e.target.value) })}
                                            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm text-white"
                                        />
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    className="w-full bg-purple-600 hover:bg-purple-500 text-white py-2 rounded font-semibold text-sm transition-colors"
                                >
                                    Register Node
                                </button>
                            </form>
                        ) : (
                            <div className="p-4 bg-slate-800/50 rounded border border-slate-700 text-slate-400 text-xs text-center">
                                Permission Denied<br />
                                (Requires OPERATOR role)
                            </div>
                        )}
                    </div>

                    {/* Node List */}
                    <div className="w-2/3 p-6 overflow-y-auto">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-purple-300 font-semibold">Active Fleet ({nodes.length})</h3>
                            <button onClick={loadNodes} className="text-xs text-slate-400 hover:text-white">Refresh</button>
                        </div>

                        {loading ? (
                            <div className="text-slate-500 text-center py-10">Loading fleet data...</div>
                        ) : error ? (
                            <div className="text-red-400 text-center py-10">{error}</div>
                        ) : nodes.length === 0 ? (
                            <div className="text-slate-500 text-center py-10 bg-slate-800/30 rounded-lg border border-slate-700 border-dashed">
                                No nodes registered. Add one to start.
                            </div>
                        ) : (
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="text-xs text-slate-500 border-b border-slate-700">
                                        <th className="py-2 pl-2">Status</th>
                                        <th className="py-2">Region</th>
                                        <th className="py-2">Last Seen</th>
                                        <th className="py-2 pr-2 text-right">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="text-sm">
                                    {nodes.map(node => {
                                        const health = getHealthStatus(node.last_seen);
                                        const isStale = health === 'unhealthy';

                                        return (
                                            <tr key={node.node_id} className="border-b border-slate-800 hover:bg-slate-800/30">
                                                <td className="py-3 pl-2">
                                                    <div className="flex items-center space-x-2">
                                                        <span className={`w-2 h-2 rounded-full ${node.status === 'reporting' ? 'bg-green-400' :
                                                            node.status === 'registered' ? 'bg-blue-400' :
                                                                'bg-slate-500'
                                                            }`} />
                                                        <span className="text-slate-300 capitalize text-xs">{node.status}</span>
                                                    </div>
                                                </td>
                                                <td className="py-3">
                                                    <div className="font-medium text-white">{node.region}</div>
                                                    <div className="text-xs text-slate-500 font-mono">{node.node_id.slice(0, 8)}...</div>
                                                </td>
                                                <td className="py-3">
                                                    <div className={`text-xs ${isStale ? 'text-red-400 font-bold' : 'text-slate-400'}`}>
                                                        {node.last_seen
                                                            ? new Date(node.last_seen).toLocaleTimeString()
                                                            : 'Never'}
                                                    </div>
                                                    {isStale && node.last_seen && (
                                                        <div className="text-[10px] text-red-500/70">check connectivity</div>
                                                    )}
                                                </td>
                                                <td className="py-3 pr-2 text-right">
                                                    {canDelete && (
                                                        <button
                                                            onClick={() => handleDelete(node.node_id)}
                                                            className="text-xs text-slate-500 hover:text-red-400 transition-colors"
                                                        >
                                                            Delete
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

