from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length


class ImportClassForm(FlaskForm):
    """Form to import/create a class"""
    class_name = StringField('Class Name', validators=[DataRequired(), Length(max=120)])
    students_text = TextAreaField('Student Names (one per line)', validators=[DataRequired()])
    submit = SubmitField('Import Class')


class AddStudentForm(FlaskForm):
    """Form to add a single student to a class"""
    student_name = StringField('Student Name', validators=[DataRequired(), Length(max=120)])
    submit = SubmitField('Add Student')


class DeployVMForm(FlaskForm):
    """Form to deploy VM for a student"""
    template_id = SelectField('VM Template', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Deploy VM')
