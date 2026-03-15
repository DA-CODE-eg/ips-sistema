"""
Servicio de backup — genera datos y los sube a Google Drive
como archivos sueltos organizados en carpetas (no ZIP).
También guarda ZIP en BD para descarga desde el sistema.
"""
import os, io, csv, zipfile, datetime
from .models import db, BackupRegistro, Paciente, Cita, Auditoria, HistoriaEntrada, Usuario, Especialidad, CorreoBackup


def _volcar_csv(campos, modelo):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(campos)
    for r in modelo.query.all():
        w.writerow([str(getattr(r, c, '') or '') for c in campos])
    return buf.getvalue().encode('utf-8')


def _generar_pdf_html(html_string):
    try:
        from weasyprint import HTML
        return HTML(string=html_string).write_pdf()
    except Exception as e:
        print(f"PDF no generado: {e}")
        return None


def generar_backup(tipo='manual', usuario_id=None):
    registro = BackupRegistro(tipo=tipo, solicitado_por_id=usuario_id, estado='generando')
    db.session.add(registro)
    db.session.commit()

    try:
        timestamp  = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_zip = f'backup_ips_fulano_{timestamp}.zip'

        # ── DATOS CSV ─────────────────────────────────────────
        datos_csv = {
            'pacientes.csv': _volcar_csv(
                ['id','nombre','identificacion','tipo_identificacion','telefono',
                 'email','direccion','fecha_nacimiento','sexo','activo','creado_en'], Paciente),
            'citas.csv': _volcar_csv(
                ['id','paciente_id','medico_id','especialidad_id','fecha',
                 'estado','motivo_consulta','creado_en'], Cita),
            'auditoria.csv': _volcar_csv(
                ['id','usuario_email','accion','modulo','descripcion',
                 'ip_origen','fecha_hora','exitoso'], Auditoria),
            'historias_clinicas.csv': _volcar_csv(
                ['id','historia_id','autor_id','tipo_entrada','contenido','fecha'], HistoriaEntrada),
            'usuarios.csv': _volcar_csv(
                ['id','nombre','email','rol_id','activo','creado_en'], Usuario),
            'especialidades.csv': _volcar_csv(
                ['id','nombre','activo'], Especialidad),
        }

        # ── REPORTES PDF ──────────────────────────────────────
        reportes_pdf = {}
        try:
            from flask import render_template
            fecha_gen = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')

            pdf = _generar_pdf_html(render_template('reporte/pacientes_pdf.html',
                pacientes=Paciente.query.all(), fecha_generacion=fecha_gen))
            if pdf:
                reportes_pdf['reporte_pacientes.pdf'] = pdf

            pdf = _generar_pdf_html(render_template('reporte/citas_pdf.html',
                citas=Cita.query.order_by(Cita.fecha.desc()).all(), fecha_generacion=fecha_gen))
            if pdf:
                reportes_pdf['reporte_citas.pdf'] = pdf

            pdf = _generar_pdf_html(render_template('reporte/especialidades_pdf.html',
                especialidades=Especialidad.query.all(), fecha_generacion=fecha_gen))
            if pdf:
                reportes_pdf['reporte_especialidades.pdf'] = pdf

        except Exception as e:
            print(f"Reportes PDF no generados: {e}")

        # ── HISTORIAS CLÍNICAS PDF ────────────────────────────
        historias_pdf = {}
        try:
            from flask import render_template
            from .models import HistoriaClinica

            for paciente in Paciente.query.filter_by(activo=True).all():
                historia = HistoriaClinica.query.filter_by(paciente_id=paciente.id).first()
                if not historia:
                    continue
                entradas = HistoriaEntrada.query.filter_by(
                    historia_id=historia.id
                ).order_by(HistoriaEntrada.fecha.desc()).all()
                if not entradas:
                    continue

                edad = None
                if paciente.fecha_nacimiento:
                    today = datetime.date.today()
                    edad  = today.year - paciente.fecha_nacimiento.year
                    if today < paciente.fecha_nacimiento.replace(year=today.year):
                        edad -= 1

                pdf = _generar_pdf_html(render_template('historia/historia_clinica_pdf.html',
                    paciente=paciente, historia=historia, entradas=entradas,
                    fecha_generacion=datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                    edad=edad, solo_recientes=False))
                if pdf:
                    nombre_pac = paciente.nombre.replace(' ', '_')
                    historias_pdf[f'{nombre_pac}_{paciente.identificacion}.pdf'] = pdf

        except Exception as e:
            print(f"Historias PDF no generadas: {e}")

        # ── GENERAR ZIP para BD y correo ──────────────────────
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('LEAME.txt',
                f'IPS FULANO — BACKUP\nFecha: {datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n')
            for nombre, contenido in datos_csv.items():
                zf.writestr(f'datos/{nombre}', contenido)
            for nombre, contenido in reportes_pdf.items():
                zf.writestr(f'reportes/{nombre}', contenido)
            for nombre, contenido in historias_pdf.items():
                zf.writestr(f'historias/{nombre}', contenido)

        zip_bytes = zip_buffer.getvalue()

        registro.archivo_nombre = nombre_zip
        registro.archivo_datos  = zip_bytes
        registro.tamano_bytes   = len(zip_bytes)
        registro.estado         = 'exitoso'
        db.session.commit()

        # ── SINCRONIZAR CON GOOGLE DRIVE ──────────────────────
        try:
            from .drive_service import sincronizar_con_drive, compartir_carpeta_con_todos
            ok, error = sincronizar_con_drive(datos_csv, reportes_pdf, historias_pdf)
            if ok:
                print("Drive sincronizado")
                # Compartir con todos los correos verificados
                correos = [c.email for c in CorreoBackup.query.filter_by(verificado=True).all()]
                compartir_carpeta_con_todos(correos)
            else:
                print(f"Drive fallo: {error}")
        except Exception as e:
            print(f"Drive no disponible: {e}")

        # ── ENVIAR A CORREOS VERIFICADOS ──────────────────────
        _enviar_a_todos(zip_bytes, nombre_zip)

        return True, registro.id, None

    except Exception as e:
        registro.estado        = 'fallido'
        registro.error_mensaje = str(e)
        db.session.commit()
        return False, None, str(e)


def _enviar_a_todos(zip_bytes, nombre_zip):
    from .correo_service import enviar_backup_por_correo
    correos = CorreoBackup.query.filter_by(verificado=True).all()
    for c in correos:
        try:
            enviar_backup_por_correo(zip_bytes, nombre_zip, c.email)
            print(f"Backup enviado a {c.email}")
        except Exception as e:
            print(f"Error enviando a {c.email}: {e}")
