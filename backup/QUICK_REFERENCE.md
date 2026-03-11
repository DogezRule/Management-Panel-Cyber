# Quick Reference Card

## What Changed (TL;DR)

**Old Way:** Templates replicated across nodes with async status tracking
**New Way:** Admin specifies exact VMID for each template on each node

---

## Key Files Modified

```
app/
  models.py                    ← Updated VMTemplate, added TemplateNodeMapping
  blueprints/admin/
    forms.py                   ← Simplified CreateVMTemplateForm
    routes.py                  ← Refactored create_template(), removed replicate_template()
    templates/admin/
      create_template.html     ← Complete UI redesign
      dashboard.html           ← Updated template table display
      multi_node_settings.html ← Removed replication section

services/
  vm_orchestrator.py          ← Simplified ensure_template_on_node()

migrations/versions/
  d1f2g3h4i5j6_...py         ← New migration (schema change)
```

---

## How to Create a Template Now

### 3-Step Process
1. **Prepare:** Ensure template exists on Proxmox nodes with known VMIDs
2. **Create:** Go to Admin → Create Template
3. **Configure:** Specify VMID for each node

### Example
```
Template Name: ubuntu-20.04
Memory: 2048 MB
Cores: 2
Active: ✓

Node VMIDs:
  pve-1: 100
  pve-2: 100
  pve-3: 100

[Create Template]
```

---

## Data Structure

### Old Way
```
vm_templates:
  - id=1, name=ubuntu, proxmox_template_id=100, proxmox_node=pve-1, replicate_to_all_nodes=true

vm_template_replicas:
  - id=1, template_id=1, target_node=pve-2, proxmox_template_id=100, is_ready=true
  - id=2, template_id=1, target_node=pve-3, proxmox_template_id=100, is_ready=false
```

### New Way
```
vm_templates:
  - id=1, name=ubuntu, memory=2048, cores=2, is_active=true

template_node_mappings:
  - id=1, template_id=1, proxmox_node=pve-1, proxmox_template_id=100
  - id=2, template_id=1, proxmox_node=pve-2, proxmox_template_id=100
  - id=3, template_id=1, proxmox_node=pve-3, proxmox_template_id=100
```

---

## Deployment Steps

### Pre-Deployment
```bash
# Backup database
cp instance/cyberlab.db instance/cyberlab.db.backup

# Document current templates
sqlite3 instance/cyberlab.db "SELECT id, name, proxmox_template_id, proxmox_node FROM vm_templates;"
```

### Deployment
```bash
# Pull changes
git pull

# Run migration
flask db upgrade

# Verify migration
flask shell
>>> from app.models import VMTemplate
>>> for t in VMTemplate.query.all(): print(f"{t.name}: {t.get_available_nodes()}")

# Restart
sudo systemctl restart cyberlab-admin
```

### Post-Deployment
- ✅ Check dashboard templates display correctly
- ✅ Create test template with multiple nodes
- ✅ Deploy test VM

---

## What Admin Sees (Dashboard)

### Before
```
Name    | Template ID | Primary Node | Memory | Cores | Multi-Node    | Actions
ubuntu  | 100         | pve-1        | 2048MB | 2     | Auto-replicated| [↻][✕]
```

### After
```
Name    | Available Nodes      | Memory | Cores | Status | Actions
ubuntu  | pve-1 pve-2 pve-3   | 2048MB | 2     | Active | [✕]
```

---

## Removed Features

- ❌ Replication button
- ❌ Replication status badge
- ❌ Auto-replicate checkbox
- ❌ Template async replication background job

---

## New Capabilities

- ✅ Explicit per-node VMID specification
- ✅ Support for different VMIDs on different nodes
- ✅ Clear visibility of template availability
- ✅ Immediate error messages with solutions

---

## Troubleshooting

### "Template not found on node"
```
Error: Template 'ubuntu-20.04' is NOT registered on node 'pve-4'.
Available nodes: pve-1, pve-2, pve-3
```
**Solution:** Create template and specify VMID for pve-4, or deploy to available node

### Migration failed
```bash
# Rollback
flask db downgrade
# Then fix issue and try again
flask db upgrade
```

### Template not showing in dashboard
```python
# Check if created properly
flask shell
>>> from app.models import VMTemplate
>>> t = VMTemplate.query.filter_by(name='ubuntu').first()
>>> t.get_available_nodes()  # Should show list of nodes
```

---

## Config Changes

### Can Remove from .env
```bash
AUTO_REPLICATE_TEMPLATES=True  # ← No longer used
```

### Still Used
```bash
USE_LINKED_CLONES=True
NODE_SELECTION_STRATEGY=least_vms
MAX_VMS_PER_NODE=12
```

---

## API Usage (For Developers)

### Get Template VMID for Node
```python
from app.models import VMTemplate

template = VMTemplate.query.get(1)

# Get VMID for specific node
vmid = template.get_template_id_for_node('pve-1')
# Returns: 100
# OR raises RuntimeError if not configured

# Get all available nodes
nodes = template.get_available_nodes()
# Returns: ['pve-1', 'pve-2', 'pve-3']
```

### Create Template with Mappings
```python
from app.models import VMTemplate, TemplateNodeMapping

template = VMTemplate(
    name='ubuntu-20.04',
    memory=2048,
    cores=2,
    is_active=True
)
db.session.add(template)
db.session.flush()

# Add node mappings
for node_name, vmid in {'pve-1': 100, 'pve-2': 100, 'pve-3': 100}.items():
    mapping = TemplateNodeMapping(
        template_id=template.id,
        proxmox_node=node_name,
        proxmox_template_id=vmid
    )
    db.session.add(mapping)

db.session.commit()
```

---

## Next Actions

1. Read: `REFACTOR_SUMMARY.md` (high-level overview)
2. Read: `TEMPLATE_ARCHITECTURE_REFACTOR.md` (technical details)
3. Read: `UI_CHANGES_GUIDE.md` (visual examples)
4. Follow: `DEPLOYMENT_CHECKLIST.md` (step-by-step)
5. Test: In staging first
6. Deploy: Follow checklist in production
7. Train: Team on new workflow

---

## Support

- 📖 **Technical Details:** TEMPLATE_ARCHITECTURE_REFACTOR.md
- 🎨 **Visual Guide:** UI_CHANGES_GUIDE.md & BEFORE_AFTER_COMPARISON.md
- ✅ **Deployment:** DEPLOYMENT_CHECKLIST.md
- 📋 **Summary:** REFACTOR_SUMMARY.md (this file)

---

## Timeline

**Old Approach (When Replicating):**
- Create template: 1 minute
- Replicate to nodes: 5-15 minutes (async)
- Monitor status: Ongoing
- Deploy VMs: Start deploying
- Potential issues: Silent failures during replication

**New Approach:**
- Create template: 1 minute
- Specify node VMIDs: 1 minute
- Deploy VMs: Immediately (or clear error)
- Total time: Same or faster
- **Key difference:** Reliable, no async failures
