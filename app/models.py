from app import db
from flask_login import UserMixin
from datetime import datetime


class Rol(db.Model):
    __tablename__ = 'rol'
    id          = db.Column(db.Integer, primary_key=True)
    nombre      = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.String(200))


class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuario'
    id                = db.Column(db.Integer, primary_key=True)
    nombre            = db.Column(db.String(100), nullable=False)
    email             = db.Column(db.String(100), unique=True, nullable=False)
    password          = db.Column(db.String(200), nullable=False)
    rol_id            = db.Column(db.Integer, db.ForeignKey('rol.id'), nullable=False)
    activo            = db.Column(db.Boolean, default=True)
    password_cambiada = db.Column(db.Boolean, default=False)
    intentos_fallidos = db.Column(db.Integer, default=0)
    bloqueado_hasta   = db.Column(db.DateTime, nullable=True)
    ultimo_acceso     = db.Column(db.DateTime, nullable=True)
    ip_ultimo_acceso  = db.Column(db.String(45), nullable=True)
    rol = db.relationship('Rol', backref='usuarios')

    def esta_bloqueado(self):
        if self.bloqueado_hasta and datetime.utcnow() < self.bloqueado_hasta:
            return True
        return False

    def registrar_intento_fallido(self):
        self.intentos_fallidos = (self.intentos_fallidos or 0) + 1
        if self.intentos_fallidos >= 5:
            from datetime import timedelta
            self.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=30)
            self.intentos_fallidos = 0

    def registrar_acceso_exitoso(self, ip=None):
        self.intentos_fallidos = 0
        self.bloqueado_hasta   = None
        self.ultimo_acceso     = datetime.utcnow()
        self.ip_ultimo_acceso  = ip


class Paciente(db.Model):
    __tablename__ = 'paciente'
    id                  = db.Column(db.Integer, primary_key=True)
    nombre              = db.Column(db.String(100), nullable=False)
    identificacion      = db.Column(db.String(20), unique=True, nullable=False)
    tipo_identificacion = db.Column(db.String(20), default='CC')
    telefono            = db.Column(db.String(15))
    email               = db.Column(db.String(100))
    direccion           = db.Column(db.String(200))
    fecha_nacimiento    = db.Column(db.Date)
    sexo                = db.Column(db.String(20))
    activo              = db.Column(db.Boolean, default=True)
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por_id       = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    creado_por = db.relationship('Usuario', foreign_keys=[creado_por_id])


class Especialidad(db.Model):
    __tablename__ = 'especialidad'
    id     = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    activo = db.Column(db.Boolean, default=True)


class HistoriaClinica(db.Model):
    __tablename__ = 'historia_clinica'
    id                   = db.Column(db.Integer, primary_key=True)
    paciente_id          = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    fecha_creacion       = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    motivo_consulta      = db.Column(db.Text, nullable=True)
    antecedentes         = db.Column(db.Text, nullable=True)
    ultima_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por_id   = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    bloqueado_por_id     = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    bloqueado_en         = db.Column(db.DateTime, nullable=True)
    paciente        = db.relationship('Paciente', backref='historias')
    actualizado_por = db.relationship('Usuario', foreign_keys=[actualizado_por_id])
    bloqueado_por   = db.relationship('Usuario', foreign_keys=[bloqueado_por_id])

    def esta_bloqueada(self):
        if self.bloqueado_por_id and self.bloqueado_en:
            from datetime import timedelta
            if datetime.utcnow() < self.bloqueado_en + timedelta(minutes=30):
                return True
            self.bloqueado_por_id = None
            self.bloqueado_en     = None
            db.session.commit()
        return False

    def bloquear(self, usuario_id):
        self.bloqueado_por_id = usuario_id
        self.bloqueado_en     = datetime.utcnow()

    def liberar(self):
        self.bloqueado_por_id = None
        self.bloqueado_en     = None


class HistoriaEntrada(db.Model):
    __tablename__ = 'historia_entrada'
    id          = db.Column(db.Integer, primary_key=True)
    historia_id = db.Column(db.Integer, db.ForeignKey('historia_clinica.id'), nullable=False)
    autor_id    = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    contenido   = db.Column(db.Text, nullable=False)
    tipo_entrada= db.Column(db.String(30), default='Consulta')
    fecha       = db.Column(db.DateTime, default=datetime.utcnow)
    historia = db.relationship('HistoriaClinica', backref='entradas')
    autor    = db.relationship('Usuario', foreign_keys=[autor_id])


class HistoriaVersion(db.Model):
    __tablename__ = 'historia_version'
    id                 = db.Column(db.Integer, primary_key=True)
    historia_id        = db.Column(db.Integer, db.ForeignKey('historia_clinica.id'), nullable=False)
    contenido          = db.Column(db.Text, nullable=False)
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha              = db.Column(db.DateTime, default=datetime.utcnow)
    historia = db.relationship('HistoriaClinica', backref='versiones')
    autor    = db.relationship('Usuario', foreign_keys=[actualizado_por_id])


class Cita(db.Model):
    __tablename__ = 'cita'
    id              = db.Column(db.Integer, primary_key=True)
    paciente_id     = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    medico_id       = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    especialidad_id = db.Column(db.Integer, db.ForeignKey('especialidad.id'), nullable=False)
    fecha           = db.Column(db.DateTime, nullable=False)
    estado          = db.Column(db.String(20), default='Pendiente')
    motivo_consulta = db.Column(db.Text)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por_id   = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    paciente     = db.relationship('Paciente', backref='citas')
    medico       = db.relationship('Usuario', foreign_keys=[medico_id])
    especialidad = db.relationship('Especialidad', backref='citas')
    creado_por   = db.relationship('Usuario', foreign_keys=[creado_por_id])


class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    id            = db.Column(db.BigInteger, primary_key=True)
    usuario_id    = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    usuario_email = db.Column(db.String(100))
    accion        = db.Column(db.String(50), nullable=False)
    modulo        = db.Column(db.String(50))
    descripcion   = db.Column(db.Text)
    ip_origen     = db.Column(db.String(45))
    fecha_hora    = db.Column(db.DateTime, default=datetime.utcnow)
    exitoso       = db.Column(db.Boolean, default=True)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])


class BackupRegistro(db.Model):
    __tablename__ = 'backup_registro'
    id                   = db.Column(db.Integer, primary_key=True)
    tipo                 = db.Column(db.String(20), default='manual')
    solicitado_por_id    = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    archivo_nombre       = db.Column(db.String(200))
    archivo_url          = db.Column(db.String(500))
    archivo_datos        = db.Column(db.LargeBinary, nullable=True)
    tamano_bytes         = db.Column(db.BigInteger)
    estado               = db.Column(db.String(20), default='generando')
    error_mensaje        = db.Column(db.Text)
    creado_en            = db.Column(db.DateTime, default=datetime.utcnow)
    notificacion_enviada = db.Column(db.Boolean, default=False)
    solicitado_por = db.relationship('Usuario', foreign_keys=[solicitado_por_id])


class VersionSistema(db.Model):
    __tablename__ = 'version_sistema'
    id                       = db.Column(db.Integer, primary_key=True)
    version                  = db.Column(db.String(20), nullable=False)
    descripcion              = db.Column(db.Text)
    es_critica               = db.Column(db.Boolean, default=False)
    publicado_en             = db.Column(db.DateTime, default=datetime.utcnow)
    minima_version_requerida = db.Column(db.String(20))


class CodigoVerificacion(db.Model):
    """Códigos temporales para 2FA y validación de correos."""
    __tablename__ = 'codigo_verificacion'
    id          = db.Column(db.Integer, primary_key=True)
    email       = db.Column(db.String(100), nullable=False)
    codigo      = db.Column(db.String(10), nullable=False)
    tipo        = db.Column(db.String(20), nullable=False)  # '2fa' o 'validar_correo'
    usado       = db.Column(db.Boolean, default=False)
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    expira_en   = db.Column(db.DateTime, nullable=False)

    def esta_vigente(self):
        return not self.usado and datetime.utcnow() < self.expira_en


class ConfiguracionSistema(db.Model):
    """Configuraciones globales del sistema."""
    __tablename__ = 'configuracion_sistema'
    id    = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(50), unique=True, nullable=False)
    valor = db.Column(db.String(200), nullable=False)

    @staticmethod
    def obtener(clave, default='true'):
        from app import db
        config = ConfiguracionSistema.query.filter_by(clave=clave).first()
        return config.valor if config else default

    @staticmethod
    def establecer(clave, valor):
        from app import db
        config = ConfiguracionSistema.query.filter_by(clave=clave).first()
        if config:
            config.valor = valor
        else:
            db.session.add(ConfiguracionSistema(clave=clave, valor=valor))
        db.session.commit()


class CorreoBackup(db.Model):
    """Correos registrados para recibir backups (máximo 5)."""
    __tablename__ = 'correo_backup'
    id          = db.Column(db.Integer, primary_key=True)
    email       = db.Column(db.String(120), unique=True, nullable=False)
    verificado  = db.Column(db.Boolean, default=False)
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)

# ─── AGREGAR AL FINAL DE models.py ──────────────────────────────────────────

class CampoPersonalizado(db.Model):
    """Define un campo extra que el admin crea para todos los pacientes."""
    __tablename__ = 'campo_personalizado'
    id          = db.Column(db.Integer, primary_key=True)
    nombre      = db.Column(db.String(100), nullable=False)
    clave       = db.Column(db.String(50),  nullable=False, unique=True)
    tipo        = db.Column(db.String(20),  nullable=False, default='texto')
    # tipos: 'texto' | 'texto_largo' | 'fecha' | 'numero' | 'seleccion'
    opciones    = db.Column(db.String(500), nullable=True)   # Para seleccion: "A,B,AB,O"
    obligatorio = db.Column(db.Boolean, default=False)
    orden       = db.Column(db.Integer, default=0)
    activo      = db.Column(db.Boolean, default=True)
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)


class ValorCampoPersonalizado(db.Model):
    """Guarda el valor de un campo para un paciente especifico."""
    __tablename__ = 'valor_campo_personalizado'
    id          = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    campo_id    = db.Column(db.Integer, db.ForeignKey('campo_personalizado.id'), nullable=False)
    valor       = db.Column(db.Text, nullable=True)
    paciente = db.relationship('Paciente', backref='campos_extra')
    campo    = db.relationship('CampoPersonalizado', backref='valores')
