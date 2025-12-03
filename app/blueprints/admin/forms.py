from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, IntegerField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange


class CreateTeacherForm(FlaskForm):
    """Form to create a new teacher account"""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=4)])
    submit = SubmitField('Create Teacher')


class CreateVMTemplateForm(FlaskForm):
    """Form to register a VM template"""
    name = StringField('Template Name', validators=[DataRequired(), Length(max=120)])
    proxmox_template_id = IntegerField('Proxmox Template ID', validators=[DataRequired(), NumberRange(min=100)])
    proxmox_node = StringField('Proxmox Node', validators=[DataRequired(), Length(max=120)])
    description = TextAreaField('Description')
    memory = IntegerField('Memory (MB)', validators=[DataRequired(), NumberRange(min=512)], default=2048)
    cores = IntegerField('CPU Cores', validators=[DataRequired(), NumberRange(min=1)], default=2)
    is_active = BooleanField('Active', default=True)
    replicate_to_all_nodes = BooleanField('Auto-replicate to all nodes', default=True)
    submit = SubmitField('Create Template')


class NodeConfigurationForm(FlaskForm):
    """Form to configure a Proxmox node"""
    node_name = StringField('Node Name', validators=[DataRequired(), Length(max=120)])
    max_vms = IntegerField('Max VMs', validators=[DataRequired(), NumberRange(min=1, max=100)], default=12)
    storage_pools = StringField('Storage Pools (comma-separated)', validators=[DataRequired(), Length(max=500)], default='local-lvm')
    priority = IntegerField('Priority', validators=[DataRequired(), NumberRange(min=1, max=10)], default=1)
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Configuration')


class MultiNodeSettingsForm(FlaskForm):
    """Form for multi-node system settings"""
    max_vms_per_node = IntegerField('Max VMs per Node', validators=[DataRequired(), NumberRange(min=1, max=100)], default=12)
    use_linked_clones = BooleanField('Use Linked Clones', default=True)
    auto_replicate_templates = BooleanField('Auto-replicate Templates', default=True)
    node_selection_strategy = SelectField('Node Selection Strategy', 
        choices=[('least_vms', 'Least VMs'), ('round_robin', 'Round Robin'), 
                ('priority', 'Priority'), ('random', 'Random')], 
        default='least_vms')
    submit = SubmitField('Update Settings')
