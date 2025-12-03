from .extensions import db
from flask_login import UserMixin
from datetime import datetime


class User(UserMixin, db.Model):
    """User model for IT admins and teachers"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='teacher')  # 'admin' or 'teacher'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    # Account lockout / brute-force protection
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    classrooms = db.relationship('Classroom', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.email} ({self.role})>'
    
    def is_admin(self):
        return self.role == 'admin'


class Classroom(db.Model):
    """Classroom/Class model"""
    __tablename__ = 'classrooms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    students = db.relationship('Student', backref='classroom', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Classroom {self.name}>'


class Student(db.Model):
    """Student model"""
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=False)
    username = db.Column(db.String(120), unique=True, index=True)  # Login username
    password_hash = db.Column(db.String(256))  # Login password
    # Encrypted initial password stored at rest. Decrypted only when displayed to authorized users.
    initial_password_enc = db.Column(db.LargeBinary)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Account lockout fields for students
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    vms = db.relationship('VirtualMachine', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password: str):
        """Set password hash"""
        from .security import hash_password
        self.password_hash = hash_password(password)

    def set_initial_password(self, password: str):
        """Encrypt and store the initial password for teacher display only."""
        from .security import encrypt_secret
        token = encrypt_secret(password)
        self.initial_password_enc = token

    def get_initial_password(self) -> str:
        """Decrypt the stored initial password or return None."""
        from .security import decrypt_secret
        if not self.initial_password_enc:
            return None
        try:
            return decrypt_secret(self.initial_password_enc)
        except Exception:
            return None
    
    def check_password(self, password: str) -> bool:
        """Check password"""
        from .security import verify_password
        if not self.password_hash:
            return False
        return verify_password(self.password_hash, password)
    
    def __repr__(self):
        return f'<Student {self.name}>'


class VirtualMachine(db.Model):
    """Virtual Machine model"""
    __tablename__ = 'virtual_machines'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Proxmox details
    proxmox_vmid = db.Column(db.Integer, unique=True)
    proxmox_node = db.Column(db.String(120))
    template_name = db.Column(db.String(120))
    
    
    # Proxmox console URL (for isolated VMs)
    console_url = db.Column(db.String(512))
    
    # Status
    status = db.Column(db.String(20), default='creating')  # creating, running, stopped, error
    ip_address = db.Column(db.String(45))
    storage = db.Column(db.String(120))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<VM {self.proxmox_vmid} for Student {self.student_id}>'


class VMTemplate(db.Model):
    """VM Template definitions"""
    __tablename__ = 'vm_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    proxmox_template_id = db.Column(db.Integer, nullable=False)
    proxmox_node = db.Column(db.String(120), nullable=False)  # Primary node where template was created
    description = db.Column(db.Text)
    memory = db.Column(db.Integer, default=2048)
    cores = db.Column(db.Integer, default=2)
    is_active = db.Column(db.Boolean, default=True)
    replicate_to_all_nodes = db.Column(db.Boolean, default=True)  # Auto-replicate to all nodes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    replicas = db.relationship('VMTemplateReplica', backref='template', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_template_id_for_node(self, node_name: str) -> int:
        """Get the template ID to use for a specific node"""
        if self.proxmox_node == node_name:
            return self.proxmox_template_id
        
        # Look for a replica on the target node
        replica = self.replicas.filter_by(target_node=node_name).first()
        if replica and replica.is_ready:
            return replica.template_id
        
        # Fallback to original if no replica found
        return self.proxmox_template_id
    
    def __repr__(self):
        return f'<VMTemplate {self.name}>'


class VMTemplateReplica(db.Model):
    """Tracks template replicas across nodes"""
    __tablename__ = 'vm_template_replicas'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('vm_templates.id'), nullable=False)
    target_node = db.Column(db.String(120), nullable=False)
    proxmox_template_id = db.Column(db.Integer, nullable=False)  # Template ID on target node
    is_ready = db.Column(db.Boolean, default=False)  # Whether replication is complete
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint: one replica per template per node
    __table_args__ = (db.UniqueConstraint('template_id', 'target_node'),)
    
    def __repr__(self):
        return f'<VMTemplateReplica {self.template_id} -> {self.target_node}>'


class NodeConfiguration(db.Model):
    """Configuration settings for Proxmox nodes"""
    __tablename__ = 'node_configurations'
    
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(120), nullable=False, unique=True)
    max_vms = db.Column(db.Integer, default=12)
    is_active = db.Column(db.Boolean, default=True)
    # Backward-compatible single storage field; prefer storage_pools when set
    storage_pool = db.Column(db.String(120), default='local-lvm')
    # Comma-separated list of storage pools for this node
    storage_pools = db.Column(db.Text, nullable=True)
    # Round-robin index for distributing VMs across storages
    storage_rr_index = db.Column(db.Integer, default=0, nullable=False)
    priority = db.Column(db.Integer, default=1)  # Higher priority nodes preferred for deployment
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    storages = db.relationship('NodeStorageConfig', backref='node', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_current_vm_count(self) -> int:
        """Get current number of VMs on this node"""
        return VirtualMachine.query.filter_by(proxmox_node=self.node_name).count()
    
    def is_available_for_deployment(self) -> bool:
        """Check if this node can accept new VM deployments"""
        return self.is_active and self.get_current_vm_count() < self.max_vms

    def get_storages_list(self):
        """Return list of configured storage pools for this node."""
        # Prefer structured storages if present
        structured = [s.name for s in self.storages.filter_by(active=True).all()]
        if structured:
            return structured
        if self.storage_pools and self.storage_pools.strip():
            return [s.strip() for s in self.storage_pools.split(',') if s.strip()]
        if self.storage_pool:
            return [self.storage_pool]
        return []

    def get_next_storage(self) -> str:
        """Return next storage via round-robin across storages. Persist index."""
        storages = self.get_storages_list()
        if not storages:
            return None
        idx = self.storage_rr_index % len(storages)
        storage = storages[idx]
        # advance index for next call
        self.storage_rr_index = (self.storage_rr_index + 1) % (len(storages) if len(storages) > 0 else 1)
        try:
            db.session.add(self)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return storage
    
    def __repr__(self):
        return f'<NodeConfiguration {self.node_name}>'


class NodeStorageConfig(db.Model):
    """Per-node storage configuration with weights and max VMs"""
    __tablename__ = 'node_storage_configs'
    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey('node_configurations.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    weight = db.Column(db.Integer, default=1, nullable=False)
    max_vms = db.Column(db.Integer, nullable=True)  # Null = unlimited
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('node_id', 'name', name='uq_node_storage'),)
    
    def __repr__(self):
        return f'<NodeStorageConfig node={self.node_id} {self.name} w={self.weight} max={self.max_vms}>'
