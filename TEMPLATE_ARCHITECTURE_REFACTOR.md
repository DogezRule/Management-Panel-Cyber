# VM Template Architecture Refactoring - Implementation Summary

## Overview
Replaced the template replication system with a per-node VMID mapping approach. Templates are no longer replicated across nodes; instead, you specify exactly which VMID corresponds to each template on each specific Proxmox node during template creation.

## Key Changes

### 1. Database Models (`app/models.py`)

#### Removed
- `VMTemplate.proxmox_template_id` - Primary template VMID
- `VMTemplate.proxmox_node` - Primary node reference
- `VMTemplate.replicate_to_all_nodes` - Replication flag

#### Added
- **New Model: `TemplateNodeMapping`** - Maps each template to its VMID on each node
  - `template_id` - Foreign key to VMTemplate
  - `proxmox_node` - Node name
  - `proxmox_template_id` - Template VMID on that specific node
  - Unique constraint: one mapping per template per node

#### Updated VMTemplate Model
- New relationship: `node_vmids` -> TemplateNodeMapping
- New methods:
  - `get_template_id_for_node(node_name)` - Returns VMID for a node, raises RuntimeError if not configured
  - `get_available_nodes()` - Returns list of nodes where template is configured

#### Preserved
- `VMTemplateReplica` - Marked as DEPRECATED, kept for backward compatibility during migration

### 2. Database Migration (`migrations/versions/d1f2g3h4i5j6_...`)

- Creates new `template_node_mappings` table
- Migrates existing data from old structure (primary node + replicas) to new per-node mappings
- Removes old columns from `vm_templates` table
- Supports rollback to restore old schema

### 3. Forms (`app/blueprints/admin/forms.py`)

#### CreateVMTemplateForm - Updated
- Removed: `proxmox_template_id`, `proxmox_node`, `replicate_to_all_nodes` fields
- Kept: `name`, `description`, `memory`, `cores`, `is_active`
- Node/VMID inputs are now handled dynamically in the route and template

#### MultiNodeSettingsForm - Updated
- Removed: `auto_replicate_templates` checkbox
- This setting is no longer needed since replication is manual and per-template

### 4. Routes (`app/blueprints/admin/routes.py`)

#### create_template() Route - Refactored
- Now retrieves active nodes and displays them in the template
- Processes form submission to collect node-VMID pairs
- Creates `TemplateNodeMapping` entries for each node/VMID combination
- Validates that at least one node mapping is provided
- Flash message shows number of configured mappings

#### Removed Routes
- `replicate_template()` - Manual replication button/route no longer exists
- No more "replicate to all nodes" functionality

#### multi_node_settings() Route - Updated
- Removed: Loading/processing of `auto_replicate_templates` setting
- Kept: Max VMs, linked clones, node selection strategy

### 5. Templates

#### create_template.html - Complete Redesign
- Bootstrap card layout for better organization
- Section 1: Template Information (name, memory, cores, description, active status)
- Section 2: Node-Specific VMID Mappings
  - One input field per active node
  - Fields are optional - only configured nodes are created in the mapping
  - Clear labeling and helpful text
- Informational alert explaining the new per-node approach

#### dashboard.html - Updated Template Display
- Removed: Primary Node column, Template ID column, Multi-Node badge
- Added: Available Nodes column (shows all nodes where template exists)
- Removed: Replicate button (arrow icon)
- Kept: Delete button

#### multi_node_settings.html - Simplified
- Removed: Template Management section with replication checkbox
- Updated: Info alert to explain new per-node template configuration

### 6. Services (`app/services/vm_orchestrator.py`)

#### ensure_template_on_node() - Simplified
- Now directly calls `template.get_template_id_for_node(node_name)`
- Improved error message showing available nodes
- Removed: Complex replica lookup logic

#### Imports Updated
- Removed: `VMTemplateReplica` import
- Added: `TemplateNodeMapping` import

## Workflow Changes

### Before (Old System)
1. Create template on primary node
2. Optionally replicate to other nodes (async, complex, error-prone)
3. Monitor replication status
4. Deploy VM (system automatically finds template copy on target node)

### After (New System)
1. Create template on multiple Proxmox nodes (manual process)
2. Create template in admin panel, specify VMID for each node where it exists
3. Deploy VM (system uses exact node-VMID mapping, no replication)

## Migration Steps for Admins

### Before Running Migration
1. Backup database
2. Identify all nodes where each template exists
3. Note the VMID for each template on each node

### Run Migration
```bash
# Apply the migration
flask db upgrade

# The old template data will be converted to new per-node mappings
# Primary node mappings are created from existing data
# Replica entries are also converted to mappings
```

### After Migration
1. Go to Admin Panel → Templates
2. Verify templates show correct available nodes
3. When deploying VMs, they will use the configured per-node VMID automatically

## Configuration Changes

### Removed Config Options
- `AUTO_REPLICATE_TEMPLATES` - No longer used
- Can be safely removed from `.env` file

### Affected Config Options
- `NODE_SELECTION_STRATEGY` - Still used for choosing deployment node
- `MAX_VMS_PER_NODE` - Still used
- `USE_LINKED_CLONES` - Still used

## Benefits

1. **Simplicity** - No complex replication logic or status tracking
2. **Reliability** - Explicit configuration eliminates race conditions and async failures
3. **Flexibility** - Templates can exist on different subsets of nodes
4. **Clarity** - Admin interface clearly shows which nodes have which templates
5. **Offline Safety** - Works without inter-node communication; errors are immediate and clear

## Error Handling

When deploying a VM:
- If template not registered on selected node: Immediate RuntimeError with available nodes listed
- No silent fallbacks or automatic replica fetching
- Admin must explicitly configure template on required nodes

## Backward Compatibility

- Old `VMTemplateReplica` table preserved but deprecated
- Database migration handles conversion automatically
- Old replica entries become new mappings
- No code cleanup required; system ignores old table

## Testing Recommendations

1. **Test Migration**: Verify templates are correctly converted
2. **Test Creation**: Create new template with multiple node mappings
3. **Test Deployment**: Deploy VM to each configured node
4. **Test Error Handling**: Try deploying to node without template (should show clear error)
5. **Test Scaling**: Verify with multiple templates on varying node sets
