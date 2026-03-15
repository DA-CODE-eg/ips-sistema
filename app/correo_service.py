"""
Servicio de correos — Gmail SMTP en hilo separado
Funciona perfecto desde instalador local (.exe)
"""

import os
import random
import string
import smtplib
import threading

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


# ============================================================
# CREDENCIALES
# ============================================================

def _credenciales():
    return os.environ.get('GMAIL_USER', ''), os.environ.get('GMAIL_APP_PASSWORD', '')


# ============================================================
# ENVÍO SMTP
# ============================================================

def _enviar_smtp(destinatario, asunto, cuerpo_html, adjunto_bytes=None, adjunto_nombre=None):

    gmail_user, gmail_password = _credenciales()

    if not gmail_user or not gmail_password:
        print("⚠️  GMAIL_USER o GMAIL_APP_PASSWORD no configurados")
        return

    try:

        msg = MIMEMultipart()
        msg['Subject'] = asunto
        msg['From'] = f'IPS Fulano <{gmail_user}>'
        msg['To'] = destinatario

        msg.attach(MIMEText(cuerpo_html, 'html'))

        if adjunto_bytes and adjunto_nombre:
            parte = MIMEBase('application', 'zip')
            parte.set_payload(adjunto_bytes)
            encoders.encode_base64(parte)
            parte.add_header(
                'Content-Disposition',
                f'attachment; filename="{adjunto_nombre}"'
            )
            msg.attach(parte)

        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, destinatario, msg.as_string())

        print(f"✅ Correo enviado a {destinatario}")

    except Exception as e:
        print(f"❌ Error enviando correo a {destinatario}: {e}")


# ============================================================
# ENVÍO EN HILO
# ============================================================

def _enviar_correo(destinatario, asunto, cuerpo_html, adjunto_bytes=None, adjunto_nombre=None):

    t = threading.Thread(
        target=_enviar_smtp,
        args=(destinatario, asunto, cuerpo_html, adjunto_bytes, adjunto_nombre),
        daemon=True
    )

    t.start()

    return True


# ============================================================
# GENERAR CÓDIGO
# ============================================================

def generar_codigo():
    return ''.join(random.choices(string.digits, k=6))


# ============================================================
# 2FA LOGIN
# ============================================================

def enviar_codigo_2fa(usuario_email, usuario_nombre, codigo):

    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#1E3A5F,#0D7377);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🏥 IPS FULANO</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">Sistema de Gestión en Salud</p>
  </div>

  <p style="color:#333;font-size:15px;">Hola <strong>{usuario_nombre}</strong>,</p>
  <p style="color:#555;font-size:14px;">Tu código de verificación es:</p>

  <div style="background:white;border:2px solid #1E3A5F;border-radius:12px;padding:24px;text-align:center;margin:20px 0;">
    <span style="font-size:42px;font-weight:bold;letter-spacing:12px;color:#1E3A5F;">{codigo}</span>
  </div>

  <p style="color:#e53935;font-size:13px;text-align:center;">⏱️ Expira en <strong>5 minutos</strong></p>

  <p style="color:#999;font-size:12px;margin-top:20px;">Si no intentaste iniciar sesión, ignora este correo.</p>
</div>
"""

    return _enviar_correo(
        usuario_email,
        f'Código: {codigo} — IPS Fulano',
        cuerpo
    )


# ============================================================
# NOTIFICACIÓN LOGIN
# ============================================================

def enviar_notificacion_login(usuario_email, usuario_nombre, ip, fecha_hora):

    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#1E3A5F,#0D7377);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🏥 IPS FULANO</h2>
  </div>

  <p style="color:#333;font-size:15px;">Hola <strong>{usuario_nombre}</strong>,</p>
  <p style="color:#555;font-size:14px;">Se registró un <strong>inicio de sesión</strong> en tu cuenta.</p>

  <div style="background:white;border-radius:8px;padding:16px;margin:16px 0;">
    <p>📅 <strong>Fecha:</strong> {fecha_hora}</p>
    <p>🌐 <strong>IP:</strong> {ip}</p>
  </div>

  <p style="color:#e53935;font-size:13px;">Si no fuiste tú, contacta al administrador.</p>
</div>
"""

    return _enviar_correo(
        usuario_email,
        'Inicio de sesión — IPS Fulano',
        cuerpo
    )


# ============================================================
# NOTIFICACIÓN LOGOUT
# ============================================================

def enviar_notificacion_logout(usuario_email, usuario_nombre, fecha_hora):

    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#1E3A5F,#0D7377);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🏥 IPS FULANO</h2>
  </div>

  <p style="color:#333;font-size:15px;">Hola <strong>{usuario_nombre}</strong>,</p>
  <p style="color:#555;font-size:14px;">Tu sesión fue <strong>cerrada</strong> correctamente.</p>

  <div style="background:white;border-radius:8px;padding:16px;margin:16px 0;">
    <p>📅 <strong>Fecha:</strong> {fecha_hora}</p>
  </div>
</div>
"""

    return _enviar_correo(
        usuario_email,
        'Sesión cerrada — IPS Fulano',
        cuerpo
    )


# ============================================================
# VALIDACIÓN DE CORREO
# ============================================================

def enviar_codigo_validacion_correo(email, codigo):

    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">

  <div style="background:linear-gradient(135deg,#1E3A5F,#0D7377);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🏥 IPS FULANO</h2>
  </div>

  <p style="color:#333;font-size:15px;">Se está creando una cuenta con este correo.</p>

  <div style="background:white;border:2px solid #0D7377;border-radius:12px;padding:24px;text-align:center;margin:20px 0;">
    <p style="color:#666;font-size:13px;margin-bottom:8px;">Código de verificación</p>
    <span style="font-size:42px;font-weight:bold;letter-spacing:12px;color:#0D7377;">{codigo}</span>
  </div>

  <p style="color:#e53935;font-size:13px;text-align:center;">⏱️ Expira en <strong>5 minutos</strong></p>

</div>
"""

    return _enviar_correo(
        email,
        f'Verificación de correo: {codigo} — IPS Fulano',
        cuerpo
    )


# ============================================================
# BACKUP POR CORREO
# ============================================================

def enviar_backup_por_correo(archivo_bytes, nombre_archivo, email_destino):

    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">

  <div style="background:linear-gradient(135deg,#1E3A5F,#0D7377);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🏥 IPS FULANO</h2>
  </div>

  <p style="color:#333;font-size:15px;">Se ha generado un <strong>backup automático</strong> del sistema.</p>

  <div style="background:white;border-radius:8px;padding:16px;margin:16px 0;">
    <p>📦 <strong>Archivo:</strong> {nombre_archivo}</p>
  </div>

  <p style="color:#555;font-size:13px;">Guarda este correo en tu Google Drive para tener respaldo seguro.</p>

</div>
"""

    return _enviar_correo(
        email_destino,
        f'📦 Backup IPS Fulano — {nombre_archivo}',
        cuerpo,
        adjunto_bytes=archivo_bytes,
        adjunto_nombre=nombre_archivo
    )


# ============================================================
# ALERTA DE ESPACIO EN NEON
# ============================================================

def enviar_alerta_neon(email_destino, mb_usado, mb_limite, porcentaje, nivel):
    """Alerta automática cuando Neon se está llenando."""

    gmail_user, gmail_pass = _credenciales()

    if not gmail_user or not gmail_pass:
        return

    if nivel == 'critico':
        color = '#dc3545'
        emoji = '🚨'
        titulo = 'CRÍTICO — Base de datos casi llena'
        accion = 'El sistema puede dejar de guardar datos MUY PRONTO. Actúe de inmediato.'

    elif nivel == 'peligro':
        color = '#fd7e14'
        emoji = '🔴'
        titulo = 'PELIGRO — Base de datos al 85%'
        accion = 'La base de datos se está llenando. Considere limpiar datos antiguos o migrar a un plan pagado.'

    else:
        color = '#ffc107'
        emoji = '⚠️'
        titulo = 'ADVERTENCIA — Base de datos al 70%'
        accion = 'La base de datos superó el 70% de capacidad. Esté pendiente.'

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">

  <div style="background:{color};color:white;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
    <h2 style="margin:0;">{emoji} {titulo}</h2>
  </div>

  <div style="background:#f9f9f9;padding:24px;border:1px solid #ddd;border-radius:0 0 8px 8px;">

    <p style="font-size:16px;">{accion}</p>

    <div style="background:#fff;border:1px solid #ddd;border-radius:8px;padding:16px;margin:16px 0;">
      <p><strong>Espacio usado:</strong> {mb_usado:.1f} MB de {mb_limite} MB</p>
      <p><strong>Porcentaje:</strong> {porcentaje:.1f}%</p>

      <div style="background:#e9ecef;border-radius:4px;height:20px;margin:8px 0;">
        <div style="background:{color};width:{min(porcentaje,100):.0f}%;height:20px;border-radius:4px;"></div>
      </div>

      <p><strong>Espacio libre:</strong> {mb_limite - mb_usado:.1f} MB</p>
    </div>

    <p style="color:#666;font-size:13px;">
      Este es un aviso automático del sistema IPS Fulano.<br>
      El límite gratuito de Neon es 512 MB (0.5 GB).
    </p>

  </div>

</div>
"""

    _enviar_correo(
        email_destino,
        f'{emoji} IPS Fulano — Base de datos al {porcentaje:.0f}%',
        html
    )

# ============================================================
# SOLICITUD DE CITA — al paciente (confirmación de recibido)
# ============================================================
def enviar_confirmacion_solicitud(email_paciente, nombre_paciente, especialidad, fecha_preferida, motivo):
    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#1E3A5F,#0D7377);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🏥 IPS FULANO</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">Fundación Universitaria de las Américas</p>
  </div>
  <p style="color:#333;font-size:15px;">Hola <strong>{nombre_paciente}</strong>,</p>
  <p style="color:#555;font-size:14px;">Tu solicitud de cita fue recibida correctamente. Pronto te contactaremos para confirmarla.</p>
  <div style="background:white;border-left:4px solid #0D7377;border-radius:8px;padding:16px;margin:16px 0;">
    <p style="margin:4px 0">🩺 <strong>Especialidad:</strong> {especialidad}</p>
    <p style="margin:4px 0">📅 <strong>Fecha preferida:</strong> {fecha_preferida or 'A convenir'}</p>
    <p style="margin:4px 0">📝 <strong>Motivo:</strong> {motivo or '-'}</p>
  </div>
  <p style="color:#555;font-size:13px;">Recibirás otro correo con la confirmación, fecha, hora y médico asignado.</p>
  <p style="color:#999;font-size:12px;margin-top:20px;">IPS Fulano — Tel: 601-7559343 | ipsfulano@fundacioneudes.co</p>
</div>"""
    return _enviar_correo(email_paciente, '✅ Solicitud de cita recibida — IPS Fulano', cuerpo)


# ============================================================
# NUEVA SOLICITUD — al sistema (notificación interna)
# ============================================================
def enviar_notificacion_nueva_solicitud(emails_sistema, nombre_paciente, cedula, especialidad, fecha_preferida, motivo, url_sistema):
    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#C0392B,#922B21);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">🔔 Nueva Solicitud de Cita</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">IPS Fulano — Panel Administrativo</p>
  </div>
  <p style="color:#333;font-size:15px;">Se recibió una nueva solicitud de cita:</p>
  <div style="background:white;border-left:4px solid #C0392B;border-radius:8px;padding:16px;margin:16px 0;">
    <p style="margin:4px 0">👤 <strong>Paciente:</strong> {nombre_paciente}</p>
    <p style="margin:4px 0">🪪 <strong>Cédula:</strong> {cedula}</p>
    <p style="margin:4px 0">🩺 <strong>Especialidad:</strong> {especialidad}</p>
    <p style="margin:4px 0">📅 <strong>Fecha preferida:</strong> {fecha_preferida or 'A convenir'}</p>
    <p style="margin:4px 0">📝 <strong>Motivo:</strong> {motivo or '-'}</p>
  </div>
  <div style="text-align:center;margin-top:20px;">
    <a href="{url_sistema}" style="background:#C0392B;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;">
      Ver en el sistema →
    </a>
  </div>
</div>"""
    for email in emails_sistema:
        _enviar_correo(email, f'🔔 Nueva solicitud de cita — {nombre_paciente}', cuerpo)


# ============================================================
# CITA CONFIRMADA — al paciente con tiquete PDF adjunto
# ============================================================
def enviar_cita_confirmada(email_paciente, nombre_paciente, medico, especialidad, fecha_hora, pdf_bytes, cita_id):
    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#1E8449,#145A32);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">✅ Cita Confirmada</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">IPS Fulano — Fundación Universitaria de las Américas</p>
  </div>
  <p style="color:#333;font-size:15px;">Hola <strong>{nombre_paciente}</strong>,</p>
  <p style="color:#555;font-size:14px;">Tu cita ha sido <strong>confirmada</strong>. Aquí están los detalles:</p>
  <div style="background:white;border-left:4px solid #1E8449;border-radius:8px;padding:16px;margin:16px 0;">
    <p style="margin:4px 0">👨‍⚕️ <strong>Médico:</strong> {medico}</p>
    <p style="margin:4px 0">🩺 <strong>Especialidad:</strong> {especialidad}</p>
    <p style="margin:4px 0">📅 <strong>Fecha y hora:</strong> {fecha_hora}</p>
  </div>
  <p style="color:#555;font-size:13px;">El tiquete de tu cita va adjunto a este correo. Preséntalo el día de tu cita.</p>
  <div style="background:#FEF9E7;border:1px solid #F39C12;border-radius:8px;padding:12px;margin-top:16px;">
    <p style="margin:0;font-size:13px;color:#784212;">⚠️ Si no puedes asistir, comunícate con nosotros con anticipación.</p>
  </div>
  <p style="color:#999;font-size:12px;margin-top:20px;">IPS Fulano — Tel: 601-7559343 | ipsfulano@fundacioneudes.co</p>
</div>"""

    # Adjuntar tiquete como PDF
    from email.mime.base import MIMEBase
    from email import encoders
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import smtplib

    gmail_user, gmail_password = _credenciales()
    if not gmail_user or not gmail_password:
        return

    def _enviar():
        try:
            msg = MIMEMultipart()
            msg['Subject'] = f'✅ Cita confirmada #{cita_id} — IPS Fulano'
            msg['From']    = f'IPS Fulano <{gmail_user}>'
            msg['To']      = email_paciente
            msg.attach(MIMEText(cuerpo, 'html'))
            parte = MIMEBase('application', 'pdf')
            parte.set_payload(pdf_bytes)
            encoders.encode_base64(parte)
            parte.add_header('Content-Disposition', f'attachment; filename="tiquete_cita_{cita_id}.pdf"')
            msg.attach(parte)
            with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as s:
                s.ehlo(); s.starttls(); s.login(gmail_user, gmail_password)
                s.sendmail(gmail_user, email_paciente, msg.as_string())
            print(f"✅ Tiquete enviado a {email_paciente}")
        except Exception as e:
            print(f"❌ Error enviando tiquete: {e}")

    import threading
    threading.Thread(target=_enviar, daemon=True).start()


# ============================================================
# CITA CANCELADA — al paciente
# ============================================================
def enviar_cita_cancelada(email_paciente, nombre_paciente, especialidad, motivo_cancelacion=''):
    cuerpo = f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#f5f5f5;padding:24px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#922B21,#C0392B);padding:20px;border-radius:8px;text-align:center;margin-bottom:24px;">
    <h2 style="color:white;margin:0;font-size:22px;">❌ Cita Cancelada</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">IPS Fulano</p>
  </div>
  <p style="color:#333;font-size:15px;">Hola <strong>{nombre_paciente}</strong>,</p>
  <p style="color:#555;font-size:14px;">Lamentamos informarte que tu cita de <strong>{especialidad}</strong> ha sido cancelada.</p>
  {f'<div style="background:white;border-left:4px solid #C0392B;border-radius:8px;padding:12px;margin:16px 0;"><p style="margin:0">📝 <strong>Motivo:</strong> {motivo_cancelacion}</p></div>' if motivo_cancelacion else ''}
  <p style="color:#555;font-size:13px;">Por favor comunícate con nosotros para reagendar tu cita.</p>
  <p style="color:#999;font-size:12px;margin-top:20px;">IPS Fulano — Tel: 601-7559343 | ipsfulano@fundacioneudes.co</p>
</div>"""
    return _enviar_correo(email_paciente, '❌ Cita cancelada — IPS Fulano', cuerpo)
