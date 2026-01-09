const API_BASE = import.meta.env.VITE_API_URL || '';

export async function fetchMetrics(params = {}) {
    const query = new URLSearchParams({
        limit: params.limit || 50,
        offset: params.offset || 0,
        ...(params.node_id && { node_id: params.node_id })
    });

    const response = await fetch(`${API_BASE}/api/metrics?${query}`);
    if (!response.ok) throw new Error('Failed to fetch metrics');
    return response.json();
}

export async function fetchStatus() {
    const response = await fetch(`${API_BASE}/api/status`);
    if (!response.ok) throw new Error('Failed to fetch status');
    return response.json();
}

// Day 43: Node Management
export async function fetchNodes() {
    const response = await fetch(`${API_BASE}/api/nodes`);
    if (!response.ok) throw new Error('Failed to fetch nodes');
    return response.json();
}

export async function createNode(nodeData) {
    const response = await fetch(`${API_BASE}/api/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nodeData)
    });
    if (!response.ok) throw new Error('Failed to create node');
    return response.json();
}

export async function deleteNode(nodeId) {
    const response = await fetch(`${API_BASE}/api/nodes/${nodeId}`, {
        method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to delete node');
    return response.json();
}
