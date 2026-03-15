from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import os
import threading
import atexit

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

_scheduler = None


def _reprogramar_zip():
    """Llamado desde routes cuando el admin cambia config ZIP."""
    global _scheduler
    if not _scheduler or not _scheduler.running:
        return
    try:
        from app.models import ConfiguracionSistema
        from apscheduler.triggers.cron import CronTrigger

        activo     = ConfiguracionSistema.obtener('zip_activo', 'true') == 'true'
        frecuencia = ConfiguracionSistema.obtener('zip_frecuencia', '2meses')
        hora_str   = ConfiguracionSistema.obtener('zip_hora', '08:00')
        hora_n     = int(hora_str.split(':')[0])
        min_n      = int(hora_str.split(':')[1])

        if not activo:
            try:
                _scheduler.remove_job('backup_zip_correo')
                print("ZIP backup desactivado")
            except:
                pass
            return

        if frecuencia == 'hora':
            trigger = CronTrigger(minute=0)
        elif frecuencia == 'dia':
            trigger = CronTrigger(hour=hora_n, minute=min_n)
        elif frecuencia == 'semana':
            trigger = CronTrigger(day_of_week='mon', hour=hora_n, minute=min_n)
        elif frecuencia == 'mes':
            trigger = CronTrigger(day=1, hour=hora_n, minute=min_n)
        else:
            trigger = CronTrigger(month='1,3,5,7,9,11', day=1, hour=hora_n, minute=min_n)

        if _scheduler.get_job('backup_zip_correo'):
            _scheduler.reschedule_job('backup_zip_correo', trigger=trigger)
            print(f"ZIP reprogramado: {frecuencia} a las {hora_str}")
        else:
            print("ZIP job no existe aun en scheduler")
    except Exception as e:
        print(f"Error reprogramando ZIP: {e}")


def _iniciar_scheduler(app):
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        if _scheduler and _scheduler.running:
            return

        _scheduler = BackgroundScheduler(daemon=True)

        # ── ZIP AL CORREO — configurable ─────────────────────────
        def ejecutar_backup_zip():
            with app.app_context():
                try:
                    from app.models import ConfiguracionSistema
                    if ConfiguracionSistema.obtener('zip_activo', 'true') != 'true':
                        return
                    print("⏰ Backup ZIP al correo iniciando...")
                    from app.backup_service import generar_backup
                    ok, registro_id, error = generar_backup(tipo='automatico')
                    if ok:
                        print(f"✅ Backup ZIP exitoso (ID: {registro_id})")
                    else:
                        print(f"❌ Backup ZIP falló: {error}")
                except Exception as e:
                    print(f"❌ Error ZIP: {e}")

        # ── MONITOREO NEON — diario 8am ──────────────────────────
        def monitorear_neon():
            with app.app_context():
                try:
                    from app.models import CorreoBackup, ConfiguracionSistema
                    from app.correo_service import enviar_alerta_neon

                    resultado = db.session.execute(
                        db.text("SELECT pg_database_size(current_database())")
                    ).scalar()
                    if not resultado:
                        return

                    mb_usado   = resultado / (1024 * 1024)
                    mb_limite  = 512
                    porcentaje = (mb_usado / mb_limite) * 100

                    print(f"📊 Neon: {mb_usado:.1f} MB / {mb_limite} MB ({porcentaje:.1f}%)")
                    ConfiguracionSistema.establecer('neon_mb_usado', str(round(mb_usado, 2)))
                    ConfiguracionSistema.establecer('neon_porcentaje', str(round(porcentaje, 1)))

                    alerta = None
                    if porcentaje >= 95:
                        alerta = 'critico'
                    elif porcentaje >= 85:
                        alerta = 'peligro'
                    elif porcentaje >= 70:
                        alerta = 'advertencia'

                    if alerta:
                        for c in CorreoBackup.query.filter_by(verificado=True).all():
                            try:
                                enviar_alerta_neon(c.email, mb_usado, mb_limite, porcentaje, alerta)
                            except Exception as e:
                                print(f"❌ Error alerta: {e}")
                except Exception as e:
                    print(f"⚠️ Error Neon: {e}")

        # ── DRIVE helpers ─────────────────────────────────────────
        def _volcar_csv(campos, modelo):
            import io, csv
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(campos)
            for r in modelo.query.all():
                w.writerow([str(getattr(r, c, '') or '') for c in campos])
            return buf.getvalue().encode('utf-8')

        def _generar_datos_csv():
            from app.models import Paciente, Cita, Auditoria, HistoriaEntrada, Usuario, Especialidad
            return {
                'pacientes.csv':          _volcar_csv(['id','nombre','identificacion','tipo_identificacion','telefono','email','direccion','fecha_nacimiento','sexo','activo','creado_en'], Paciente),
                'citas.csv':              _volcar_csv(['id','paciente_id','medico_id','especialidad_id','fecha','estado','creado_en'], Cita),
                'auditoria.csv':          _volcar_csv(['id','usuario_email','accion','modulo','descripcion','ip_origen','fecha_hora','exitoso'], Auditoria),
                'historias_clinicas.csv': _volcar_csv(['id','historia_id','autor_id','tipo_entrada','contenido','fecha'], HistoriaEntrada),
                'usuarios.csv':           _volcar_csv(['id','nombre','email','rol_id','activo','creado_en'], Usuario),
                'especialidades.csv':     _volcar_csv(['id','nombre','activo'], Especialidad),
            }

        def _compartir_drive():
            from app.drive_service import compartir_carpeta_con_todos
            from app.models import CorreoBackup
            correos = [c.email for c in CorreoBackup.query.filter_by(verificado=True).all()]
            compartir_carpeta_con_todos(correos)

        # ── DRIVE CSV — cada 5 minutos ────────────────────────────
        def sincronizar_drive_csv():
            with app.app_context():
                try:
                    from app.drive_service import sincronizar_con_drive
                    ok, error = sincronizar_con_drive(_generar_datos_csv(), {}, {})
                    if ok:
                        _compartir_drive()
                        print("☁️  Drive CSVs actualizados")
                    else:
                        print(f"Drive CSV falló: {error}")
                except Exception as e:
                    print(f"Drive CSV error: {e}")

        # ── DRIVE COMPLETO — cada hora a los :30 ─────────────────
        def sincronizar_drive_completo():
            with app.app_context():
                try:
                    import datetime
                    from flask import render_template
                    from weasyprint import HTML
                    from app.drive_service import sincronizar_con_drive
                    from app.models import Paciente, Cita, Especialidad, HistoriaClinica, HistoriaEntrada

                    datos_csv     = _generar_datos_csv()
                    reportes_pdf  = {}
                    historias_pdf = {}
                    fecha_gen = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')

                    for tpl, nombre, ctx in [
                        ('reporte/pacientes_pdf.html',     'reporte_pacientes.pdf',     {'pacientes': Paciente.query.all()}),
                        ('reporte/citas_pdf.html',         'reporte_citas.pdf',         {'citas': Cita.query.order_by(Cita.fecha.desc()).all()}),
                        ('reporte/especialidades_pdf.html','reporte_especialidades.pdf',{'especialidades': Especialidad.query.all()}),
                    ]:
                        try:
                            ctx['fecha_generacion'] = fecha_gen
                            pdf = HTML(string=render_template(tpl, **ctx)).write_pdf()
                            if pdf:
                                reportes_pdf[nombre] = pdf
                        except Exception as e:
                            print(f"Reporte {nombre} falló: {e}")

                    for paciente in Paciente.query.filter_by(activo=True).all():
                        historia = HistoriaClinica.query.filter_by(paciente_id=paciente.id).first()
                        if not historia:
                            continue
                        entradas = HistoriaEntrada.query.filter_by(historia_id=historia.id).order_by(HistoriaEntrada.fecha.desc()).all()
                        if not entradas:
                            continue
                        edad = None
                        if paciente.fecha_nacimiento:
                            today = datetime.date.today()
                            edad  = today.year - paciente.fecha_nacimiento.year
                            if today < paciente.fecha_nacimiento.replace(year=today.year):
                                edad -= 1
                        try:
                            pdf = HTML(string=render_template(
                                'historia/historia_clinica_pdf.html',
                                paciente=paciente, historia=historia, entradas=entradas,
                                fecha_generacion=fecha_gen, edad=edad, solo_recientes=False
                            )).write_pdf()
                            if pdf:
                                historias_pdf[f"{paciente.nombre.replace(' ','_')}_{paciente.identificacion}.pdf"] = pdf
                        except Exception as e:
                            print(f"Historia {paciente.nombre} falló: {e}")

                    ok, error = sincronizar_con_drive(datos_csv, reportes_pdf, historias_pdf)
                    if ok:
                        _compartir_drive()
                        print("☁️  Drive completo sincronizado (CSVs + PDFs)")
                    else:
                        print(f"Drive completo falló: {error}")
                except Exception as e:
                    print(f"Drive completo error: {e}")

        # ── Leer config ZIP para trigger inicial ──────────────────
        try:
            from app.models import ConfiguracionSistema
            zip_activo     = ConfiguracionSistema.obtener('zip_activo', 'true') == 'true'
            zip_frecuencia = ConfiguracionSistema.obtener('zip_frecuencia', '2meses')
            zip_hora_str   = ConfiguracionSistema.obtener('zip_hora', '08:00')
            hora_n = int(zip_hora_str.split(':')[0])
            min_n  = int(zip_hora_str.split(':')[1])
        except:
            zip_activo     = True
            zip_frecuencia = '2meses'
            hora_n, min_n  = 8, 0

        if zip_frecuencia == 'hora':
            zip_trigger = CronTrigger(minute=0)
        elif zip_frecuencia == 'dia':
            zip_trigger = CronTrigger(hour=hora_n, minute=min_n)
        elif zip_frecuencia == 'semana':
            zip_trigger = CronTrigger(day_of_week='mon', hour=hora_n, minute=min_n)
        elif zip_frecuencia == 'mes':
            zip_trigger = CronTrigger(day=1, hour=hora_n, minute=min_n)
        else:
            zip_trigger = CronTrigger(month='1,3,5,7,9,11', day=1, hour=hora_n, minute=min_n)

        if zip_activo:
            _scheduler.add_job(
                ejecutar_backup_zip,
                trigger=zip_trigger,
                id='backup_zip_correo',
                replace_existing=True,
                misfire_grace_time=300
            )

        _scheduler.add_job(
            sincronizar_drive_csv,
            trigger=CronTrigger(minute='*/5'),
            id='drive_csv',
            replace_existing=True,
            misfire_grace_time=60
        )

        _scheduler.add_job(
            sincronizar_drive_completo,
            trigger=CronTrigger(hour='*', minute=30),
            id='drive_completo',
            replace_existing=True,
            misfire_grace_time=300
        )

        _scheduler.add_job(
            monitorear_neon,
            trigger=CronTrigger(hour=8, minute=0),
            id='monitoreo_neon',
            replace_existing=True,
            misfire_grace_time=300
        )

        _scheduler.start()

        threading.Timer(10, sincronizar_drive_csv).start()
        print("⏳ Sync Drive inicial en 10 segundos...")

        atexit.register(lambda: _scheduler.shutdown(wait=False))
        print("✅ Scheduler — Drive CSV c/5min | Drive completo c/hora | ZIP configurable | Neon diario")

    except Exception as e:
        print(f"⚠️ Scheduler no iniciado: {e}")


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cambia-esta-clave-en-produccion-32chars')
    app.config['WTF_CSRF_ENABLED'] = False

    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    if DATABASE_URL:
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg2://', 1)
        elif DATABASE_URL.startswith('postgresql://') and '+psycopg2' not in DATABASE_URL:
            DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../instance/database.db'

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 5,
        'max_overflow': 2,
        'connect_args': {'connect_timeout': 5}
    }

    app.config['APP_VERSION'] = os.environ.get('APP_VERSION', '2.0.0')

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'main.index'
    login_manager.login_message = 'Por favor inicia sesión para acceder.'
    login_manager.login_message_category = 'warning'

    from app.models import Usuario, Rol

    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    from app.routes import main
    app.register_blueprint(main)

    with app.app_context():
        if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
            os.makedirs(os.path.join(app.instance_path), exist_ok=True)

        db.create_all()

        if not Rol.query.first():
            for r in [
                ('admin',        'Administrador del sistema'),
                ('medico',       'Profesional médico'),
                ('enfermeria',   'Personal de enfermería'),
                ('recepcionista','Personal de recepción'),
            ]:
                db.session.add(Rol(nombre=r[0], descripcion=r[1]))
            db.session.commit()
            print("✅ Roles creados")

        from app.models import ConfiguracionSistema
        try:
            if not ConfiguracionSistema.query.filter_by(clave='2fa_activo').first():
                db.session.add(ConfiguracionSistema(clave='2fa_activo', valor='true'))
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Config 2FA: {e}")

        try:
            gmail_user = ConfiguracionSistema.obtener('gmail_user', '')
            gmail_pass = ConfiguracionSistema.obtener('gmail_app_password', '')
            if gmail_user:
                os.environ.setdefault('GMAIL_USER', gmail_user)
            if gmail_pass:
                os.environ.setdefault('GMAIL_APP_PASSWORD', gmail_pass)
            for clave, valor in [
                ('backup_email',  ''),
                ('zip_activo',    'true'),
                ('zip_frecuencia','2meses'),
                ('zip_hora',      '08:00'),
            ]:
                if not ConfiguracionSistema.query.filter_by(clave=clave).first():
                    db.session.add(ConfiguracionSistema(clave=clave, valor=valor))
            db.session.commit()
        except Exception as e:
            print(f'⚠️ Config correo: {e}')

        from app.models import VersionSistema
        if not VersionSistema.query.first():
            db.session.add(VersionSistema(
                version=app.config['APP_VERSION'],
                descripcion='Versión inicial',
                es_critica=False
            ))
            db.session.commit()

        _iniciar_scheduler(app)

    return app
