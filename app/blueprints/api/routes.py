from flask import jsonify, session
from flask_login import login_required, current_user
from . import bp
from ...models import VirtualMachine
from ...services.vm_orchestrator import get_vm_status, get_proxmox_client


@bp.route('/vm/<int:vm_id>/status')
@login_required
def vm_status(vm_id):
    """Get current VM status via AJAX"""
    try:
        status = get_vm_status(vm_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500


@bp.route('/vm/<int:vm_id>/vnc-credentials')
def vnc_credentials(vm_id):
    """Get VNC credentials for VM console"""
    try:
        # Verify access permissions
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Check if user is teacher/admin or the student who owns this VM
        if current_user.is_authenticated:
            # Teacher or admin
            if current_user.role not in ['teacher', 'admin']:
                return jsonify({'error': 'Access denied'}), 403
        else:
            # Student - check session
            if 'student_id' not in session or vm.student_id != session['student_id']:
                return jsonify({'error': 'Access denied'}), 403
        
        # Get VNC ticket from Proxmox
        proxmox = get_proxmox_client()
        vnc_data = proxmox.get_vnc_ticket(vm.proxmox_node, vm.proxmox_vmid)
        
        # Cache the ticket for the WebSocket proxy to use
        from ..vnc_proxy.routes import vnc_ticket_cache
        import time
        vnc_ticket_cache[vm_id] = {
            'ticket': vnc_data['ticket'],
            'port': vnc_data['port'],
            'session_ticket': vnc_data.get('session_ticket'),
            'timestamp': time.time()
        }
        
        # Return the ticket as the password for VNC authentication
        return jsonify({'password': vnc_data['ticket']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/vm/<int:vm_id>/start', methods=['POST'])
@login_required
def vm_start(vm_id):
    """Start VM"""
    try:
        # Verify access permissions
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Check if user is teacher/admin or the student who owns this VM
        if current_user.role not in ['teacher', 'admin']:
            if not (hasattr(current_user, 'student') and current_user.student and vm.student_id == current_user.student.id):
                return jsonify({'error': 'Access denied', 'success': False}), 403
        
        # Start the VM
        proxmox = get_proxmox_client()
        result = proxmox.start_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM started successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/stop', methods=['POST'])
@login_required
def vm_stop(vm_id):
    """Stop VM"""
    try:
        # Verify access permissions
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Check if user is teacher/admin or the student who owns this VM
        if current_user.role not in ['teacher', 'admin']:
            if not (hasattr(current_user, 'student') and current_user.student and vm.student_id == current_user.student.id):
                return jsonify({'error': 'Access denied', 'success': False}), 403
        
        # Stop the VM
        proxmox = get_proxmox_client()
        result = proxmox.stop_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM stopped successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/reset', methods=['POST'])
@login_required
def vm_reset(vm_id):
    """Reset VM"""
    try:
        # Verify access permissions
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Check if user is teacher/admin or the student who owns this VM
        if current_user.role not in ['teacher', 'admin']:
            if not (hasattr(current_user, 'student') and current_user.student and vm.student_id == current_user.student.id):
                return jsonify({'error': 'Access denied', 'success': False}), 403
        
        # Reset the VM
        proxmox = get_proxmox_client()
        result = proxmox.reset_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM reset successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/suspend', methods=['POST'])
@login_required
def vm_suspend(vm_id):
    """Suspend VM (teacher only)"""
    try:
        # Verify access permissions - only teachers and admins
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        if current_user.role not in ['teacher', 'admin']:
            return jsonify({'error': 'Access denied', 'success': False}), 403
        
        # Suspend the VM
        proxmox = get_proxmox_client()
        result = proxmox.suspend_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM suspended successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/resume', methods=['POST'])
@login_required
def vm_resume(vm_id):
    """Resume VM (teacher only)"""
    try:
        # Verify access permissions - only teachers and admins
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        if current_user.role not in ['teacher', 'admin']:
            return jsonify({'error': 'Access denied', 'success': False}), 403
        
        # Resume the VM
        proxmox = get_proxmox_client()
        result = proxmox.resume_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM resumed successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/student-info')
@login_required
def vm_student_info(vm_id):
    """Get student information for VM (teacher only)"""
    try:
        # Verify access permissions - only teachers and admins
        if current_user.role not in ['teacher', 'admin']:
            return jsonify({'error': 'Access denied', 'success': False}), 403
        
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        return jsonify({
            'success': True,
            'student_id': vm.student.id,
            'student_name': vm.student.name,
            'classroom': vm.student.classroom.name if vm.student.classroom else None
        })
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})
