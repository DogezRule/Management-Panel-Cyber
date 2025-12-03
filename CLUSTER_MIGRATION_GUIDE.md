# Proxmox Cluster Migration Guide

## Current Status ✅
- **Removed**: Old `cyberrack` node configuration
- **Removed**: 1 VM template associated with old cluster  
- **Backup**: Created at `instance/cyberlab_backup_20251119_182607.db`
- **Ready**: System is now clean and ready for new cluster

## Next Steps for New Cluster

### 1. Update Proxmox Connection Settings
Edit the `.env` file in the cyberlab-admin directory:

```bash
# Proxmox connection settings
PROXMOX_HOST=https://your-new-proxmox-cluster:8006
PROXMOX_USER=root@pam
PROXMOX_TOKEN_NAME=admin-panel
PROXMOX_TOKEN_VALUE=your-new-api-token

# Optional: SSH connection (for better performance)
PROXMOX_SSH_HOST=your-new-proxmox-ssh-ip
PROXMOX_SSH_USER=root
PROXMOX_SSH_KEY_PATH=/path/to/ssh/key
```

### 2. Create API Token in New Proxmox Cluster
In your new Proxmox cluster shell:
```bash
pveum user token add root@pam admin-panel --privsep=0
```

### 3. Add New Nodes
Once connected to new cluster:
1. Go to: `https://Cybersecurity.local/admin/nodes`
2. Click "Add First Node" 
3. Enter node details from your new cluster

### 4. Configure VM Templates
1. Go to: `https://Cybersecurity.local/admin/templates`
2. Add templates from your new cluster
3. Configure auto-replication if using multiple nodes

### 5. Test Deployment
1. Create a test classroom
2. Deploy a VM to verify everything works
3. Test console connectivity

## Restore Previous Setup (If Needed)
If you need to restore the old configuration:
```bash
cd /home/admin/Admin-Panel/cyberlab-admin
cp instance/cyberlab_backup_20251119_182607.db instance/cyberlab.db
```

## Key Configuration Files
- **Main config**: `.env` (Proxmox connection details)
- **Database**: `instance/cyberlab.db` (application data)
- **Logs**: `instance/logs/` (troubleshooting)

## Verification Commands
After setting up new cluster, verify with:
```bash
# Check node configurations
sqlite3 instance/cyberlab.db "SELECT * FROM node_configurations;"

# Check templates  
sqlite3 instance/cyberlab.db "SELECT name, proxmox_node, proxmox_template_id FROM vm_templates;"

# Test Proxmox connection
curl -k "$PROXMOX_HOST/api2/json/version" -H "Authorization: PVEAPIToken=$PROXMOX_USER!$PROXMOX_TOKEN_NAME=$PROXMOX_TOKEN_VALUE"
```

---
**Note**: The system is now completely clean and ready for your new Proxmox cluster. All old node references have been removed.