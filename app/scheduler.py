"""
Scheduler — backup cada hora + monitoreo automático de Neon.
Al arrancar el sistema corre un backup inicial después de 10 segundos.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import threading
import atexit

_scheduler = None


def iniciar_scheduler(app):
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)

    # ── BACKUP CADA HORA ─────────────────────────────────────
    def ejecutar_backup():
        with app.app_context():
            try:
                print("⏰ Backup automático iniciando...")
                from .backup_service import generar_backup
                ok, registro_id, error = generar_backup(tipo='automatico')
                if ok:
                    print(f"✅ Backup automático exitoso (ID: {registro_id})")
                else:
                    print(f"❌ Backup automático falló: {error}")
            except Exception as e:
                print(f"❌ Error en backup automático: {e}")

    _scheduler.add_job(
        ejecutar_backup,
        trigger=CronTrigger(hour='*', minute=0),
        id='backup_automatico',
        replace_existing=True,
        misfire_grace_time=300
    )

    # ── MONITOREO NEON — cada día a las 8am ──────────────────
    def monitorear_neon():
        with app.app_context():
            try:
                from . import db
                from .models import CorreoBackup, ConfiguracionSistema
                from .correo_service import enviar_alerta_neon

                resultado = db.session.execute(
                    db.text("SELECT pg_database_size(current_database())")
                ).scalar()
                if not resultado:
                    return

                mb_usado   = resultado / (1024 * 1024)
                mb_limite  = 512
                porcentaje = (mb_usado / mb_limite) * 100

                print(f"📊 Neon: {mb_usado:.1f} MB usado de {mb_limite} MB ({porcentaje:.1f}%)")

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
                    correos = CorreoBackup.query.filter_by(verificado=True).all()
                    for c in correos:
                        try:
                            enviar_alerta_neon(c.email, mb_usado, mb_limite, porcentaje, alerta)
                            print(f"📧 Alerta Neon ({alerta}) enviada a {c.email}")
                        except Exception as e:
                            print(f"❌ Error enviando alerta a {c.email}: {e}")

            except Exception as e:
                print(f"⚠️ Error monitoreando Neon: {e}")

    _scheduler.add_job(
        monitorear_neon,
        trigger=CronTrigger(hour=8, minute=0),
        id='monitoreo_neon',
        replace_existing=True,
        misfire_grace_time=300
    )

    _scheduler.start()

    # ── BACKUP INMEDIATO AL ARRANCAR (10 segundos después) ───
    # Da tiempo a que Flask termine de iniciar antes de correr
    threading.Timer(10, ejecutar_backup).start()
    print("⏳ Backup inicial programado en 10 segundos...")

    atexit.register(lambda: _scheduler.shutdown(wait=False))
    print("✅ Scheduler activo — backup cada hora + monitoreo Neon diario")
