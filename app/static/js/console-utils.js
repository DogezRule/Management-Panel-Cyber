/**
 * Console Utilities
 * Shared functionality for noVNC console interface
 */

class ConsoleUtils {
    static getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    static async apiRequest(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            }
        };

        const mergedOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, mergedOptions);
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    static showNotification(message, type = 'info', duration = 3000) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible position-fixed`;
        notification.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            max-width: 350px;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.3s ease;
        `;
        
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(notification);

        // Animate in
        setTimeout(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        }, 10);

        // Auto remove
        setTimeout(() => {
            this.removeNotification(notification);
        }, duration);

        // Manual remove on close button
        notification.querySelector('.btn-close').addEventListener('click', () => {
            this.removeNotification(notification);
        });

        return notification;
    }

    static removeNotification(notification) {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }

    static formatTimestamp(timestamp) {
        return new Date(timestamp).toLocaleString();
    }

    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    static throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    static getWebSocketUrl(vmId) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/vnc-proxy/ws/${vmId}`;
    }

    static handleVMOperation(operation, vmId, onSuccess, onError) {
        return this.apiRequest(`/api/vm/${vmId}/${operation}`, {
            method: 'POST'
        }).then(result => {
            if (result.success) {
                this.showNotification(`VM ${operation} successful`, 'success');
                if (onSuccess) onSuccess(result);
            } else {
                this.showNotification(`Failed to ${operation} VM: ${result.message || 'Unknown error'}`, 'danger');
                if (onError) onError(result);
            }
        }).catch(error => {
            this.showNotification(`Error ${operation} VM: ${error.message}`, 'danger');
            if (onError) onError(error);
        });
    }
}

// Global keyboard shortcuts handler
class KeyboardShortcuts {
    constructor() {
        this.shortcuts = new Map();
        this.init();
    }

    init() {
        document.addEventListener('keydown', (event) => {
            const key = this.getKeyString(event);
            const handler = this.shortcuts.get(key);
            
            if (handler) {
                event.preventDefault();
                handler(event);
            }
        });
    }

    getKeyString(event) {
        const parts = [];
        if (event.ctrlKey) parts.push('ctrl');
        if (event.altKey) parts.push('alt');
        if (event.shiftKey) parts.push('shift');
        if (event.metaKey) parts.push('meta');
        parts.push(event.key.toLowerCase());
        return parts.join('+');
    }

    register(keyString, handler) {
        this.shortcuts.set(keyString.toLowerCase(), handler);
    }

    unregister(keyString) {
        this.shortcuts.delete(keyString.toLowerCase());
    }

    clear() {
        this.shortcuts.clear();
    }
}

// Export for use in console pages
window.ConsoleUtils = ConsoleUtils;
window.KeyboardShortcuts = KeyboardShortcuts;