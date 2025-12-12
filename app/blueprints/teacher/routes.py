from flask import render_template, redirect, url_for, flash, request, jsonify
import time
from flask_login import login_required, current_user
from . import bp
from .forms import ImportClassForm, AddStudentForm, DeployVMForm
from ...models import Classroom, Student, VirtualMachine, VMTemplate
from ...extensions import db
from ...security import teacher_required
from ...services.vm_orchestrator import (
    deploy_vm_for_student,
    get_proxmox_client
)
import re
import secrets
import csv
from io import StringIO

def generate_student_credentials(name: str):
    """Generate a unique username and random password from a student name"""
    base = re.sub(r'[^a-zA-Z0-9]+', '-', name.strip().lower())
    base = re.sub(r'-{2,}', '-', base).strip('-')
    if not base:
        base = 'student'
    candidate = base
    counter = 1
    from ...models import Student
    while Student.query.filter_by(username=candidate).first():
        counter += 1
        candidate = f"{base}{counter}"
    password = secrets.token_urlsafe(8)  # ~11 chars, URL safe
    return candidate, password


@bp.route('/')
@login_required
@teacher_required
def dashboard():
    """Teacher dashboard showing all classes"""
    if current_user.is_admin():
        classrooms = Classroom.query.all()
    else:
        classrooms = current_user.classrooms.all()
    
    return render_template('teacher/dashboard.html', classrooms=classrooms)


@bp.route('/import', methods=['GET', 'POST'])
@login_required
@teacher_required
def import_class():
    """Import a new class with students"""
    form = ImportClassForm()
    
    if form.validate_on_submit():
        try:
            # Create classroom
            classroom = Classroom(
                name=form.class_name.data,
                teacher_id=current_user.id
            )
            db.session.add(classroom)
            db.session.flush()  # Get classroom ID

            # Parse student names (one per line)
            student_names = [line.strip() for line in form.students_text.data.split('\n') if line.strip()]

            # Create students with generated credentials
            generated_summary = []
            for name in student_names:
                username, plain_pw = generate_student_credentials(name)
                student = Student(name=name, classroom_id=classroom.id, username=username, is_active=True)
                student.set_password(plain_pw)
                # Store encrypted initial password so teachers can view it; don't store plaintext.
                try:
                    student.set_initial_password(plain_pw)
                except Exception:
                    # If encryption isn't configured, fall back to not storing initial password.
                    pass
                # Do NOT store plaintext passwords. Provide credentials as a one-time download below.
                db.session.add(student)
                db.session.flush()

                generated_summary.append((name, username, plain_pw))

            db.session.commit()
            # Redirect to class details; passwords will be rendered inline per student
            flash(f'Class "{classroom.name}" imported with {len(student_names)} students!', 'success')
            return redirect(url_for('teacher.class_detail', class_id=classroom.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error importing class: {str(e)}', 'danger')

    return render_template('teacher/import_class.html', form=form)


@bp.route('/class/<int:class_id>')
@login_required
@teacher_required
def class_detail(class_id):
    """View class details with students and VMs"""
    classroom = Classroom.query.get_or_404(class_id)
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    students = classroom.students.all()
    templates = VMTemplate.query.filter_by(is_active=True).all()
    
    # Prepare student data with VMs
    student_data = []
    for student in students:
        vms = student.vms.all()
        # Decrypt initial password for display to teachers (requires FERNET_KEY configured)
        try:
            initial_pw = student.get_initial_password()
        except Exception:
            initial_pw = None
        student_data.append({
            'student': student,
            'vms': vms,
            'initial_password': initial_pw
        })
    
    return render_template('teacher/class_detail.html', 
                         classroom=classroom,
                         student_data=student_data,
                         templates=templates)


@bp.route('/class/<int:class_id>/credentials.csv', methods=['GET'])
@login_required
@teacher_required
def download_class_credentials(class_id):
    """Download CSV of all students' credentials for a class"""
    classroom = Classroom.query.get_or_404(class_id)
    # Permission check
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'username', 'password'])
    for student in classroom.students.order_by(Student.name.asc()).all():
        try:
            pw = student.get_initial_password()
        except Exception:
            pw = None
        writer.writerow([student.name or '', student.username or '', pw or ''])

    csv_data = output.getvalue()
    from flask import make_response
    resp = make_response(csv_data)
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=class_{classroom.id}_credentials.csv'
    return resp


@bp.route('/class/<int:class_id>/bulk_vm_cleanup', methods=['POST'])
@login_required
@teacher_required
def class_bulk_vm_cleanup(class_id):
    """Stop and delete all VMs for every student in the class"""
    classroom = Classroom.query.get_or_404(class_id)

    # Permission check
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))

    stopped = 0
    deleted = 0
    errors = []

    proxmox = get_proxmox_client()

    # Iterate through students and their VMs
    for student in classroom.students.all():
        for vm in student.vms.all():
            try:
                # Always attempt stop first (idempotent)
                try:
                    if vm.status == 'running':
                        stop_vm_for_student(vm.id)
                        stopped += 1
                except Exception as e:
                    errors.append(f'Stop VM {vm.proxmox_vmid}: {e}')

                # Poll Proxmox status until not running (max ~30s)
                for attempt in range(15):
                    try:
                        status_data = proxmox.get_vm_status(vm.proxmox_node, vm.proxmox_vmid)
                        current_status = status_data.get('status') or status_data.get('qmpstatus')
                    except Exception as poll_err:
                        current_status = vm.status  # fallback
                        errors.append(f'Status poll VM {vm.proxmox_vmid}: {poll_err}')
                    if current_status and current_status.lower() != 'running':
                        break
                    time.sleep(2)

                # Delete with wait complete
                try:
                    delete_vm(vm.id)
                    deleted += 1
                except Exception as e:
                    errors.append(f'Delete VM {vm.proxmox_vmid}: {e}')
            except Exception as e:
                errors.append(f'VM {vm.proxmox_vmid} general error: {e}')

    if deleted:
        flash(f'Bulk VM cleanup complete: stopped {stopped}, deleted {deleted} VMs.', 'success')
    else:
        flash('No VMs found to clean up.', 'info')

    if errors:
        flash('Some errors occurred: ' + '; '.join(errors[:5]) + (' ...' if len(errors) > 5 else ''), 'warning')

    return redirect(url_for('teacher.class_detail', class_id=class_id))


@bp.route('/class/<int:class_id>/add_student', methods=['POST'])
@login_required
@teacher_required
def add_student(class_id):
    """Add a single student to a class"""
    classroom = Classroom.query.get_or_404(class_id)
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    student_name = request.form.get('student_name', '').strip()
    
    if not student_name:
        flash('Student name is required', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    
    # Generate credentials
    username, plain_pw = generate_student_credentials(student_name)
    
    try:
        student = Student(name=student_name, classroom_id=classroom.id, username=username, is_active=True)
        student.set_password(plain_pw)
        try:
            student.set_initial_password(plain_pw)
        except Exception:
            pass
        # Do NOT store plaintext passwords. Provide credentials as a one-time download below.
        db.session.add(student)
        db.session.commit()
        # Show credentials inline on the page for teacher convenience
        flash(f'Added student {student_name} (username: {username}) — initial password shown in the list below.', 'success')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding student: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=class_id))


@bp.route('/console/<int:vm_id>')
@login_required
@teacher_required
def console(vm_id):
    """Embedded console view for a VM"""
    vm = VirtualMachine.query.get_or_404(vm_id)
    classroom = vm.student.classroom
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    # Pass VM info to template - WebSocket will be proxied through Flask
    return render_template('teacher/console.html', 
                         vm=vm,
                         node=vm.proxmox_node,
                         vmid=vm.proxmox_vmid)


@bp.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_student(student_id):
    """Delete a student"""
    student = Student.query.get_or_404(student_id)
    classroom = student.classroom
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    try:
        # Delete all VMs for this student
        for vm in student.vms.all():
            try:
                delete_vm(vm.id)
            except Exception as e:
                flash(f'Warning: Could not delete VM {vm.proxmox_vmid}: {str(e)}', 'warning')
        
        db.session.delete(student)
        db.session.commit()
        flash(f'Student "{student.name}" deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=classroom.id))


@bp.route('/student/<int:student_id>/deploy_vm', methods=['POST'])
@login_required
@teacher_required
def deploy_vm(student_id):
    """Deploy a VM for a student"""
    student = Student.query.get_or_404(student_id)
    classroom = student.classroom
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    template_id = request.form.get('template_id', type=int)
    if not template_id:
        flash('Template ID is required', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=classroom.id))
    
    template = VMTemplate.query.get(template_id)
    if not template:
        flash('Invalid template', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=classroom.id))
    
    try:
        vm = deploy_vm_for_student(
            student_id=student_id,
            template_id=template.id  # Use database template ID, not Proxmox template ID
        )
        flash(f'VM deployed successfully for {student.name}! VM ID: {vm.proxmox_vmid} on node {vm.proxmox_node}', 'success')
    except Exception as e:
        flash(f'Error deploying VM: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=classroom.id))


@bp.route('/vm/<int:vm_id>/stop', methods=['POST'])
@login_required
@teacher_required
def stop_vm_route(vm_id):
    """Stop a VM"""
    from ...services.vm_orchestrator import stop_vm_for_student
    
    vm = VirtualMachine.query.get_or_404(vm_id)
    student = vm.student
    classroom = student.classroom
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    try:
        stop_vm_for_student(vm_id)
        flash(f'VM {vm.proxmox_vmid} stopped successfully', 'success')
    except Exception as e:
        flash(f'Error stopping VM: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=classroom.id))


@bp.route('/vm/<int:vm_id>/start', methods=['POST'])
@login_required
@teacher_required
def start_vm_route(vm_id):
    """Start a VM"""
    from ...services.vm_orchestrator import start_vm_for_student
    
    vm = VirtualMachine.query.get_or_404(vm_id)
    student = vm.student
    classroom = student.classroom
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    try:
        start_vm_for_student(vm_id)
        flash(f'VM {vm.proxmox_vmid} started successfully', 'success')
    except Exception as e:
        flash(f'Error starting VM: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=classroom.id))


@bp.route('/vm/<int:vm_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_vm_route(vm_id):
    """Delete a VM"""
    vm = VirtualMachine.query.get_or_404(vm_id)
    student = vm.student
    classroom = student.classroom
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    try:
        delete_vm(vm_id)
        flash(f'VM {vm.proxmox_vmid} deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting VM: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=classroom.id))


@bp.route('/student/<int:student_id>/reset_password', methods=['POST'])
@login_required
@teacher_required
def reset_student_password(student_id):
    """Reset a student's password and update the stored initial password."""
    student = Student.query.get_or_404(student_id)
    classroom = student.classroom

    # Permission check
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))

    # Generate a new secure password
    new_pw = secrets.token_urlsafe(10)

    try:
        student.set_password(new_pw)
        try:
            student.set_initial_password(new_pw)
        except Exception:
            pass
        db.session.commit()
        flash(f'Reset password for {student.name} (username: {student.username}). New password shown below.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error resetting password: {str(e)}', 'danger')

    return redirect(url_for('teacher.class_detail', class_id=classroom.id))


@bp.route('/class/<int:class_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_class(class_id):
    """Delete a class"""
    classroom = Classroom.query.get_or_404(class_id)
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    try:
        # Cascading delete will handle students and VMs
        db.session.delete(classroom)
        db.session.commit()
        flash(f'Class "{classroom.name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting class: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.dashboard'))


@bp.route('/class/<int:class_id>/deploy_bulk_vms', methods=['POST'])
@login_required
@teacher_required
def deploy_bulk_vms(class_id):
    """Deploy VMs for multiple students at once"""
    classroom = Classroom.query.get_or_404(class_id)
    
    # Check permission
    if not current_user.is_admin() and classroom.teacher_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    template_id = request.form.get('template_id', type=int)
    selected_student_ids = request.form.getlist('student_ids', type=int)
    
    if not template_id:
        flash('Template ID is required', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    
    if not selected_student_ids:
        flash('Please select at least one student', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    
    template = VMTemplate.query.get(template_id)
    if not template or not template.is_active:
        flash('Invalid or inactive template', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    
    # Verify all students belong to this classroom
    students = Student.query.filter(Student.id.in_(selected_student_ids)).all()
    if not all(student.classroom_id == class_id for student in students):
        flash('Invalid student selection', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    
    try:
        from ...services.vm_orchestrator import deploy_vms_for_students
        
        deployed_vms = deploy_vms_for_students(selected_student_ids, template_id)
        
        # Group results by node for display
        node_summary = {}
        for vm in deployed_vms:
            if vm.proxmox_node not in node_summary:
                node_summary[vm.proxmox_node] = 0
            node_summary[vm.proxmox_node] += 1
        
        summary_msg = f'Successfully deployed {len(deployed_vms)} VMs'
        if len(node_summary) > 1:
            node_details = ', '.join([f'{count} on {node}' for node, count in node_summary.items()])
            summary_msg += f' ({node_details})'
        
        flash(summary_msg, 'success')
        
    except Exception as e:
        flash(f'Error during bulk deployment: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.class_detail', class_id=class_id))
