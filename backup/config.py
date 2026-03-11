import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///cyberlab.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Proxmox settings
    PROXMOX_HOST = os.getenv('PROXMOX_HOST')
    PROXMOX_USER = os.getenv('PROXMOX_USER')
    PROXMOX_TOKEN_NAME = os.getenv('PROXMOX_TOKEN_NAME')
    PROXMOX_TOKEN_VALUE = os.getenv('PROXMOX_TOKEN_VALUE')
    PROXMOX_PASSWORD = os.getenv('PROXMOX_PASSWORD')
    PROXMOX_SSH_HOST = os.getenv('PROXMOX_SSH_HOST')
    PROXMOX_SSH_USER = os.getenv('PROXMOX_SSH_USER', 'root')
    PROXMOX_SSH_KEY_PATH = os.getenv('PROXMOX_SSH_KEY_PATH')
    
    
    # VM defaults
    DEFAULT_VM_MEMORY = int(os.getenv('DEFAULT_VM_MEMORY', 2048))
    DEFAULT_VM_CORES = int(os.getenv('DEFAULT_VM_CORES', 2))
    DEFAULT_VM_STORAGE = os.getenv('DEFAULT_VM_STORAGE', 'local-lvm')
    
    # Multi-node settings
    MAX_VMS_PER_NODE = int(os.getenv('MAX_VMS_PER_NODE', 12))
    USE_LINKED_CLONES = os.getenv('USE_LINKED_CLONES', 'True') == 'True'
    AUTO_REPLICATE_TEMPLATES = os.getenv('AUTO_REPLICATE_TEMPLATES', 'True') == 'True'
    # Comma-separated list of storage pools for linked clones
    LINKED_CLONE_STORAGES = os.getenv('LINKED_CLONE_STORAGES', 'local-lvm').split(',')
    # Node selection strategy: 'round_robin', 'least_vms', 'random'
    NODE_SELECTION_STRATEGY = os.getenv('NODE_SELECTION_STRATEGY', 'least_vms')
    # Force passing storage to Proxmox clone even for linked clones
    FORCE_STORAGE_FOR_LINKED_CLONES = os.getenv('FORCE_STORAGE_FOR_LINKED_CLONES', 'False') == 'True'
    
    # Security
    WTF_CSRF_ENABLED = True
    # Enforce secure cookies and HTTPS in production via env vars
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True') == 'True'
    SESSION_COOKIE_HTTPONLY = os.getenv('SESSION_COOKIE_HTTPONLY', 'True') == 'True'
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Strict')
    REMEMBER_COOKIE_SECURE = os.getenv('REMEMBER_COOKIE_SECURE', 'True') == 'True'
    REMEMBER_COOKIE_HTTPONLY = os.getenv('REMEMBER_COOKIE_HTTPONLY', 'True') == 'True'
    PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'https')

    # Rate limiting (Flask-Limiter) - increased for testing
    RATELIMIT_DEFAULT = os.getenv('RATELIMIT_DEFAULT', '10000 per day;1000 per hour')
    RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')

    # Content Security Policy for Talisman. Modify as necessary for your app.
    CSP = {
        'default-src': ["'self'"],
        'script-src': ["'self'"],
        'style-src': ["'self'"],
        'img-src': ["'self'", 'data:'],
        'connect-src': ["'self'", 'https:', 'wss:', 'ws:'],  # Allow same-origin + WebSocket + HTTPS for API
    }
    # Whether the app should redirect HTTP to HTTPS. Disable if terminating TLS at a proxy
    SSL_REDIRECT = os.getenv('SSL_REDIRECT', 'True') == 'True'
    # When app is behind a proxy (like nginx) set BEHIND_PROXY=True
    BEHIND_PROXY = os.getenv('BEHIND_PROXY', 'True') == 'True'
    # Login lockout policy
    LOGIN_MAX_ATTEMPTS = int(os.getenv('LOGIN_MAX_ATTEMPTS', 5))
    LOGIN_LOCK_MINUTES = int(os.getenv('LOGIN_LOCK_MINUTES', 15))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # Reduce info leak on errors
    PROPAGATE_EXCEPTIONS = False
