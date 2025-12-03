"""VM orchestration service for Proxmox with multi-node support"""

from flask import current_app
from .proxmox_client import ProxmoxClient
from ..models import VirtualMachine, Student, Classroom, VMTemplate, VMTemplateReplica, NodeConfiguration, NodeStorageConfig
from ..extensions import db
import secrets
import string
import time
import random
from typing import List, Dict, Optional


def get_proxmox_client() -> ProxmoxClient:
    """Get configured Proxmox client"""
    return ProxmoxClient(
        host=current_app.config['PROXMOX_HOST'],
        user=current_app.config.get('PROXMOX_USER'),
        token_name=current_app.config.get('PROXMOX_TOKEN_NAME'),
        token_value=current_app.config.get('PROXMOX_TOKEN_VALUE'),
        password=current_app.config.get('PROXMOX_PASSWORD'),
        ssh_host=current_app.config.get('PROXMOX_SSH_HOST'),
        ssh_user=current_app.config.get('PROXMOX_SSH_USER'),
        ssh_key_path=current_app.config.get('PROXMOX_SSH_KEY_PATH')
    )


def initialize_nodes() -> None:
    """Initialize node configurations from Proxmox cluster"""
    try:
        proxmox = get_proxmox_client()
        nodes = proxmox.get_nodes()
        
        for node_name in nodes:
            # Check if node configuration exists
            node_config = NodeConfiguration.query.filter_by(node_name=node_name).first()
            
            if not node_config:
                # Create default configuration
                node_config = NodeConfiguration(
                    node_name=node_name,
                    max_vms=current_app.config.get('MAX_VMS_PER_NODE', 12),
                    storage_pool=current_app.config.get('DEFAULT_VM_STORAGE', 'local-lvm')
                )
                db.session.add(node_config)
        
        db.session.commit()
        print(f"[VM-ORCHESTRATOR] Initialized configurations for {len(nodes)} nodes")
        
    except Exception as e:
        db.session.rollback()
        print(f"[VM-ORCHESTRATOR] Error initializing nodes: {e}")


def select_best_node(strategy: str = None) -> Optional[NodeConfiguration]:
    """Select the best node for VM deployment based on strategy"""
    if not strategy:
        strategy = current_app.config.get('NODE_SELECTION_STRATEGY', 'least_vms')
    
    # Get all active nodes that can accept VMs
    available_nodes = NodeConfiguration.query.filter_by(is_active=True).all()
    available_nodes = [node for node in available_nodes if node.is_available_for_deployment()]
    
    if not available_nodes:
        return None
    
    if strategy == 'least_vms':
        # Select node with fewest VMs
        return min(available_nodes, key=lambda n: n.get_current_vm_count())
    elif strategy == 'round_robin':
        # Simple round-robin (you might want to implement proper state tracking)
        return random.choice(available_nodes)
    elif strategy == 'random':
        return random.choice(available_nodes)
    elif strategy == 'priority':
        # Select highest priority node that's available
        return max(available_nodes, key=lambda n: n.priority)
    else:
        # Default to least VMs
        return min(available_nodes, key=lambda n: n.get_current_vm_count())


def ensure_template_on_node(template: VMTemplate, target_node: str) -> int:
    """Ensure template exists on target node, replicate if necessary"""
    
    # Check if template is already on the target node
    if template.proxmox_node == target_node:
        return template.proxmox_template_id
    
    # Look for existing replica
    replica = template.replicas.filter_by(target_node=target_node).first()
    if replica and replica.is_ready:
        return replica.proxmox_template_id
    
    # Need to replicate template
    if not current_app.config.get('AUTO_REPLICATE_TEMPLATES', True):
        raise Exception(f"Template '{template.name}' not available on node '{target_node}' and auto-replication is disabled")
    
    try:
        proxmox = get_proxmox_client()
        
        # Get next available template ID on target node
        new_template_id = proxmox.get_next_vmid()
        
        print(f"[VM-ORCHESTRATOR] Replicating template '{template.name}' from {template.proxmox_node} to {target_node}")
        
        # Create or update replica record
        if not replica:
            replica = VMTemplateReplica(
                template_id=template.id,
                target_node=target_node,
                proxmox_template_id=new_template_id,
                is_ready=False
            )
            db.session.add(replica)
        else:
            replica.proxmox_template_id = new_template_id
            replica.is_ready = False
        
        db.session.commit()
        
        # Perform the replication
        result = proxmox.replicate_template(
            source_node=template.proxmox_node,
            source_template_id=template.proxmox_template_id,
            target_node=target_node,
            target_template_id=new_template_id
        )
        
        # Create snapshot for linked clones
        proxmox.create_template_snapshot(target_node, new_template_id)
        
        # Mark replica as ready
        replica.is_ready = True
        db.session.commit()
        
        print(f"[VM-ORCHESTRATOR] Template replication completed: {new_template_id} on {target_node}")
        
        return new_template_id
        
    except Exception as e:
        if replica:
            db.session.delete(replica)
        db.session.rollback()
        raise Exception(f"Failed to replicate template to {target_node}: {str(e)}")


def _count_vms_on_storage(node_name: str, storage_name: Optional[str]) -> int:
    q = VirtualMachine.query.filter_by(proxmox_node=node_name)
    if storage_name:
        q = q.filter_by(storage=storage_name)
    return q.count()


def _choose_storage_for_node(node_cfg: NodeConfiguration) -> Optional[str]:
    """Weighted round-robin storage selection honoring per-storage max_vms."""
    stor_rel = getattr(node_cfg, 'storages', None)
    if stor_rel is None:
        stor_configs = []
    elif hasattr(stor_rel, 'filter_by'):
        stor_configs = stor_rel.filter_by(active=True).all()
    else:
        stor_configs = [sc for sc in (stor_rel or []) if getattr(sc, 'active', False)]
    if not stor_configs:
        # Fallback to legacy CSV if present
        return node_cfg.get_next_storage()
    # Build weighted list of available storages
    weighted = []
    for sc in stor_configs:
        used = _count_vms_on_storage(node_cfg.node_name, sc.name)
        if sc.max_vms is not None and used >= sc.max_vms:
            continue
        weight = max(0, sc.weight or 0)
        weighted.extend([sc.name] * (weight if weight > 0 else 0))
    if not weighted:
        return None
    # Use node round-robin index to pick next
    idx = node_cfg.storage_rr_index % len(weighted)
    choice = weighted[idx]
    node_cfg.storage_rr_index = (node_cfg.storage_rr_index + 1) % (len(weighted) if len(weighted) > 0 else 1)
    try:
        db.session.add(node_cfg)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return choice


def deploy_vms_for_students(student_ids: List[int], template_id: int) -> List[VirtualMachine]:
    """Deploy VMs for multiple students with intelligent load balancing"""
    
    template = VMTemplate.query.get(template_id)
    if not template or not template.is_active:
        raise ValueError(f"Template {template_id} not found or inactive")
    
    # Initialize nodes if not already done
    initialize_nodes()
    
    deployed_vms = []
    current_node = None
    vms_on_current_node = 0
    max_vms_per_node = current_app.config.get('MAX_VMS_PER_NODE', 12)
    
    try:
        for student_id in student_ids:
            # Select node if we don't have one or current node is full
            if not current_node or vms_on_current_node >= max_vms_per_node:
                current_node = select_best_node()
                if not current_node:
                    raise Exception("No available nodes for VM deployment")
                vms_on_current_node = 0
                print(f"[VM-ORCHESTRATOR] Selected node {current_node.node_name} for deployment")
            
            # Deploy VM on selected node
            vm = deploy_vm_for_student(student_id, template_id, current_node.node_name)
            deployed_vms.append(vm)
            vms_on_current_node += 1
            
            print(f"[VM-ORCHESTRATOR] Deployed VM {vm.proxmox_vmid} for student {student_id} on {current_node.node_name}")
    
    except Exception as e:
        # Clean up any VMs that were created before the error
        for vm in deployed_vms:
            try:
                delete_vm(vm.id)
            except:
                pass
        raise e
    
    return deployed_vms


def plan_storage_distribution(student_ids: List[int], template_id: int) -> List[Dict]:
    """Dry-run planning of node + storage assignment without cloning VMs.
    Returns list of dicts: {'student_id': ..., 'node': ..., 'storage': ...}
    """
    from flask import current_app
    initialize_nodes()
    template = VMTemplate.query.get(template_id)
    if not template:
        raise ValueError('Template not found')
    plan = []
    for student_id in student_ids:
        node = select_best_node(current_app.config.get('NODE_SELECTION_STRATEGY'))
        if not node:
            plan.append({'student_id': student_id, 'node': None, 'storage': None})
            continue
        storage = _choose_storage_for_node(node)
        if not storage:
            storage = current_app.config.get('DEFAULT_VM_STORAGE')
        plan.append({'student_id': student_id, 'node': node.node_name, 'storage': storage})
    return plan


def replicate_template_to_all_nodes(template_id: int) -> None:
    """Replicate a template to all active nodes"""
    template = VMTemplate.query.get(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")
    
    # Get all active nodes
    nodes = NodeConfiguration.query.filter_by(is_active=True).all()
    
    for node_config in nodes:
        # Skip if this is the source node
        if node_config.node_name == template.proxmox_node:
            continue
        
        # Check if replica already exists
        existing_replica = template.replicas.filter_by(target_node=node_config.node_name).first()
        if existing_replica and existing_replica.is_ready:
            print(f"[VM-ORCHESTRATOR] Template '{template.name}' already replicated to {node_config.node_name}")
            continue
        
        try:
            # Replicate template to this node
            ensure_template_on_node(template, node_config.node_name)
            print(f"[VM-ORCHESTRATOR] Successfully replicated template '{template.name}' to {node_config.node_name}")
        except Exception as e:
            print(f"[VM-ORCHESTRATOR] Failed to replicate template '{template.name}' to {node_config.node_name}: {e}")
            # Don't raise here - continue with other nodes


def prepare_template_for_linked_clones(template_id: int) -> None:
    """Ensure template has the required snapshot for linked clones"""
    template = VMTemplate.query.get(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")
    
    try:
        proxmox = get_proxmox_client()
        
        # Create snapshot on primary template
        proxmox.create_template_snapshot(
            template.proxmox_node, 
            template.proxmox_template_id
        )
        print(f"[VM-ORCHESTRATOR] Created linked clone snapshot for template '{template.name}'")
        
        # Create snapshots on all replicas
        for replica in template.replicas.filter_by(is_ready=True):
            try:
                proxmox.create_template_snapshot(
                    replica.target_node,
                    replica.proxmox_template_id
                )
                print(f"[VM-ORCHESTRATOR] Created snapshot on replica {replica.target_node}")
            except Exception as e:
                print(f"[VM-ORCHESTRATOR] Warning: Could not create snapshot on {replica.target_node}: {e}")
                
    except Exception as e:
        print(f"[VM-ORCHESTRATOR] Error preparing template for linked clones: {e}")
        raise


def get_node_statistics() -> Dict:
    """Get comprehensive statistics about node usage and performance"""
    nodes = NodeConfiguration.query.all()
    stats = {
        'total_nodes': len(nodes),
        'active_nodes': len([n for n in nodes if n.is_active]),
        'total_capacity': sum(n.max_vms for n in nodes),
        'total_vms': sum(n.get_current_vm_count() for n in nodes),
        'nodes': []
    }
    
    for node in nodes:
        vm_count = node.get_current_vm_count()
        node_stats = {
            'name': node.node_name,
            'vm_count': vm_count,
            'max_vms': node.max_vms,
            'utilization': (vm_count / node.max_vms * 100) if node.max_vms > 0 else 0,
            'is_active': node.is_active,
            'priority': node.priority,
            'storage_pool': node.storage_pool,
            'available_slots': max(0, node.max_vms - vm_count) if node.is_active else 0
        }
        stats['nodes'].append(node_stats)
    
    # Calculate overall utilization
    stats['overall_utilization'] = (stats['total_vms'] / stats['total_capacity'] * 100) if stats['total_capacity'] > 0 else 0
    
    return stats





def deploy_vm_for_student(student_id: int, template_id: int, node: str = None) -> VirtualMachine:
    """Deploy a VM for a student from a template with multi-node support
    
    Args:
        student_id: Student database ID
        template_id: Database template ID (not Proxmox template ID)
        node: Proxmox node name (optional, will auto-select if None)
    
    Returns:
        VirtualMachine object
    """
    proxmox = get_proxmox_client()
    
    student = Student.query.get(student_id)
    if not student:
        raise ValueError(f"Student {student_id} not found")
    
    template = VMTemplate.query.get(template_id)
    if not template or not template.is_active:
        raise ValueError(f"Template {template_id} not found or inactive")
    
    classroom = student.classroom
    
    try:
        # Select node if not specified
        if not node:
            node_config = select_best_node()
            if not node_config:
                raise Exception("No available nodes for VM deployment")
            node = node_config.node_name
        
        # Ensure template is available on target node
        proxmox_template_id = ensure_template_on_node(template, node)
        
        # Get next available VM ID
        new_vmid = proxmox.get_next_vmid()
        
        # VM name must be valid DNS name: lowercase, letters/numbers/hyphens only
        clean_classroom = ''.join(c if c.isalnum() else '-' for c in classroom.name.lower())
        clean_student = ''.join(c if c.isalnum() else '-' for c in student.name.lower())
        vm_name = f"{clean_classroom}-{clean_student}-{new_vmid}"
        
        # Get storage for this node
        node_config = NodeConfiguration.query.filter_by(node_name=node).first()
        # Choose storage via weighted round-robin across configured storages
        storage = _choose_storage_for_node(node_config) if node_config else None
        if not storage:
            storage = current_app.config.get('DEFAULT_VM_STORAGE', 'local-lvm')
        
        # Create linked clone for better performance
        use_linked_clones = current_app.config.get('USE_LINKED_CLONES', True)
        
        print(f"[VM-ORCHESTRATOR] Cloning template {proxmox_template_id} -> VM {new_vmid} on {node} (linked: {use_linked_clones})")
        
        # For linked clones, optionally force storage param if configured
        force_storage = current_app.config.get('FORCE_STORAGE_FOR_LINKED_CLONES', False)
        clone_storage = storage if (force_storage and use_linked_clones) else (None if use_linked_clones else storage)
        
        proxmox.clone_vm(
            node=node, 
            template_id=proxmox_template_id, 
            new_vmid=new_vmid, 
            name=vm_name,
            storage=clone_storage,
            linked=use_linked_clones
        )
        
        # Apply performance optimizations
        proxmox.optimize_vm_for_performance(node, new_vmid)
        
        # Start the VM
        proxmox.start_vm(node, new_vmid)
        
        # Wait a moment and get VM config to find IP
        time.sleep(2)  # Give VM time to initialize
        config = proxmox.get_vm_config(node, new_vmid)
        vm_ip = config.get('ipconfig0', '').split('=')[1].split('/')[0] if 'ipconfig0' in config else None
        
        # For isolated VMs, store Proxmox console URL
        console_url = proxmox.get_console_url(node, new_vmid)
        
        # Create VM record in database
        vm = VirtualMachine(
            student_id=student_id,
            proxmox_vmid=new_vmid,
            proxmox_node=node,
            template_name=template.name,
            console_url=console_url,
            status='running',
            ip_address=vm_ip,
            storage=storage
        )
        db.session.add(vm)
        db.session.commit()
        
        print(f"[VM-ORCHESTRATOR] Successfully deployed VM {new_vmid} for student {student.name} on node {node}")
        
        return vm
    
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Failed to deploy VM: {str(e)}")


def delete_vm(vm_id: int) -> None:
    """Delete a VM"""
    vm = VirtualMachine.query.get(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")
    
    proxmox = get_proxmox_client()
    
    try:
        # Delete from Proxmox
        if vm.proxmox_vmid and vm.proxmox_node:
            try:
                proxmox.stop_vm(vm.proxmox_node, vm.proxmox_vmid)
            except:
                pass  # VM might already be stopped
            proxmox.delete_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        # Delete from database
        db.session.delete(vm)
        db.session.commit()
    
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Failed to delete VM: {str(e)}")


def stop_vm_for_student(vm_id: int) -> None:
    """Stop a VM"""
    vm = VirtualMachine.query.get(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")
    
    proxmox = get_proxmox_client()
    
    try:
        proxmox.stop_vm(vm.proxmox_node, vm.proxmox_vmid)
        vm.status = 'stopped'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Failed to stop VM: {str(e)}")


def start_vm_for_student(vm_id: int) -> None:
    """Start a VM"""
    vm = VirtualMachine.query.get(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")
    
    proxmox = get_proxmox_client()
    
    try:
        proxmox.start_vm(vm.proxmox_node, vm.proxmox_vmid)
        vm.status = 'running'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Failed to start VM: {str(e)}")


def get_vm_status(vm_id: int) -> dict:
    """Get current status of a VM"""
    vm = VirtualMachine.query.get(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")
    
    proxmox = get_proxmox_client()
    
    try:
        status = proxmox.get_vm_status(vm.proxmox_node, vm.proxmox_vmid)
        
        # Update database
        vm.status = status.get('status', 'unknown')
        db.session.commit()
        
        return {
            'id': vm.id,
            'vmid': vm.proxmox_vmid,
            'status': vm.status,
            'ip_address': vm.ip_address,
            'node': vm.proxmox_node
        }
    except Exception as e:
        return {
            'id': vm.id,
            'vmid': vm.proxmox_vmid,
            'status': 'error',
            'error': str(e)
        }
