"""Replace template replication with per-node VMID mappings

Revision ID: d1f2g3h4i5j6
Revises: 7ab9b15165d5
Create Date: 2025-12-05 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f2g3h4i5j6'
down_revision = '7ab9b15165d5'
branch_labels = None
depends_on = None


def upgrade():
    # Create new table for template-node mappings
    op.create_table('template_node_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('template_id', sa.Integer(), nullable=False),
    sa.Column('proxmox_node', sa.String(length=120), nullable=False),
    sa.Column('proxmox_template_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['template_id'], ['vm_templates.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('template_id', 'proxmox_node', name='uq_template_node')
    )
    
    # Migrate existing data from old structure to new structure
    # For each template, create mappings from existing data
    connection = op.get_bind()
    
    # Get all templates with their primary node and VMID
    templates = connection.execute(
        sa.text("""
            SELECT id, proxmox_template_id, proxmox_node 
            FROM vm_templates
        """)
    ).fetchall()
    
    for template_id, vmid, node in templates:
        # Insert the primary node mapping
        try:
            connection.execute(
                sa.text("""
                    INSERT INTO template_node_mappings 
                    (template_id, proxmox_node, proxmox_template_id, created_at, updated_at)
                    VALUES (:template_id, :node, :vmid, datetime('now'), datetime('now'))
                """),
                {'template_id': template_id, 'node': node, 'vmid': vmid}
            )
        except Exception:
            # Ignore duplicates
            pass
    
    # Remove old columns from vm_templates and add updated_at if missing
    with op.batch_alter_table('vm_templates', schema=None) as batch_op:
        batch_op.drop_column('proxmox_template_id')
        batch_op.drop_column('proxmox_node')
        batch_op.drop_column('replicate_to_all_nodes')
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade():
    # Add back old columns
    with op.batch_alter_table('vm_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proxmox_template_id', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('proxmox_node', sa.String(length=120), nullable=False))
        batch_op.add_column(sa.Column('replicate_to_all_nodes', sa.Boolean(), nullable=True))
    
    # Migrate data back from template_node_mappings
    connection = op.get_bind()
    mappings = connection.execute(
        sa.text("""
            SELECT DISTINCT template_id, proxmox_node, proxmox_template_id
            FROM template_node_mappings
            ORDER BY template_id, created_at
        """)
    ).fetchall()
    
    # For each template, use the first mapping as the primary
    processed_templates = set()
    for template_id, node, vmid in mappings:
        if template_id not in processed_templates:
            connection.execute(
                sa.text("""
                    UPDATE vm_templates 
                    SET proxmox_node = :node, proxmox_template_id = :vmid, replicate_to_all_nodes = 1
                    WHERE id = :template_id
                """),
                {'node': node, 'vmid': vmid, 'template_id': template_id}
            )
            processed_templates.add(template_id)
    
    # Drop new table
    op.drop_table('template_node_mappings')
