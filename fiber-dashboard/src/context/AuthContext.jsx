import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);
const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Day 78: Authentication Context Provider
 * 
 * Security Properties:
 * - Tokens are server-issued (not client-generated)
 * - Roles come from server (not user-selectable)
 * - Permissions are fetched from server
 */
export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Fetch user info from server using stored token
    const fetchUserFromServer = useCallback(async (token) => {
        try {
            const res = await fetch(`${API_BASE}/api/auth/me`, {
                headers: { Authorization: `Bearer ${token}` }
            });

            if (res.ok) {
                const data = await res.json();
                if (data.status === 'ok' && data.data.authenticated) {
                    return data.data;
                }
            }

            // Token invalid or expired
            localStorage.removeItem('fiber_token');
            return null;

        } catch (e) {
            console.error('Auth fetch failed:', e);
            return null;
        }
    }, []);

    // Initialize auth state on mount
    useEffect(() => {
        const token = localStorage.getItem('fiber_token');
        if (token) {
            fetchUserFromServer(token).then(userData => {
                setUser(userData);
                setLoading(false);
            });
        } else {
            setLoading(false);
        }
    }, [fetchUserFromServer]);

    /**
     * Login with username and password.
     * Token is issued by server, not generated client-side.
     */
    const login = async (username, password) => {
        setError(null);

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await res.json();

            if (!res.ok) {
                setError(data.detail || 'Login failed');
                return null;
            }

            // Store server-issued token
            localStorage.setItem('fiber_token', data.data.token);

            // Set user state from server response
            const userData = {
                authenticated: true,
                username: username,
                role: data.data.role,
                permissions: data.data.permissions,
                expiresAt: data.data.expires_at
            };

            setUser(userData);
            return userData;

        } catch (e) {
            setError('Network error');
            console.error('Login failed:', e);
            return null;
        }
    };

    /**
     * Logout - clear token and user state.
     */
    const logout = () => {
        setUser(null);
        localStorage.removeItem('fiber_token');
    };

    /**
     * Check if current user has a permission.
     * Uses server-provided permissions list.
     */
    const can = (permission) => {
        if (!user?.permissions) return false;
        return user.permissions.includes(permission);
    };

    /**
     * Get auth headers for API requests.
     */
    const getAuthHeaders = () => {
        const token = localStorage.getItem('fiber_token');
        return token ? { Authorization: `Bearer ${token}` } : {};
    };

    const value = {
        user,
        loading,
        error,
        login,
        logout,
        can,
        getAuthHeaders,
        isAuthenticated: !!user?.authenticated
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

/**
 * Hook to access auth context.
 */
export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
}
