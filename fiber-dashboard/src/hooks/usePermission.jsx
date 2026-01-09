/**
 * Day 78: Permission Hook
 * 
 * Provides easy access to permission checks in components.
 * Uses AuthContext to check server-provided permissions.
 */
import { useAuth } from '../context/AuthContext';
import { PERMISSIONS } from '../admin/roles';

/**
 * Check if current user has a specific permission.
 * @param {string} permission - Permission to check
 * @returns {boolean}
 */
export function usePermission(permission) {
    const { can } = useAuth();
    return can(permission);
}

/**
 * Check if user can manage nodes (create/update).
 */
export function useCanManageNodes() {
    return usePermission(PERMISSIONS.CREATE_NODE);
}

/**
 * Check if user can delete nodes (ADMIN only).
 */
export function useCanDeleteNodes() {
    return usePermission(PERMISSIONS.DELETE_NODE);
}

/**
 * Check if user can view admin panel.
 */
export function useCanViewAdmin() {
    const canCreate = usePermission(PERMISSIONS.CREATE_NODE);
    const canDelete = usePermission(PERMISSIONS.DELETE_NODE);
    return canCreate || canDelete;
}

/**
 * Check if user can configure cluster (ADMIN only).
 */
export function useCanConfigureCluster() {
    return usePermission(PERMISSIONS.CONFIGURE_CLUSTER);
}

// Re-export permissions for convenience
export { PERMISSIONS };
