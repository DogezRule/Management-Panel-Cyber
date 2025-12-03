# CyberLab Admin Panel

A production-ready administrative panel for managing Proxmox VE virtual machines in cybersecurity lab environments.

## Features

- **VM Management**: Create, start, stop, delete VMs with template-based deployment
- **Multi-Node Support**: Automatic VM distribution across Proxmox cluster nodes
- **Role-Based Access**: Admin, Teacher, and Student user roles with appropriate permissions
- **Real-Time Monitoring**: WebSocket-powered live VM status updates
- **VNC Console**: Integrated web-based console access
- **Security**: SSL/TLS encryption, rate limiting, CSRF protection
- **RESTful API**: Full API access for external integrations

## Production Deployment

### Prerequisites
- Proxmox VE cluster (6.0+)
- Ubuntu/Debian server
- Domain name pointing to server IP

### Quick Deploy

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd cyberlab-admin
   ```

2. **Run deployment:**
   ```bash
   ./deploy.sh
   ```

3. **Configure Proxmox credentials in `.env`:**
   ```bash
   PROXMOX_HOST=https://your-proxmox-ip:8006
   PROXMOX_USER=root@pam
   PROXMOX_TOKEN_NAME=your-token-name
   PROXMOX_TOKEN_VALUE=your-token-value
   ```

4. **Access application:**
   - URL: `https://Cybersecurity.local`
   - Default admin: Set up on first access

### Manual Setup

If automatic deployment fails:

```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize database
python -c "from app import create_app; app = create_app(); app.app_context().push(); from app.extensions import db; db.create_all()"

# Setup systemd service
sudo cp deploy/gunicorn.service /etc/systemd/system/cyberlab-admin.service
sudo systemctl daemon-reload
sudo systemctl enable --now cyberlab-admin

# Setup Caddy reverse proxy
sudo cp deploy/caddy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

## Configuration

### Environment Variables (.env)
```bash
# Production settings
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///cyberlab.db
DOMAIN=Cybersecurity.local:443

# Proxmox connection
PROXMOX_HOST=https://proxmox-server:8006
PROXMOX_USER=root@pam
PROXMOX_TOKEN_NAME=admin-panel
PROXMOX_TOKEN_VALUE=your-api-token

# VM settings
MAX_VMS_PER_NODE=12
USE_LINKED_CLONES=True
NODE_SELECTION_STRATEGY=least_vms

# Security
SSL_REDIRECT=True
BEHIND_PROXY=True
LOGIN_MAX_ATTEMPTS=5
```

### Proxmox API Setup

1. **Create API token in Proxmox:**
   ```bash
   # In Proxmox shell:
   pveum user token add root@pam admin-panel --privsep=0
   ```

2. **Update `.env` with token details**

## System Management

### Service Control
```bash
# Check status
sudo systemctl status cyberlab-admin caddy

# Restart services
sudo systemctl restart cyberlab-admin caddy

# View logs
sudo journalctl -u cyberlab-admin -f
sudo journalctl -u caddy -f
```

### Database Operations
```bash
cd /home/admin/Admin-Panel/cyberlab-admin
source .venv/bin/activate

# Backup database
cp instance/cyberlab.db instance/cyberlab.db.backup

# Reset database (WARNING: Deletes all data)
rm instance/cyberlab.db
python -c "from app import create_app; app = create_app(); app.app_context().push(); from app.extensions import db; db.create_all()"
```

## API Usage

### Authentication
All API calls require authentication via session cookies.

### Key Endpoints
```bash
# List VMs
GET /api/vms

# VM control
POST /api/vms/{vmid}/start
POST /api/vms/{vmid}/stop
POST /api/vms/{vmid}/restart

# VM creation from template
POST /api/templates/{template_id}/clone
```

## Troubleshooting

### Common Issues

**Cannot access https://Cybersecurity.local:**
- Verify `/etc/hosts` contains: `<server-ip> Cybersecurity.local`
- Check Caddy service: `sudo systemctl status caddy`

**Proxmox connection failed:**
- Verify Proxmox credentials in `.env`
- Test API access: `curl -k https://proxmox-ip:8006/api2/json/version`

**Service won't start:**
- Check logs: `sudo journalctl -u cyberlab-admin`
- Verify file permissions: `sudo chown -R admin:caddy /home/admin/Admin-Panel`

### System Requirements
- **RAM**: 2GB minimum, 4GB recommended
- **Disk**: 10GB minimum for application and database
- **Network**: Reliable connection to Proxmox cluster

## File Structure

### Root Directory
```
cyberlab-admin/
├── .env                    # Environment variables (Proxmox credentials, security settings)
├── .gitignore             # Git ignore patterns for security and cache files
├── config.py              # Flask configuration classes (Development/Production)
├── deploy.sh              # Production deployment automation script
├── gunicorn.conf.py       # Gunicorn WSGI server configuration
├── README.md              # This documentation file
├── requirements.txt       # Python package dependencies
├── run.py                 # Development server entry point
├── wsgi.py               # Production WSGI application entry point
├── .venv/                # Python virtual environment (isolated dependencies)
├── app/                  # Main Flask application package
├── deploy/               # Production deployment configurations
├── instance/             # Runtime data and application state
└── migrations/           # Database schema migration files
```

### Core Application (`app/`)
```
app/
├── __init__.py           # Flask app factory, extensions setup, blueprint registration
├── extensions.py         # Flask extension instances (SQLAlchemy, Login, Security)
├── models.py            # Database models (User, Classroom, Student, VM, Template, Node)
├── security.py          # Authentication utilities, password hashing, encryption
├── blueprints/          # Modular Flask blueprints for different app sections
├── services/            # Business logic and external service integrations
├── static/             # Static web assets (CSS, JavaScript, images, fonts)
└── templates/          # Jinja2 HTML templates for web pages
```

#### Application Blueprints (`app/blueprints/`)
```
blueprints/
├── admin/              # Administrator dashboard and system management
│   ├── __init__.py     # Blueprint registration and configuration
│   ├── forms.py        # WTForms for admin operations (create nodes, templates)
│   ├── routes.py       # Admin view functions and API endpoints
│   └── templates/admin/
│       ├── create_node.html         # Add new Proxmox nodes to cluster
│       ├── create_teacher.html      # Teacher account creation form
│       ├── create_template.html     # VM template configuration form
│       ├── dashboard.html           # Main admin dashboard with system overview
│       ├── edit_node.html          # Modify existing node configurations
│       ├── logs.html               # System audit logs and security events
│       ├── multi_node_settings.html # Cluster-wide configuration settings
│       └── nodes.html              # Proxmox node status and management
│
├── api/               # RESTful API endpoints for external integrations
│   ├── __init__.py    # API blueprint setup and error handlers
│   └── routes.py      # JSON API routes (VM control, status, user management)
│
├── auth/              # Authentication and session management
│   ├── __init__.py    # Auth blueprint configuration
│   ├── forms.py       # Login forms with CSRF protection
│   ├── routes.py      # Login/logout handlers, session management
│   └── templates/auth/
│       ├── login.html          # Unified login page with role selection
│       ├── student_login.html  # Student-specific login interface
│       └── teacher_login.html  # Teacher-specific login interface
│
├── student/           # Student dashboard and VM access
│   ├── __init__.py    # Student blueprint setup
│   ├── routes.py      # Student view functions and VM console access
│   └── templates/student/
│       ├── console.html    # Embedded noVNC console interface
│       └── dashboard.html  # Student VM list and status display
│
├── teacher/           # Teacher classroom management interface
│   ├── __init__.py    # Teacher blueprint configuration
│   ├── forms.py       # Classroom and student management forms
│   ├── routes.py      # Teacher dashboard, class management, VM operations
│   └── templates/teacher/
│       ├── class_detail.html   # Individual classroom management page
│       ├── console.html        # Teacher VM console access
│       ├── dashboard.html      # Teacher overview of all classes
│       └── import_class.html   # Bulk student import from CSV/Excel
│
└── vnc_proxy/         # WebSocket proxy for VNC connections
    ├── __init__.py    # VNC proxy blueprint setup
    └── routes.py      # WebSocket handlers for secure VM console tunneling
```

#### Business Logic Services (`app/services/`)
```
services/
├── proxmox_client.py     # Proxmox VE API client wrapper and connection management
└── vm_orchestrator.py    # High-level VM lifecycle management and cluster operations
```

#### Static Web Assets (`app/static/`)
```
static/
├── css/
│   └── main.css              # Custom application styles and dark theme
├── js/
│   └── main.js              # Client-side JavaScript for dynamic UI elements
└── vendor/                   # Third-party libraries and frameworks
    ├── bootstrap/           # Bootstrap CSS framework and components
    │   ├── bootstrap.bundle.min.js  # Bootstrap JavaScript with Popper.js
    │   └── bootstrap.min.css        # Bootstrap CSS framework
    ├── bootstrap-icons/     # Bootstrap icon font and graphics
    │   ├── bootstrap-icons.min.css  # Icon CSS definitions
    │   └── fonts/               # Web font files (WOFF/WOFF2)
    └── novnc/              # noVNC HTML5 VNC client (production files only)
        ├── app/            # noVNC UI components, styles, and localization
        ├── core/           # VNC protocol implementation and decoders
        ├── vendor/pako/    # Compression library for VNC data streams
        ├── AUTHORS         # noVNC contributors and licensing info
        ├── LICENSE.txt     # noVNC license (MPL 2.0)
        └── README.md       # noVNC documentation
```

#### HTML Templates (`app/templates/`)
```
templates/
├── base.html              # Master template with navigation and common elements
├── _navbar.html          # Navigation bar component with role-based menus
├── _flash_messages.html  # Alert/notification message display component
├── 403.html             # Access forbidden error page
├── 404.html             # Page not found error page
└── 500.html             # Internal server error page
```

### Production Deployment (`deploy/`)
```
deploy/
├── caddy/                    # Caddy web server configuration
│   └── Caddyfile            # Caddy reverse proxy and TLS configuration
├── certs/                   # SSL/TLS certificates and CA files
│   └── Caddy_Local_Authority_Root.crt  # Caddy's internal CA root certificate
├── gunicorn.service         # systemd service unit for production deployment
└── install.sh              # One-command production installation script
```

### Runtime Data (`instance/`)
```
instance/
├── cyberlab.db           # SQLite database file (user accounts, VMs, logs)
└── logs/                # Application log files
    └── auth.log         # Authentication events and security audit trail
```

### Database Migrations (`migrations/`)
```
migrations/
├── alembic.ini          # Alembic migration tool configuration
├── env.py               # Migration environment setup and database connection
├── README               # Migration usage instructions
├── script.py.mako      # Template for generating new migration files
└── versions/           # Individual database migration scripts
    ├── f164ccb09fe7_initial_schema.py                    # Initial database tables
    ├── c49eca35176b_add_multi_node_support_with_node_.py # Multi-node cluster support
    ├── 7ab9b15165d5_add_nodestorageconfig_and_vm_storage.py # Storage configuration
    ├── 818b25c84d91_add_console_url_to_virtualmachine.py # VNC console URLs
    ├── 719badf3f07c_add_initial_password_to_student.py   # Student password management
    ├── 0f3a1c2b5d6e_harden_auth_and_encrypt_initial_passwords.py # Security hardening
    └── [additional migration files...]                   # Progressive schema updates
```

### Key Configuration Files

| File | Purpose | Critical Settings |
|------|---------|-------------------|
| `.env` | Environment configuration | Proxmox credentials, security keys, SSL settings |
| `config.py` | Flask application settings | Database URLs, security policies, feature flags |
| `gunicorn.conf.py` | WSGI server configuration | Worker processes, socket binding, performance tuning |
| `requirements.txt` | Python dependencies | Flask, SQLAlchemy, Proxmox client, security libraries |
| `deploy/gunicorn.service` | systemd service definition | Service lifecycle, user permissions, restart policies |
| `deploy/caddy/Caddyfile` | Reverse proxy configuration | HTTPS termination, WebSocket proxying, security headers |

### Data Flow Architecture
```
Client Browser → Caddy (HTTPS/WSS) → Gunicorn (HTTP) → Flask App → SQLite/Proxmox API
      ↓              ↓                    ↓              ↓              ↓
  Static Assets   TLS Termination    WSGI Processing   Business Logic  Data Storage
  noVNC Client    Load Balancing     Session Management VM Operations  User Accounts
  Bootstrap UI    Security Headers   Authentication    API Calls      Configuration
```

## License

MIT License - see LICENSE file for details.