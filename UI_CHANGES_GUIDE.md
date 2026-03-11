# UI Changes - Quick Reference

## Template Management UI Updates

### Admin Dashboard - Templates Section
**What Changed:**
- Removed "Template ID" column (was showing proxmox_template_id)
- Removed "Primary Node" column (was showing proxmox_node)
- Replaced "Multi-Node" column (Auto-replicated/Single node badges) with "Available Nodes" column
- Removed "Replicate" button (the circular arrow icon)

**Current Display:**
```
Name | Available Nodes | Memory | Cores | Status | Actions
ubuntu-20 | pve-1 | 2048 MB | 2 | Active | [Delete]
centos-7  | pve-1  pve-2  pve-3 | 4096 MB | 4 | Active | [Delete]
```

### Create Template Form
**New Layout (Bootstrap Cards):**

```
┌─────────────────────────────────────┐
│ Template Information                │
├─────────────────────────────────────┤
│ • Template Name (text)              │
│ • Memory (int)                      │
│ • CPU Cores (int)                   │
│ • Active (checkbox)                 │
│ • Description (textarea)            │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Node-Specific Template VMIDs        │
├─────────────────────────────────────┤
│ ┌───────────────────────────────┐   │
│ │ pve-1                         │   │
│ │ Template VMID: [___________]  │   │
│ │ (Leave blank to exclude)      │   │
│ └───────────────────────────────┘   │
│                                     │
│ ┌───────────────────────────────┐   │
│ │ pve-2                         │   │
│ │ Template VMID: [___________]  │   │
│ │ (Leave blank to exclude)      │   │
│ └───────────────────────────────┘   │
│                                     │
│ ℹ️ Templates are now stored per-    │
│    node. Specify VMID for each      │
│    node where template exists.      │
└─────────────────────────────────────┘

[Create Template] [Cancel]
```

### Multi-Node Settings Page
**Changes:**
- Removed "Template Management" section
- Removed "Auto-replicate Templates" checkbox
- Updated info message to explain new per-node template approach

**Current Sections:**
1. VM Deployment Settings
   - Max VMs per Node
2. Performance & Clone Settings
   - Use Linked Clones checkbox
3. Node Selection Strategy
   - Dropdown: Least VMs, Round Robin, Priority, Random
4. Info alert about per-node template configuration

## How to Create a Template with Multi-Node Support

### Example: Ubuntu 20.04 on 3 nodes

1. Go to Admin Panel → Create Template
2. Fill in basic info:
   - Template Name: `ubuntu-20.04`
   - Memory: `2048` MB
   - Cores: `2`
   - Active: ✓ (checked)
   - Description: `Ubuntu 20.04 LTS baseline`

3. Node-Specific VMIDs:
   - pve-1: `105`
   - pve-2: `105`
   - pve-3: `105`
   - (Leave other nodes blank)

4. Click "Create Template"

Result:
- Template created with 3 node mappings
- When deploying to any of these nodes, VMID 105 will be used
- If trying to deploy to pve-4, will get error: "Template not registered on node 'pve-4'"

### Example: Ubuntu 20.04 on Primary Node Only

1. Create template same as above
2. Node-Specific VMIDs:
   - pve-1: `105`
   - pve-2: (blank)
   - pve-3: (blank)

Result:
- Template only available on pve-1
- Deployments will only use pve-1 for this template
- Best practice: Set to single node if no replicas exist

## Deployment Behavior

When deploying a VM for a student:
1. System selects best node (based on NODE_SELECTION_STRATEGY)
2. Checks if template has a mapping for that node
3. If yes: Uses the configured VMID to clone
4. If no: Shows error message with available nodes

Example error if template not on selected node:
```
Template 'ubuntu-20.04' is NOT registered on node 'pve-4'.
Available nodes: pve-1, pve-2, pve-3
➡ You must specify the template VMID for this node when creating the template.
```

## Admin Workflow Changes

### Old Workflow
1. Create template on primary node
2. Click "Replicate" button
3. Wait for async replication
4. Check replication status badge
5. Deploy VMs (system finds copies)

### New Workflow
1. Ensure template exists on desired Proxmox nodes (manual)
2. Go to Create Template form
3. Specify VMID for each node
4. Create template
5. Deploy VMs (system uses exact mappings)

**Result:** Faster, more predictable, no async failures
