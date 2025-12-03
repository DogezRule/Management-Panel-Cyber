from flask import render_template, redirect, url_for, flash, request, send_file, abort, Response, jsonify
from flask_login import login_required
from . import bp
from .forms import CreateTeacherForm, CreateVMTemplateForm, NodeConfigurationForm, MultiNodeSettingsForm
from ...models import User, Classroom, Student, VirtualMachine, VMTemplate, NodeConfiguration, VMTemplateReplica
from ...extensions import db
from ...security import admin_required, hash_password
import os


@bp.route('/')
@login_required
@admin_required
def dashboard():
    """IT Admin dashboard"""
    from ...services.vm_orchestrator import initialize_nodes
    
    # Initialize nodes if needed
    try:
        initialize_nodes()
    except Exception as e:
        flash(f'Warning: Could not initialize nodes: {str(e)}', 'warning')
    
    teachers = User.query.filter_by(role='teacher').all()
    templates = VMTemplate.query.filter_by(is_active=True).all()
    nodes = NodeConfiguration.query.all()
    
    # Statistics
    total_classes = Classroom.query.count()
    total_students = Student.query.count()
    total_vms = VirtualMachine.query.count()
    
    # Node statistics
    node_stats = []
    for node in nodes:
        vm_count = node.get_current_vm_count()
        node_stats.append({
            'name': node.node_name,
            'vm_count': vm_count,
            'max_vms': node.max_vms,
            'utilization': (vm_count / node.max_vms * 100) if node.max_vms > 0 else 0,
            'is_active': node.is_active,
            'available': node.is_available_for_deployment()
        })
    
    stats = {
        'teachers': len(teachers),
        'classes': total_classes,
        'students': total_students,
        'vms': total_vms,
        'nodes': len(nodes),
        'active_nodes': len([n for n in nodes if n.is_active])
    }
    
    return render_template('admin/dashboard.html', 
                         teachers=teachers, 
                         templates=templates,
                         nodes=node_stats,
                         stats=stats)


@bp.route('/logs', methods=['GET'])
@login_required
@admin_required
def logs_page():
    """Admin page to download auth logs"""
    return render_template('admin/logs.html')


@bp.route('/logs/download', methods=['GET'])
@login_required
@admin_required
def download_logs():
    """Download the last 10,000 lines of the auth.log file if present"""
    from flask import current_app
    logs_dir = os.path.join(current_app.instance_path, 'logs')
    log_path = os.path.join(logs_dir, 'auth.log')
    if not os.path.exists(log_path):
        abort(404)
    # Tail last 10,000 lines without loading entire file into memory unnecessarily
    try:
        max_lines = 10000
        with open(log_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = bytearray()
            lines = 0
            while size > 0 and lines <= max_lines:
                read_size = block if size >= block else size
                size -= read_size
                f.seek(size)
                chunk = f.read(read_size)
                data[:0] = chunk
                lines = data.count(b'\n')
            # Keep only last max_lines
            if lines > max_lines:
                # find the position of the (lines-max_lines)th newline from start
                to_trim = lines - max_lines
                idx = 0
                for _ in range(to_trim):
                    idx = data.find(b'\n', idx) + 1
                data = data[idx:]
        return Response(bytes(data), mimetype='text/plain', headers={
            'Content-Disposition': 'attachment; filename="auth.log"'
        })
    except Exception:
        # Fallback to send_file if tailing fails
        return send_file(log_path, as_attachment=True, download_name='auth.log', mimetype='text/plain')


@bp.route('/teachers/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_teacher():
    """Create a new teacher account"""
    form = CreateTeacherForm()
    
    if form.validate_on_submit():
        # Check if username already exists
        existing = User.query.filter_by(email=form.username.data).first()
        if existing:
            flash('A user with this username already exists', 'danger')
            return render_template('admin/create_teacher.html', form=form)
        
        try:
            # Create teacher user
            teacher = User(
                email=form.username.data,
                password_hash=hash_password(form.password.data),
                role='teacher'
            )
            
            # Auto credential / noVNC only; no external remote user provisioning
            
            db.session.add(teacher)
            db.session.commit()
            
            flash(f'Teacher account created successfully! Username: {teacher.email}', 'success')
            return redirect(url_for('admin.dashboard'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating teacher: {str(e)}', 'danger')
    
    return render_template('admin/create_teacher.html', form=form)


@bp.route('/teachers/<int:teacher_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_teacher(teacher_id):
    """Delete a teacher account"""
    teacher = User.query.get_or_404(teacher_id)
    
    if teacher.role != 'teacher':
        flash('Cannot delete non-teacher users', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    try:
        # Delete teacher and all cascading data
        db.session.delete(teacher)
        db.session.commit()
        flash(f'Teacher {teacher.email} deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting teacher: {str(e)}', 'danger')
    
    return redirect(url_for('admin.dashboard'))


@bp.route('/templates/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_template():
    """Register a new VM template"""
    form = CreateVMTemplateForm()
    
    if form.validate_on_submit():
        template = VMTemplate(
            name=form.name.data,
            proxmox_template_id=form.proxmox_template_id.data,
            proxmox_node=form.proxmox_node.data,
            description=form.description.data,
            memory=form.memory.data,
            cores=form.cores.data,
            is_active=form.is_active.data,
            replicate_to_all_nodes=form.replicate_to_all_nodes.data
        )
        
        try:
            db.session.add(template)
            db.session.commit()
            
            # If auto-replication is enabled, trigger replication
            if form.replicate_to_all_nodes.data:
                try:
                    from ...services.vm_orchestrator import replicate_template_to_all_nodes
                    replicate_template_to_all_nodes(template.id)
                    flash(f'VM template "{template.name}" created and replication started', 'success')
                except Exception as e:
                    flash(f'Template created but replication failed: {str(e)}', 'warning')
            else:
                flash(f'VM template "{template.name}" created successfully', 'success')
                
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating template: {str(e)}', 'danger')
    
    return render_template('admin/create_template.html', form=form)


@bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_template(template_id):
    """Delete a VM template"""
    template = VMTemplate.query.get_or_404(template_id)
    
    try:
        db.session.delete(template)
        db.session.commit()
        flash(f'Template "{template.name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting template: {str(e)}', 'danger')
    
    return redirect(url_for('admin.dashboard'))


@bp.route('/nodes')
@login_required
@admin_required
def nodes():
    """Node management page"""
    nodes = NodeConfiguration.query.all()
    # Build per-storage counts for active storages
    from ...models import VirtualMachine, NodeStorageConfig
    storage_counts = {}
    for node in nodes:
        sc_list = []
        # Prefer structured storage configs
        try:
            stor_cfgs = node.storages.filter_by(active=True).all()
        except Exception:
            stor_cfgs = []
        if stor_cfgs:
            for sc in stor_cfgs:
                count = VirtualMachine.query.filter_by(proxmox_node=node.node_name, storage=sc.name).count()
                sc_list.append({
                    'name': sc.name,
                    'count': count,
                    'max_vms': sc.max_vms
                })
        else:
            # Fallback to legacy CSV list
            for name in (node.get_storages_list() or []):
                count = VirtualMachine.query.filter_by(proxmox_node=node.node_name, storage=name).count()
                sc_list.append({
                    'name': name,
                    'count': count,
                    'max_vms': None
                })
        storage_counts[node.id] = sc_list
    return render_template('admin/nodes.html', nodes=nodes, storage_counts=storage_counts)


@bp.route('/api/nodes/<string:node_name>/storages', methods=['GET'])
@login_required
@admin_required
def api_node_storages(node_name: str):
    """Return storages for a given Proxmox node"""
    try:
        from ...services.vm_orchestrator import get_proxmox_client
        proxmox = get_proxmox_client()
        storages = proxmox.get_node_storages(node_name)
        # Normalize to simple list with id and status/enabled
        resp = []
        for s in storages or []:
            # Proxmox returns fields like 'storage', 'type', 'active'
            name = s.get('storage') or s.get('id') or s.get('name')
            if name:
                resp.append({
                    'name': name,
                    'type': s.get('type'),
                    'active': s.get('active', 1) in (1, True, '1')
                })
        return jsonify({'ok': True, 'node': node_name, 'storages': resp})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bp.route('/nodes/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_node():
    """Create or configure a node"""
    form = NodeConfigurationForm()
    
    if form.validate_on_submit():
        # Check if node already exists
        existing = NodeConfiguration.query.filter_by(node_name=form.node_name.data).first()
        if existing:
            flash(f'Node "{form.node_name.data}" already exists', 'danger')
        else:
            # Optional: verify node exists in Proxmox cluster
            try:
                from ...services.vm_orchestrator import get_proxmox_client
                proxmox = get_proxmox_client()
                cluster_nodes = proxmox.get_nodes()
                if form.node_name.data not in cluster_nodes:
                    flash(f'Warning: Node "{form.node_name.data}" not found in Proxmox cluster. It will be saved but unused until it exists.', 'warning')
            except Exception:
                # If Proxmox check fails, continue silently
                pass

            node = NodeConfiguration(
                node_name=form.node_name.data,
                max_vms=form.max_vms.data,
                storage_pools=form.storage_pools.data,
                priority=form.priority.data,
                is_active=form.is_active.data
            )
            
            try:
                db.session.add(node)
                db.session.commit()
                # Create storage configs if provided via picker
                selected = request.form.get('selected_storages', '').strip()
                if selected:
                    names = [x.strip() for x in selected.split(',') if x.strip()]
                    for name in names:
                        from ...models import NodeStorageConfig
                        sc = NodeStorageConfig(node_id=node.id, name=name, weight=1, max_vms=None, active=True)
                        db.session.add(sc)
                    # also mirror into CSV for convenience
                    node.storage_pools = ', '.join(names)
                    db.session.commit()
                flash(f'Node "{node.node_name}" configured successfully', 'success')
                return redirect(url_for('admin.nodes'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error configuring node: {str(e)}', 'danger')
    
    return render_template('admin/create_node.html', form=form)


@bp.route('/nodes/<int:node_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_node(node_id):
    """Edit node configuration"""
    node = NodeConfiguration.query.get_or_404(node_id)

    # Map model to form, preferring storage_pools
    form = NodeConfigurationForm(obj=node)
    if node.storage_pools:
        form.storage_pools.data = node.storage_pools
    else:
        form.storage_pools.data = node.storage_pool

    if form.validate_on_submit():
        node.node_name = form.node_name.data
        node.max_vms = form.max_vms.data
        node.storage_pools = form.storage_pools.data
        node.priority = form.priority.data
        node.is_active = form.is_active.data

        try:
            from ...models import NodeStorageConfig

            # ---- 1) Parse storage_pools CSV into a list of names ----
            csv_names = [
                x.strip()
                for x in (node.storage_pools or "").split(",")
                if x.strip()
            ]

            # ---- 2) Load all existing storage configs for this node ----
            existing_cfgs = NodeStorageConfig.query.filter_by(node_id=node.id).all()
            existing_by_name = {sc.name: sc for sc in existing_cfgs}

            # First mark everything inactive by default
            for sc in existing_cfgs:
                sc.active = False

            # ---- 3) Upsert configs for everything in storage_pools ----
            for name in csv_names:
                sc = existing_by_name.get(name)
                if not sc:
                    # New storage: create with default weight/max_vms
                    sc = NodeStorageConfig(
                        node_id=node.id,
                        name=name,
                        weight=1,
                        max_vms=None,
                        active=True,
                    )
                    db.session.add(sc)
                else:
                    # Existing storage: mark as active again
                    sc.active = True

            # Optional: keep weights / max_vms from the table if present
            # (ONLY if you want to preserve current behavior)
            # names = request.form.getlist("storage_name")
            # weights = request.form.getlist("storage_weight")
            # maxvms = request.form.getlist("storage_max_vms")
            # for i, n in enumerate(names):
            #     n = (n or "").strip()
            #     if not n:
            #         continue
            #     sc = existing_by_name.get(n)
            #     if not sc:
            #         continue
            #     try:
            #         sc.weight = (
            #             int(weights[i])
            #             if weights and i < len(weights) and weights[i].strip() != ""
            #             else 1
            #         )
            #     except Exception:
            #         sc.weight = 1
            #     try:
            #         mv = maxvms[i].strip() if maxvms and i < len(maxvms) else ""
            #         sc.max_vms = int(mv) if mv != "" else None
            #     except Exception:
            #         sc.max_vms = None

            db.session.commit()
            flash(f'Node "{node.node_name}" updated successfully', "success")
            return redirect(url_for("admin.nodes"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating node: {str(e)}", "danger")

    # GET or failed validation: just render the template
    return render_template("admin/edit_node.html", form=form, node=node)

    """Edit node configuration"""
    node = NodeConfiguration.query.get_or_404(node_id)

    # Map model to form, preferring storage_pools
    form = NodeConfigurationForm(obj=node)
    if node.storage_pools:
        form.storage_pools.data = node.storage_pools
    else:
        form.storage_pools.data = node.storage_pool

    if form.validate_on_submit():
        node.node_name = form.node_name.data
        node.max_vms = form.max_vms.data
        node.storage_pools = form.storage_pools.data
        node.priority = form.priority.data
        node.is_active = form.is_active.data

        try:
            from ...models import NodeStorageConfig

            # ---- 1) Update / create storages from the table rows ----
            names = request.form.getlist("storage_name")
            weights = request.form.getlist("storage_weight")
            maxvms = request.form.getlist("storage_max_vms")
            form_map = request.form.to_dict(flat=False)
            active_flags = form_map.get("storage_active", [])

            seen_names = []

            for i, n in enumerate(names):
                n = (n or "").strip()
                if not n:
                    continue

                seen_names.append(n)

                sc = NodeStorageConfig.query.filter_by(
                    node_id=node.id, name=n
                ).first()
                if not sc:
                    sc = NodeStorageConfig(node_id=node.id, name=n)
                    db.session.add(sc)

                # weight
                try:
                    sc.weight = (
                        int(weights[i])
                        if weights and i < len(weights) and weights[i].strip() != ""
                        else 1
                    )
                except Exception:
                    sc.weight = 1

                # max_vms
                try:
                    mv = maxvms[i].strip() if maxvms and i < len(maxvms) else ""
                    sc.max_vms = int(mv) if mv != "" else None
                except Exception:
                    sc.max_vms = None

                # Active flag: checkbox presence by index
                sc.active = i < len(active_flags)

            # ---- 2) Any storages not in the form rows get marked inactive ----
            all_cfgs = NodeStorageConfig.query.filter_by(node_id=node.id).all()
            for sc in all_cfgs:
                if sc.name not in seen_names:
                    sc.active = False

            db.session.commit()
            flash(f'Node "{node.node_name}" updated successfully', "success")
            return redirect(url_for("admin.nodes"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating node: {str(e)}", "danger")

    # GET or failed validation: just render the template
    return render_template("admin/edit_node.html", form=form, node=node)


@bp.route('/templates/<int:template_id>/replicate', methods=['POST'])
@login_required
@admin_required
def replicate_template(template_id):
    """Manually trigger template replication to all nodes"""
    template = VMTemplate.query.get_or_404(template_id)
    
    try:
        from ...services.vm_orchestrator import replicate_template_to_all_nodes
        replicate_template_to_all_nodes(template_id)
        flash(f'Template "{template.name}" replication started', 'success')
    except Exception as e:
        flash(f'Error starting replication: {str(e)}', 'danger')
    
    return redirect(url_for('admin.dashboard'))


@bp.route('/settings/multi-node', methods=['GET', 'POST'])
@login_required
@admin_required
def multi_node_settings():
    """Multi-node system settings"""
    form = MultiNodeSettingsForm()
    
    # Load current settings from config/environment
    if request.method == 'GET':
        from flask import current_app
        form.max_vms_per_node.data = current_app.config.get('MAX_VMS_PER_NODE', 12)
        form.use_linked_clones.data = current_app.config.get('USE_LINKED_CLONES', True)
        form.auto_replicate_templates.data = current_app.config.get('AUTO_REPLICATE_TEMPLATES', True)
        form.node_selection_strategy.data = current_app.config.get('NODE_SELECTION_STRATEGY', 'least_vms')
    
    if form.validate_on_submit():
        # Update all existing node configurations
        try:
            NodeConfiguration.query.update({
                NodeConfiguration.max_vms: form.max_vms_per_node.data
            })
            db.session.commit()
            
            flash('Multi-node settings updated successfully. Note: Some settings require application restart.', 'success')
            flash('Consider updating your .env file with the new settings for persistence.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating settings: {str(e)}', 'danger')
    
    return render_template('admin/multi_node_settings.html', form=form)
