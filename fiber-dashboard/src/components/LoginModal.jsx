import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export function LoginModal({ onClose }) {
    const { login, error } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username.trim() || !password.trim()) return;

        setIsLoading(true);

        // Attempt login
        const result = await login(username, password);

        setIsLoading(false);

        if (result) {
            // Success
            if (onClose) onClose();
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-purple-900 border border-purple-500/30 p-8 rounded-lg w-96 shadow-2xl">
                <h2 className="text-2xl font-bold mb-6 text-white">Login</h2>

                {error && (
                    <div className="bg-red-500/20 border border-red-500/50 text-red-200 p-3 rounded mb-4 text-sm">
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-purple-200 text-sm mb-1">Username</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full bg-purple-950 border border-purple-600 rounded p-2 text-white focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
                            placeholder="admin"
                            autoFocus
                        />
                    </div>

                    <div>
                        <label className="block text-purple-200 text-sm mb-1">Password</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full bg-purple-950 border border-purple-600 rounded p-2 text-white focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
                            placeholder="••••••"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading}
                        className={`w-full bg-gradient-to-r from-purple-500 to-indigo-600 hover:from-purple-400 hover:to-indigo-500 text-white font-bold py-2 px-4 rounded transition-all transform hover:scale-[1.02] ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {isLoading ? 'Authenticating...' : 'Login'}
                    </button>
                </form>

                <div className="mt-4 text-xs text-purple-300/60 text-center">
                    FiberStack Secure Access • Server Authenticated
                </div>
            </div>
        </div>
    );
}
