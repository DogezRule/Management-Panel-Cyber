from flask import render_template, redirect, url_for, flash, session, request
from functools import wraps
from . import bp
from ...models import Student, VirtualMachine
from ...extensions import db
from ...services.proxmox_client import ProxmoxClient
import os


def student_required(f):
    """Decorator to require student login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.student_login'))
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/')
@student_required
def dashboard():
    """Student dashboard showing their VMs"""
    student_id = session.get('student_id')
    student = Student.query.get_or_404(student_id)
    
    # Get all VMs for this student
    vms = student.vms.all()
    
    return render_template('student/dashboard.html', student=student, vms=vms)


@bp.route('/console/<int:vm_id>')
@student_required
def console(vm_id):
    """Embedded console view for a specific VM"""
    student_id = session.get('student_id')
    student = Student.query.get_or_404(student_id)
    
    # Get VM and verify it belongs to this student
    vm = VirtualMachine.query.get_or_404(vm_id)
    if vm.student_id != student.id:
        flash('Access denied', 'danger')
        return redirect(url_for('auth.student_login'))
    
    # Pass VM info to template - WebSocket will be proxied through Flask
    return render_template('student/console.html', 
                         student=student, 
                         vm=vm,
                         node=vm.proxmox_node,
                         vmid=vm.proxmox_vmid)
