from flask import jsonify, session
from flask_login import login_required, current_user
from functools import wraps
from . import bp
from ...models import VirtualMachine
from ...services.vm_orchestrator import get_vm_status, get_proxmox_client


def check_vm_access(vm_id):
    """Check if current user/student has access to the VM. Returns (has_access, error_response)"""
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
    except:
        return False, jsonify({'error': 'VM not found'}), 404
    
    # Check Flask-Login authentication
    if current_user.is_authenticated:
        # Admin has access to all VMs
        if current_user.is_admin():
            return True, None, None
        # Teacher has access to their classroom's VMs
        if current_user.role == 'teacher' and vm.student and vm.student.classroom:
            if vm.student.classroom.teacher_id == current_user.id:
                return True, None, None
        # Students checking their own VMs (if they have student relation)
        if hasattr(current_user, 'student') and current_user.student:
            if vm.student_id == current_user.student.id:
                return True, None, None
        return False, jsonify({'error': 'Access denied'}), 403
    
    # Check session-based student authentication
    if session.get('student_id'):
        if vm.student_id == session.get('student_id'):
            return True, None, None
        return False, jsonify({'error': 'Access denied'}), 403
    
    # Not authenticated
    return False, jsonify({'error': 'Not authenticated'}), 401


@bp.route('/vm/<int:vm_id>/status')
def vm_status(vm_id):
    """Get current VM status via AJAX"""
    has_access, error_response, status_code = check_vm_access(vm_id)
    if not has_access:
        return error_response, status_code
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        status = get_vm_status(vm.proxmox_node, vm.proxmox_vmid)
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500


@bp.route('/vm/<int:vm_id>/console-url')
def console_url(vm_id):
    """Get console URL for VM"""
    has_access, error_response, status_code = check_vm_access(vm_id)
    if not has_access:
        return error_response, status_code
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Get proxmox client and console URL
        prox = get_proxmox_client()
        console_url = prox.get_console_url(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'console_url': console_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/vm/<int:vm_id>/vnc-websocket')
def vnc_websocket_url(vm_id):
    """Get VNC WebSocket URL and credentials for direct browser connection"""
    has_access, error_response, status_code = check_vm_access(vm_id)
    if not has_access:
        return error_response, status_code
    
    try:
        from ...services.proxmox_client import ProxmoxClient
        from flask import current_app
        
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Get proxmox client
        proxmox = ProxmoxClient(
            host=current_app.config.get('PROXMOX_HOST'),
            user=current_app.config.get('PROXMOX_USER'),
            token_name=current_app.config.get('PROXMOX_TOKEN_NAME'),
            token_value=current_app.config.get('PROXMOX_TOKEN_VALUE'),
            password=current_app.config.get('PROXMOX_PASSWORD'),
            ssh_host=current_app.config.get('PROXMOX_SSH_HOST', '192.168.1.2'),
            ssh_user=current_app.config.get('PROXMOX_SSH_USER', 'root'),
            ssh_key_path=current_app.config.get('PROXMOX_SSH_KEY_PATH'),
        )
        
        # Get VNC ticket
        vnc_data = proxmox.get_vnc_ticket(vm.proxmox_node, vm.proxmox_vmid)
        
        # Get auth cookie
        auth_cookie = None
        try:
            auth_cookie = proxmox.get_auth_cookie()
        except:
            pass
        
        # Build WebSocket URL
        proxmox_host = (current_app.config.get('PROXMOX_HOST') or '').replace('https://', '').replace('http://', '')
        ws_url = f"wss://{proxmox_host}/api2/json/nodes/{vm.proxmox_node}/qemu/{vm.proxmox_vmid}/vncwebsocket"
        ws_url += f"?port={vnc_data['port']}"
        
        return jsonify({
            'success': True,
            'url': ws_url,
            'ticket': vnc_data['ticket'],
            'port': vnc_data['port'],
            'auth_cookie': auth_cookie,
            'node': vm.proxmox_node,
            'vmid': vm.proxmox_vmid
        })
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/start', methods=['POST'])
def vm_start(vm_id):
    """Start VM"""
    has_access, error_response, status_code = check_vm_access(vm_id)
    if not has_access:
        return error_response, status_code
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Start the VM
        proxmox = get_proxmox_client()
        result = proxmox.start_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM started successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/stop', methods=['POST'])
def vm_stop(vm_id):
    """Stop VM"""
    has_access, error_response, status_code = check_vm_access(vm_id)
    if not has_access:
        return error_response, status_code
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Stop the VM
        proxmox = get_proxmox_client()
        result = proxmox.stop_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM stopped successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/reset', methods=['POST'])
def vm_reset(vm_id):
    """Reset VM"""
    has_access, error_response, status_code = check_vm_access(vm_id)
    if not has_access:
        return error_response, status_code
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Reset the VM
        proxmox = get_proxmox_client()
        result = proxmox.reset_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM reset successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/suspend', methods=['POST'])
def vm_suspend(vm_id):
    """Suspend VM (teacher only)"""
    # Only allow teachers and admins to suspend VMs
    if current_user.is_authenticated:
        if current_user.role not in ['teacher', 'admin']:
            return jsonify({'error': 'Access denied', 'success': False}), 403
    else:
        # Students via session can't suspend
        return jsonify({'error': 'Access denied', 'success': False}), 403
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Suspend the VM
        proxmox = get_proxmox_client()
        result = proxmox.suspend_vm(vm.proxmox_node, vm.proxmox_vmid)
        
        return jsonify({'success': True, 'message': 'VM suspended successfully', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@bp.route('/vm/<int:vm_id>/resume', methods=['POST'])
def vm_resume(vm_id):
    """Resume VM (teacher only)"""
    # Only allow teachers and admins to resume VMs
    if current_user.is_authenticated:
        if current_user.role not in ['teacher', 'admin']:
            return jsonify({'error': 'Access denied', 'success': False}), 403
    else:
        # Students via session can't resume
        return jsonify({'error': 'Access denied', 'success': False}), 403
    
    try:
        vm = VirtualMachine.query.get_or_404(vm_id)
        
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
