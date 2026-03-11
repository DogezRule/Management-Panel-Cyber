// CyberLab Admin Panel - Main JavaScript

// Theme toggle functionality
(function() {
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    const htmlElement = document.documentElement;
    
    // Load saved theme (theme attribute already set by inline script)
    const savedTheme = localStorage.getItem('theme') || 'dark';
    updateThemeIcon(savedTheme);
    
    // Navbar classes should already be set by inline script, but ensure they're correct
    const navbar = document.getElementById('mainNavbar');
    if (navbar) {
        if (savedTheme === 'dark') {
            navbar.classList.add('navbar-dark');
            navbar.classList.remove('navbar-light');
        } else {
            navbar.classList.add('navbar-light');
            navbar.classList.remove('navbar-dark');
        }
    }
    
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const currentTheme = htmlElement.getAttribute('data-bs-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            htmlElement.setAttribute('data-bs-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }
    
    function updateThemeIcon(theme) {
        if (themeIcon) {
            if (theme === 'dark') {
                themeIcon.className = 'bi bi-sun-fill';
            } else {
                themeIcon.className = 'bi bi-moon-stars';
            }
        }
        
        // Update navbar classes for proper Bootstrap theming
        const navbar = document.getElementById('mainNavbar');
        if (navbar) {
            if (theme === 'dark') {
                navbar.classList.add('navbar-dark');
                navbar.classList.remove('navbar-light');
            } else {
                navbar.classList.add('navbar-light');
                navbar.classList.remove('navbar-dark');
            }
        }
    }
})();

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

// Confirmation for delete actions
document.addEventListener('DOMContentLoaded', function() {
    const deleteForms = document.querySelectorAll('form[action*="delete"]');
    deleteForms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!form.hasAttribute('data-no-confirm')) {
                const confirmed = confirm('Are you sure you want to delete this? This action cannot be undone.');
                if (!confirmed) {
                    e.preventDefault();
                }
            }
        });
    });
});

// VM Status polling helper (can be called from individual pages)
function pollVMStatus(vmId, badgeElement, interval = 10000) {
    const updateStatus = () => {
        fetch(`/api/vm/${vmId}/status`)
            .then(response => response.json())
            .then(data => {
                if (badgeElement) {
                    badgeElement.textContent = data.status;
                    
                    // Update badge color based on status
                    badgeElement.className = 'badge';
                    if (data.status === 'running') {
                        badgeElement.classList.add('bg-success');
                    } else if (data.status === 'stopped') {
                        badgeElement.classList.add('bg-warning');
                    } else if (data.status === 'error') {
                        badgeElement.classList.add('bg-danger');
                    } else {
                        badgeElement.classList.add('bg-info');
                    }
                }
            })
            .catch(error => {
                console.error('Failed to fetch VM status:', error);
            });
    };
    
    // Initial update
    updateStatus();
    
    // Set up interval
    return setInterval(updateStatus, interval);
}

// Export for use in other scripts
window.cyberlabAdmin = {
    pollVMStatus: pollVMStatus
};
