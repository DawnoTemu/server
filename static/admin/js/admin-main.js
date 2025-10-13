/**
 * DawnoTemu Admin Panel - Global JavaScript
 * Common functionality for all admin pages
 */

(function() {
    'use strict';

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        initFeatherIcons();
        initTooltips();
        initConfirmDialogs();
        initAutoRefresh();
        initSearchShortcut();
        initDarkMode();
    });

    /**
     * Initialize Feather Icons
     */
    function initFeatherIcons() {
        if (typeof feather !== 'undefined') {
            feather.replace();

            // Re-initialize icons after dynamic content loads
            const observer = new MutationObserver(function(mutations) {
                feather.replace();
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    }

    /**
     * Initialize Tooltips
     */
    function initTooltips() {
        const tooltips = document.querySelectorAll('[data-tooltip]');

        tooltips.forEach(element => {
            element.addEventListener('mouseenter', function() {
                showTooltip(this);
            });

            element.addEventListener('mouseleave', function() {
                hideTooltip();
            });
        });
    }

    function showTooltip(element) {
        const text = element.getAttribute('data-tooltip');
        const tooltip = document.createElement('div');
        tooltip.className = 'tooltip';
        tooltip.textContent = text;
        tooltip.id = 'active-tooltip';

        document.body.appendChild(tooltip);

        const rect = element.getBoundingClientRect();
        tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';
        tooltip.style.left = (rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2)) + 'px';
    }

    function hideTooltip() {
        const tooltip = document.getElementById('active-tooltip');
        if (tooltip) {
            tooltip.remove();
        }
    }

    /**
     * Initialize Confirm Dialogs
     */
    function initConfirmDialogs() {
        document.addEventListener('click', function(e) {
            const button = e.target.closest('[data-confirm]');
            if (button) {
                const message = button.getAttribute('data-confirm');
                if (!confirm(message)) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            }
        });
    }

    /**
     * Auto-refresh functionality for dashboards
     */
    function initAutoRefresh() {
        const refreshButtons = document.querySelectorAll('[data-auto-refresh]');

        refreshButtons.forEach(button => {
            const interval = parseInt(button.getAttribute('data-auto-refresh')) * 1000;

            if (interval > 0) {
                setInterval(() => {
                    location.reload();
                }, interval);

                // Add countdown indicator
                updateCountdown(button, interval);
            }
        });
    }

    function updateCountdown(button, interval) {
        let remaining = interval / 1000;
        const countdownEl = document.createElement('span');
        countdownEl.className = 'text-xs text-gray-500 ml-2';
        button.appendChild(countdownEl);

        const timer = setInterval(() => {
            remaining--;
            countdownEl.textContent = `(${remaining}s)`;

            if (remaining <= 0) {
                clearInterval(timer);
            }
        }, 1000);
    }

    /**
     * Search shortcut (Cmd/Ctrl + K)
     */
    function initSearchShortcut() {
        document.addEventListener('keydown', function(e) {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('input[type="search"]');
                if (searchInput) {
                    searchInput.focus();
                    searchInput.select();
                }
            }
        });
    }

    /**
     * Dark Mode Toggle
     */
    function initDarkMode() {
        const darkModeKey = 'dawnotemu_admin_dark_mode';
        const savedMode = localStorage.getItem(darkModeKey);

        if (savedMode === 'true') {
            document.body.classList.add('dark');
        }

        // Listen for dark mode toggle events
        document.addEventListener('click', function(e) {
            if (e.target.closest('[data-toggle-dark-mode]')) {
                const isDark = document.body.classList.toggle('dark');
                localStorage.setItem(darkModeKey, isDark);
            }
        });
    }

    /**
     * Toast Notifications
     */
    window.showToast = function(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const iconMap = {
            success: 'check-circle',
            error: 'alert-circle',
            warning: 'alert-triangle',
            info: 'info'
        };

        toast.innerHTML = `
            <div class="flex items-center gap-3">
                <i data-feather="${iconMap[type]}" class="w-5 h-5"></i>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-auto">
                    <i data-feather="x" class="w-4 h-4"></i>
                </button>
            </div>
        `;

        // Add to page
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'fixed top-4 right-4 z-50 space-y-3';
            document.body.appendChild(toastContainer);
        }

        toastContainer.appendChild(toast);
        feather.replace();

        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    };

    /**
     * Loading Spinner
     */
    window.showLoading = function(text = 'Loading...') {
        const overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        overlay.innerHTML = `
            <div class="bg-white rounded-lg p-6 flex flex-col items-center gap-4">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
                <p class="text-gray-700 font-medium">${text}</p>
            </div>
        `;
        document.body.appendChild(overlay);
    };

    window.hideLoading = function() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    };

    /**
     * Copy to Clipboard
     */
    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard!', 'success');
        }).catch(err => {
            showToast('Failed to copy', 'error');
        });
    };

    /**
     * Format Numbers
     */
    window.formatNumber = function(num) {
        return new Intl.NumberFormat('pl-PL').format(num);
    };

    /**
     * Format Date
     */
    window.formatDate = function(date, includeTime = true) {
        const options = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        };

        if (includeTime) {
            options.hour = '2-digit';
            options.minute = '2-digit';
        }

        return new Intl.DateTimeFormat('pl-PL', options).format(new Date(date));
    };

    /**
     * Debounce Function
     */
    window.debounce = function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    /**
     * Export Table to CSV
     */
    window.exportTableToCSV = function(tableId, filename = 'export.csv') {
        const table = document.getElementById(tableId);
        if (!table) return;

        let csv = [];
        const rows = table.querySelectorAll('tr');

        rows.forEach(row => {
            const cols = row.querySelectorAll('td, th');
            const csvRow = [];
            cols.forEach(col => {
                csvRow.push('"' + col.textContent.trim().replace(/"/g, '""') + '"');
            });
            csv.push(csvRow.join(','));
        });

        const csvContent = csv.join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        window.URL.revokeObjectURL(url);

        showToast('Table exported successfully!', 'success');
    };

})();
