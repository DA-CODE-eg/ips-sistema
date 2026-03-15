from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, DateField, DateTimeLocalField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError


class LoginForm(FlaskForm):
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Iniciar sesión')


class CambiarPasswordForm(FlaskForm):
    password_actual = PasswordField('Contraseña actual', validators=[])
    password_nueva = PasswordField('Nueva contraseña', validators=[DataRequired(), Length(min=6)])
    password_confirmacion = PasswordField('Confirmar nueva contraseña', 
                                         validators=[DataRequired(), EqualTo('password_nueva', message='Las contraseñas deben coincidir')])
    submit = SubmitField('Cambiar contraseña')
    
    def __init__(self, require_current=True, *args, **kwargs):
        super(CambiarPasswordForm, self).__init__(*args, **kwargs)
        if require_current:
            self.password_actual.validators = [DataRequired()]
        else:
            self.password_actual.validators = []


class RolForm(FlaskForm):
    nombre = StringField('Nombre del rol', validators=[DataRequired(), Length(max=50)])
    descripcion = StringField('Descripción', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Guardar')


class UsuarioForm(FlaskForm):
    nombre = StringField('Nombre completo', validators=[DataRequired(), Length(max=100)])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email(), Length(max=120)])
    rol_id = SelectField('Rol', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Guardar')


class PacienteForm(FlaskForm):
    nombre = StringField('Nombre completo', validators=[DataRequired(), Length(max=100)])
    identificacion = StringField('Identificación', validators=[DataRequired(), Length(max=20)])
    sexo = StringField('Sexo', validators=[DataRequired(), Length(max=20)])
    fecha_nacimiento = DateField('Fecha de nacimiento', validators=[DataRequired()])
    telefono = StringField('Teléfono', validators=[Optional(), Length(max=20)])
    email = StringField('Correo electrónico', validators=[Optional(), Email(), Length(max=120)])
    direccion = TextAreaField('Dirección', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Guardar')


class EspecialidadForm(FlaskForm):
    nombre = StringField('Nombre de la especialidad', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Crear Especialidad')


class CitaForm(FlaskForm):
    paciente_id = SelectField('Paciente', coerce=int, validators=[DataRequired()])
    medico_id = SelectField('Médico', coerce=int, validators=[DataRequired()])
    especialidad_id = SelectField('Especialidad', coerce=int, validators=[DataRequired()])
    fecha = DateTimeLocalField('Fecha y hora', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    submit = SubmitField('Agendar Cita')


class HistoriaClinicaForm(FlaskForm):
    contenido = TextAreaField('Contenido de la historia clínica', validators=[DataRequired()])
    submit = SubmitField('Guardar')

class CodigoVerificacionForm(FlaskForm):
    codigo = StringField('Código de verificación', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Verificar')


class ValidarCorreoForm(FlaskForm):
    codigo = StringField('Código enviado al correo', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Confirmar correo')
