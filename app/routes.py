from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, jsonify, send_file, session
from flask_login import login_required, current_user, logout_user, login_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import (db, Usuario, Paciente, Cita, Especialidad,
                     CampoPersonalizado, ValorCampoPersonalizado,
                     HistoriaClinica, HistoriaVersion, HistoriaEntrada,
                     Rol, Auditoria, BackupRegistro, VersionSistema)
from .forms import (LoginForm, CambiarPasswordForm, UsuarioForm,
                    EspecialidadForm, CitaForm, PacienteForm, RolForm)
from .auditoria_helper import registrar_auditoria
from .drive_service import subir_pdf_drive
from app.pdf_generator import (generar_historia_pdf, generar_pacientes_pdf,
                               generar_citas_pdf, generar_especialidades_pdf,
                               generar_tiquete_pdf)
from datetime import datetime, timedelta
import os

main = Blueprint('main', __name__)


# ============================================================
# LOGIN / LOGOUT
# ============================================================
@main.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data).first()

        if not usuario:
            registrar_auditoria('LOGIN_FALLIDO', 'Auth',
                f'Email no encontrado: {form.email.data}', exitoso=False)
            flash('Correo o contraseña incorrectos', 'error')
            return render_template('login.html', form=form)

        # Verificar bloqueo
        if usuario.esta_bloqueado():
            minutos = int((usuario.bloqueado_hasta - datetime.utcnow()).total_seconds() / 60) + 1
            flash(f'Cuenta bloqueada por múltiples intentos fallidos. Intenta en {minutos} minuto(s).', 'danger')
            return render_template('login.html', form=form)

        if not check_password_hash(usuario.password, form.password.data):
            usuario.registrar_intento_fallido()
            db.session.commit()
            intentos = 5 - (usuario.intentos_fallidos or 0)
            registrar_auditoria('LOGIN_FALLIDO', 'Auth',
                f'Contraseña incorrecta para: {form.email.data}', exitoso=False,
                usuario_id=usuario.id, usuario_email=usuario.email)
            if usuario.esta_bloqueado():
                flash('Cuenta bloqueada por 30 minutos después de 5 intentos fallidos.', 'danger')
            else:
                flash(f'Contraseña incorrecta. Intentos restantes: {max(intentos,0)}', 'error')
            return render_template('login.html', form=form)

        if not usuario.activo:
            flash('Tu cuenta está inactiva. Contacta al administrador.', 'warning')
            return render_template('login.html', form=form)

        # Verificar si 2FA está activo
        from .models import ConfiguracionSistema, CodigoVerificacion
        from .correo_service import generar_codigo, enviar_codigo_2fa
        from flask import session

        dos_fa_activo = ConfiguracionSistema.obtener('2fa_activo', 'true') == 'true'

        if dos_fa_activo:
            # Guardar usuario pendiente y enviar código
            codigo = generar_codigo()
            expira = datetime.utcnow() + timedelta(minutes=5)
            db.session.add(CodigoVerificacion(email=usuario.email, codigo=codigo, tipo='2fa', expira_en=expira))
            db.session.commit()
            enviado = enviar_codigo_2fa(usuario.email, usuario.nombre, codigo)
            session['pendiente_2fa'] = usuario.id
            if not enviado:
                flash('No se pudo enviar el código. Contacta al administrador.', 'danger')
                return render_template('login.html', form=form)
            return redirect(url_for('main.verificar_codigo'))

        # Sin 2FA — login directo
        usuario.registrar_acceso_exitoso(ip=request.remote_addr)
        db.session.commit()
        login_user(usuario)

        from .correo_service import enviar_notificacion_login
        try:
            enviar_notificacion_login(usuario.email, usuario.nombre, request.remote_addr, datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S'))
        except:
            pass

        registrar_auditoria('LOGIN', 'Auth', f'Acceso exitoso: {usuario.email}')

        if not usuario.password_cambiada:
            flash('Por seguridad, debes cambiar tu contraseña.', 'info')
            return redirect(url_for('main.cambiar_password'))

        flash(f'Bienvenido {usuario.nombre}', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('login.html', form=form)


@main.route('/logout')
@login_required
def logout():
    from .correo_service import enviar_notificacion_logout
    nombre = current_user.nombre
    email  = current_user.email
    registrar_auditoria('LOGOUT', 'Auth', f'Cierre de sesión: {email}')
    try:
        enviar_notificacion_logout(email, nombre, datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S'))
    except:
        pass
    logout_user()
    if request.args.get('inactive') == '1':
        flash('Sesión cerrada por inactividad.', 'warning')
    else:
        flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('main.index'))


# ============================================================
# DASHBOARD
# ============================================================
@main.route('/dashboard')
@login_required
def dashboard():
    from datetime import timedelta
    hoy = datetime.today()

    pacientes_recientes = Paciente.query.order_by(Paciente.id.desc()).limit(5).all()
    citas_recientes     = Cita.query.order_by(Cita.fecha.desc()).limit(5).all()

    try:
        from app.models import CampoPersonalizado
        campos_activos = CampoPersonalizado.query.filter_by(activo=True).order_by(CampoPersonalizado.orden).all()
    except Exception:
        campos_activos = []

    stats = {
        'total_pacientes':    Paciente.query.filter_by(activo=True).count(),
        'total_citas':        Cita.query.count(),
        'citas_hoy':          Cita.query.filter(
                                  Cita.fecha >= hoy.replace(hour=0,minute=0,second=0),
                                  Cita.fecha <= hoy.replace(hour=23,minute=59,second=59)
                              ).count(),
        'citas_pendientes':   Cita.query.filter_by(estado='Pendiente').count(),
        'citas_solicitadas':  Cita.query.filter_by(estado='Solicitada').count(),
        'citas_confirmadas':  Cita.query.filter_by(estado='Confirmada').count(),
        'pacientes_recientes': pacientes_recientes,
        'citas_recientes':     citas_recientes,
    }
    return render_template('admin/dashboard.html', stats=stats, campos_activos=campos_activos)


# ============================================================
# PERFIL
# ============================================================
@main.route('/perfil/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    require_current = current_user.password_cambiada
    form = CambiarPasswordForm(require_current=require_current)

    if form.validate_on_submit():
        if require_current:
            if not check_password_hash(current_user.password, form.password_actual.data):
                flash('La contraseña actual es incorrecta', 'danger')
                return render_template('perfil/cambiar_password.html', form=form, require_current=require_current)

        if check_password_hash(current_user.password, form.password_nueva.data):
            flash('La nueva contraseña debe ser diferente a la actual', 'warning')
            return render_template('perfil/cambiar_password.html', form=form, require_current=require_current)

        current_user.password = generate_password_hash(form.password_nueva.data)
        current_user.password_cambiada = True
        db.session.commit()
        registrar_auditoria('CAMBIO_PASSWORD', 'Perfil', 'Contraseña actualizada')
        flash('Contraseña actualizada exitosamente', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('perfil/cambiar_password.html', form=form, require_current=require_current)


# ============================================================
# PACIENTES
# ============================================================
@main.route('/pacientes')
@login_required
def lista_pacientes():
    q = request.args.get('q', '').strip()
    if q:
        pacientes = Paciente.query.filter(
            db.or_(Paciente.nombre.contains(q), Paciente.identificacion.contains(q))
        ).all()
    else:
        pacientes = Paciente.query.all()
    return render_template('paciente/pacientes.html', pacientes=pacientes, query=q)


def _guardar_campos_extra(paciente):
    """Guarda los valores de campos personalizados para un paciente."""
    campos = CampoPersonalizado.query.filter_by(activo=True).all()
    for campo in campos:
        valor_nuevo = request.form.get(f'campo_{campo.id}', '').strip()
        registro = ValorCampoPersonalizado.query.filter_by(
            paciente_id=paciente.id, campo_id=campo.id).first()
        if registro:
            registro.valor = valor_nuevo or None
        else:
            if valor_nuevo:
                db.session.add(ValorCampoPersonalizado(
                    paciente_id=paciente.id,
                    campo_id=campo.id,
                    valor=valor_nuevo
                ))
    db.session.commit()


@main.route('/paciente/nuevo', methods=['GET', 'POST'])
@login_required
def crear_paciente():
    form = PacienteForm()
    campos_extra = CampoPersonalizado.query.filter_by(activo=True).order_by(
        CampoPersonalizado.orden).all()
    if form.validate_on_submit():
        existente = Paciente.query.filter_by(identificacion=form.identificacion.data).first()
        if existente:
            return render_template('paciente/crear.html', form=form, campos_extra=campos_extra,
                                   duplicado_id=existente.id,
                                   duplicado_nombre=existente.nombre,
                                   duplicado_doc=existente.identificacion,
                                   duplicado_activo=existente.activo)
        try:
            p = Paciente(
                nombre=form.nombre.data,
                identificacion=form.identificacion.data,
                sexo=form.sexo.data,
                fecha_nacimiento=form.fecha_nacimiento.data,
                telefono=form.telefono.data,
                email=form.email.data,
                direccion=form.direccion.data,
                activo=True,
                creado_por_id=current_user.id
            )
            db.session.add(p)
            db.session.commit()
            _guardar_campos_extra(p)
            registrar_auditoria('CREAR', 'Pacientes', f'Paciente creado: {p.nombre} ({p.identificacion})')
            flash('Paciente creado exitosamente', 'success')
            return redirect(url_for('main.lista_pacientes'))
        except Exception:
            db.session.rollback()
            flash('Error al guardar el paciente.', 'danger')
    return render_template('paciente/crear.html', form=form, campos_extra=campos_extra)


@main.route('/paciente/<int:id>/reactivar', methods=['POST'])
@login_required
def reactivar_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    paciente.activo = True
    db.session.commit()
    registrar_auditoria('REACTIVAR', 'Pacientes', f'Paciente reactivado: {paciente.nombre}')
    flash(f'Paciente {paciente.nombre} reactivado correctamente.', 'success')
    return redirect(url_for('main.lista_pacientes'))


@main.route('/paciente/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    form = PacienteForm(obj=paciente)
    campos_extra = CampoPersonalizado.query.filter_by(activo=True).order_by(
        CampoPersonalizado.orden).all()
    if form.validate_on_submit():
        # Verificar duplicado (excluyendo el propio paciente)
        existente = Paciente.query.filter(
            Paciente.identificacion == form.identificacion.data,
            Paciente.id != id
        ).first()
        if existente:
            flash(f'Ya existe otro paciente con la identificación {form.identificacion.data}.', 'danger')
            return render_template('paciente/editar.html', form=form, paciente=paciente,
                                   campos_extra=campos_extra)
        try:
            paciente.nombre           = form.nombre.data
            paciente.identificacion   = form.identificacion.data
            paciente.sexo             = form.sexo.data
            paciente.fecha_nacimiento = form.fecha_nacimiento.data
            paciente.telefono         = form.telefono.data
            paciente.email            = form.email.data
            paciente.direccion        = form.direccion.data
            db.session.commit()
            _guardar_campos_extra(paciente)
            registrar_auditoria('EDITAR', 'Pacientes', f'Paciente editado: {paciente.nombre}')
            flash('Paciente actualizado exitosamente', 'success')
            return redirect(url_for('main.lista_pacientes'))
        except Exception:
            db.session.rollback()
            flash('Error al actualizar el paciente.', 'danger')
    return render_template('paciente/editar.html', form=form, paciente=paciente,
                           campos_extra=campos_extra)


@main.route('/paciente/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    nombre = paciente.nombre
    try:
        from .models import HistoriaClinica, HistoriaEntrada, Cita, ValorCampoPersonalizado
        # 1. Campos personalizados
        ValorCampoPersonalizado.query.filter_by(paciente_id=id).delete()
        # 2. Entradas e historia clínica
        historia = HistoriaClinica.query.filter_by(paciente_id=id).first()
        if historia:
            HistoriaEntrada.query.filter_by(historia_id=historia.id).delete()
            db.session.delete(historia)
        # 3. Citas
        Cita.query.filter_by(paciente_id=id).delete()
        # 4. Paciente
        db.session.delete(paciente)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Pacientes', f'Paciente eliminado: {nombre}')
        flash(f'Paciente {nombre} eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'No se pudo eliminar el paciente: {e}', 'danger')
    return redirect(url_for('main.lista_pacientes'))


@main.route('/paciente/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    paciente.activo = not paciente.activo
    estado = 'activado' if paciente.activo else 'desactivado'
    db.session.commit()
    registrar_auditoria('TOGGLE', 'Pacientes', f'Paciente {estado}: {paciente.nombre}')
    flash(f'Paciente {paciente.nombre} {estado} correctamente.', 'success')
    return redirect(url_for('main.lista_pacientes'))


# ============================================================
# USUARIOS (ADMIN)
# ============================================================
def _solo_admin():
    if current_user.rol is None or current_user.rol.nombre != 'admin':
        flash('Acceso denegado', 'danger')
        return False
    return True


@main.route('/usuarios', methods=['GET', 'POST'])
@login_required
def lista_usuarios():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))

    form = UsuarioForm()
    form.rol_id.choices = [(r.id, r.nombre) for r in Rol.query.all()]

    if form.validate_on_submit():
        if Usuario.query.filter_by(email=form.email.data).first():
            flash('El correo ya está registrado', 'warning')
        else:
            u = Usuario(
                nombre=form.nombre.data, email=form.email.data,
                password=generate_password_hash('123456'),
                rol_id=form.rol_id.data, activo=True, password_cambiada=False
            )
            db.session.add(u)
            db.session.commit()
            registrar_auditoria('CREAR', 'Usuarios', f'Usuario creado: {u.email}')
            flash('Usuario creado. Contraseña temporal: 123456', 'info')
            return redirect(url_for('main.lista_usuarios'))

    usuarios = Usuario.query.join(Rol).order_by(Rol.nombre, Usuario.nombre).all()
    return render_template('admin/usuarios.html', usuarios=usuarios, form=form)


@main.route('/usuario/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    usuario = Usuario.query.get_or_404(id)
    form = UsuarioForm(obj=usuario)
    form.rol_id.choices = [(r.id, r.nombre) for r in Rol.query.all()]
    if form.validate_on_submit():
        existing = Usuario.query.filter_by(email=form.email.data).first()
        if existing and existing.id != usuario.id:
            flash('El correo ya está registrado en otro usuario', 'warning')
        else:
            usuario.nombre  = form.nombre.data
            usuario.email   = form.email.data
            usuario.rol_id  = form.rol_id.data
            db.session.commit()
            registrar_auditoria('EDITAR', 'Usuarios', f'Usuario editado: {usuario.email}')
            flash('Usuario actualizado exitosamente', 'success')
            return redirect(url_for('main.lista_usuarios'))
    return render_template('admin/editar_usuario.html', form=form, usuario=usuario)


@main.route('/usuario/<int:id>/toggle-activo', methods=['POST'])
@login_required
def toggle_usuario_activo(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    usuario = Usuario.query.get_or_404(id)
    usuario.activo = not usuario.activo
    db.session.commit()
    accion = 'ACTIVAR' if usuario.activo else 'DESACTIVAR'
    registrar_auditoria(accion, 'Usuarios', f'Usuario {accion.lower()}: {usuario.email}')
    flash(f'Usuario {"activado" if usuario.activo else "inactivado"}', 'info')
    return redirect(url_for('main.lista_usuarios'))


@main.route('/usuario/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_usuario(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    usuario = Usuario.query.get_or_404(id)
    registrar_auditoria('ELIMINAR', 'Usuarios', f'Usuario eliminado: {usuario.email}')
    db.session.delete(usuario)
    db.session.commit()
    flash('Usuario eliminado permanentemente', 'info')
    return redirect(url_for('main.lista_usuarios'))


@main.route('/usuario/<int:id>/resetear-password', methods=['POST'])
@login_required
def resetear_password_usuario(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    usuario = Usuario.query.get_or_404(id)
    usuario.password          = generate_password_hash('123456')
    usuario.password_cambiada = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta   = None
    db.session.commit()
    registrar_auditoria('RESET_PASSWORD', 'Usuarios', f'Contraseña restablecida: {usuario.email}')
    flash(f'Contraseña de {usuario.nombre} restablecida a: 123456', 'info')
    return redirect(url_for('main.lista_usuarios'))


@main.route('/usuario/<int:id>/desbloquear', methods=['POST'])
@login_required
def desbloquear_usuario(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    usuario = Usuario.query.get_or_404(id)
    usuario.bloqueado_hasta   = None
    usuario.intentos_fallidos = 0
    db.session.commit()
    registrar_auditoria('DESBLOQUEAR', 'Usuarios', f'Usuario desbloqueado: {usuario.email}')
    flash(f'Usuario {usuario.nombre} desbloqueado exitosamente', 'success')
    return redirect(url_for('main.lista_usuarios'))


# ============================================================
# ESPECIALIDADES
# ============================================================
@main.route('/especialidades', methods=['GET', 'POST'])
@login_required
def lista_especialidades():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    form = EspecialidadForm()
    if form.validate_on_submit():
        if Especialidad.query.filter_by(nombre=form.nombre.data).first():
            flash('La especialidad ya existe', 'warning')
        else:
            esp = Especialidad(nombre=form.nombre.data)
            db.session.add(esp)
            db.session.commit()
            registrar_auditoria('CREAR', 'Especialidades', f'Especialidad creada: {esp.nombre}')
            flash('Especialidad creada', 'success')
            return redirect(url_for('main.lista_especialidades'))
    especialidades = Especialidad.query.all()
    return render_template('admin/especialidades.html', especialidades=especialidades, form=form)


@main.route('/especialidad/<int:id>/editar', methods=['POST'])
@login_required
def editar_especialidad(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    especialidad = Especialidad.query.get_or_404(id)
    nombre_nuevo = request.form.get('nombre', '').strip()
    if not nombre_nuevo:
        flash('El nombre es requerido', 'danger')
        return redirect(url_for('main.lista_especialidades'))
    existe = Especialidad.query.filter(Especialidad.nombre == nombre_nuevo, Especialidad.id != id).first()
    if existe:
        flash('Ya existe una especialidad con ese nombre', 'warning')
        return redirect(url_for('main.lista_especialidades'))
    especialidad.nombre = nombre_nuevo
    db.session.commit()
    registrar_auditoria('EDITAR', 'Especialidades', f'Especialidad editada: {nombre_nuevo}')
    flash(f'Especialidad actualizada: {nombre_nuevo}', 'success')
    return redirect(url_for('main.lista_especialidades'))


@main.route('/especialidad/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_especialidad(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    especialidad = Especialidad.query.get_or_404(id)
    if especialidad.citas:
        flash(f'No se puede eliminar: tiene {len(especialidad.citas)} cita(s) asociada(s)', 'danger')
        return redirect(url_for('main.lista_especialidades'))
    nombre = especialidad.nombre
    db.session.delete(especialidad)
    db.session.commit()
    registrar_auditoria('ELIMINAR', 'Especialidades', f'Especialidad eliminada: {nombre}')
    flash(f'Especialidad "{nombre}" eliminada', 'info')
    return redirect(url_for('main.lista_especialidades'))


# ============================================================
# ROLES
# ============================================================
@main.route('/roles', methods=['GET', 'POST'])
@login_required
def lista_roles():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    form = RolForm()
    if form.validate_on_submit():
        if Rol.query.filter_by(nombre=form.nombre.data).first():
            flash('El rol ya existe', 'warning')
        else:
            rol = Rol(nombre=form.nombre.data, descripcion=form.descripcion.data)
            db.session.add(rol)
            db.session.commit()
            flash('Rol creado exitosamente', 'success')
            return redirect(url_for('main.lista_roles'))
    roles = Rol.query.all()
    return render_template('admin/roles.html', roles=roles, form=form)


@main.route('/rol/<int:id>/editar', methods=['POST'])
@login_required
def editar_rol(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    rol = Rol.query.get_or_404(id)
    nombre_nuevo = request.form.get('nombre', '').strip()
    if not nombre_nuevo:
        flash('El nombre es requerido', 'danger')
        return redirect(url_for('main.lista_roles'))
    existe = Rol.query.filter(Rol.nombre == nombre_nuevo, Rol.id != id).first()
    if existe:
        flash('Ya existe un rol con ese nombre', 'warning')
        return redirect(url_for('main.lista_roles'))
    rol.nombre      = nombre_nuevo
    rol.descripcion = request.form.get('descripcion', '').strip()
    db.session.commit()
    flash(f'Rol actualizado: {nombre_nuevo}', 'success')
    return redirect(url_for('main.lista_roles'))


@main.route('/rol/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_rol(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    rol = Rol.query.get_or_404(id)
    if rol.usuarios:
        flash(f'No se puede eliminar: tiene {len(rol.usuarios)} usuario(s)', 'danger')
        return redirect(url_for('main.lista_roles'))
    nombre = rol.nombre
    db.session.delete(rol)
    db.session.commit()
    flash(f'Rol "{nombre}" eliminado', 'info')
    return redirect(url_for('main.lista_roles'))


# ============================================================
# CAMPOS PERSONALIZADOS DE PACIENTE (ADMIN)
# ============================================================
@main.route('/admin/campos', methods=['GET', 'POST'])
@login_required
def campos_personalizados():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        accion   = request.form.get('accion')
        campo_id = request.form.get('campo_id')

        if accion == 'crear':
            nombre = request.form.get('nombre', '').strip()
            tipo   = request.form.get('tipo', 'texto')
            if not nombre:
                flash('El nombre es obligatorio', 'danger')
                return redirect(url_for('main.campos_personalizados'))
            import re, unicodedata
            clave = unicodedata.normalize('NFD', nombre.lower())
            clave = clave.encode('ascii', 'ignore').decode('ascii')
            clave = re.sub(r'[^a-z0-9]+', '_', clave).strip('_')
            base_clave = clave
            i = 1
            while CampoPersonalizado.query.filter_by(clave=clave).first():
                clave = f'{base_clave}_{i}'
                i += 1
            campo = CampoPersonalizado(
                nombre      = nombre,
                clave       = clave,
                tipo        = tipo,
                opciones    = request.form.get('opciones', '').strip() or None,
                obligatorio = 'obligatorio' in request.form,
                orden       = int(request.form.get('orden', 0) or 0),
            )
            db.session.add(campo)
            db.session.commit()
            flash(f'Campo "{nombre}" creado exitosamente', 'success')

        elif accion == 'editar' and campo_id:
            campo = CampoPersonalizado.query.get_or_404(int(campo_id))
            nombre = request.form.get('nombre', '').strip()
            if not nombre:
                flash('El nombre es obligatorio', 'danger')
                return redirect(url_for('main.campos_personalizados'))
            campo.nombre      = nombre
            campo.tipo        = request.form.get('tipo', 'texto')
            campo.opciones    = request.form.get('opciones', '').strip() or None
            campo.obligatorio = 'obligatorio' in request.form
            campo.orden       = int(request.form.get('orden', 0) or 0)
            db.session.commit()
            flash(f'Campo "{nombre}" actualizado', 'success')

        elif accion == 'eliminar' and campo_id:
            campo = CampoPersonalizado.query.get_or_404(int(campo_id))
            ValorCampoPersonalizado.query.filter_by(campo_id=campo.id).delete()
            db.session.delete(campo)
            db.session.commit()
            flash(f'Campo "{campo.nombre}" eliminado', 'info')

        elif accion == 'toggle' and campo_id:
            campo = CampoPersonalizado.query.get_or_404(int(campo_id))
            campo.activo = not campo.activo
            db.session.commit()
            flash(f'Campo "{campo.nombre}" {"activado" if campo.activo else "desactivado"}', 'info')

        return redirect(url_for('main.campos_personalizados'))

    campos = CampoPersonalizado.query.order_by(
        CampoPersonalizado.orden, CampoPersonalizado.id).all()
    return render_template('admin/campos_personalizados.html', campos=campos)


# ============================================================
# CITAS
# ============================================================
@main.route('/citas')
@login_required
def lista_citas():
    q = request.args.get('q', '').strip()
    if q:
        citas = Cita.query.join(Paciente).join(Usuario, Cita.medico_id == Usuario.id).join(Especialidad).filter(
            db.or_(
                Paciente.nombre.contains(q), Paciente.identificacion.contains(q),
                Usuario.nombre.contains(q), Especialidad.nombre.contains(q)
            )
        ).order_by(Cita.fecha.desc()).all()
    else:
        citas = Cita.query.order_by(Cita.fecha.desc()).all()
    return render_template('cita/citas.html', citas=citas)


@main.route('/cita/nueva', methods=['GET', 'POST'])
@login_required
def crear_cita():
    form = CitaForm()
    form.paciente_id.choices    = [(p.id, f"{p.nombre} ({p.identificacion})") for p in Paciente.query.filter_by(activo=True).all()]
    form.medico_id.choices      = [(u.id, u.nombre) for u in Usuario.query.join(Rol).filter(Rol.nombre == 'medico', Usuario.activo == True).all()]
    form.especialidad_id.choices= [(e.id, e.nombre) for e in Especialidad.query.filter_by(activo=True).all()]
    if form.validate_on_submit():
        cita = Cita(
            paciente_id=form.paciente_id.data, medico_id=form.medico_id.data,
            especialidad_id=form.especialidad_id.data, fecha=form.fecha.data,
            estado='Pendiente', creado_por_id=current_user.id
        )
        db.session.add(cita)
        db.session.commit()
        registrar_auditoria('CREAR', 'Citas', f'Cita creada para paciente ID {cita.paciente_id}')
        flash('Cita agendada exitosamente', 'success')
        return redirect(url_for('main.lista_citas'))
    return render_template('cita/crear.html', form=form)


@main.route('/cita/<int:id>/realizada', methods=['GET', 'POST'])
@login_required
def marcar_cita_realizada(id):
    cita = Cita.query.get_or_404(id)
    cita.estado = 'Realizada'
    db.session.commit()
    registrar_auditoria('ACTUALIZAR', 'Citas', f'Cita {id} marcada como Realizada')
    flash('Cita marcada como realizada', 'success')
    return redirect(url_for('main.lista_citas'))


@main.route('/cita/<int:id>/confirmar', methods=['POST'])
@login_required
def confirmar_cita(id):
    """Confirma una cita solicitada, asigna médico automáticamente y envía tiquete al paciente."""
    cita = Cita.query.get_or_404(id)

    fecha_str  = request.form.get('fecha_confirmada', '').strip()
    hora_str   = request.form.get('hora_confirmada', '').strip()

    if not fecha_str or not hora_str:
        flash('Debes indicar fecha y hora para confirmar la cita.', 'danger')
        return redirect(url_for('main.lista_citas'))

    try:
        fecha_dt = datetime.strptime(f'{fecha_str} {hora_str}', '%Y-%m-%d %H:%M')
    except ValueError:
        flash('Formato de fecha u hora inválido.', 'danger')
        return redirect(url_for('main.lista_citas'))

    # Auto-asignar médico: el de la especialidad con menos citas pendientes
    if not cita.medico_id:
        from sqlalchemy import func
        medicos = (Usuario.query
            .join(Rol)
            .filter(Rol.nombre.in_(['medico', 'médico']), Usuario.activo == True)
            .all())
        # Filtrar por especialidad si el médico tiene relación
        mejor = None
        menor_citas = float('inf')
        for m in medicos:
            citas_m = Cita.query.filter(
                Cita.medico_id == m.id,
                Cita.especialidad_id == cita.especialidad_id,
                Cita.estado.in_(['Pendiente', 'Confirmada'])
            ).count()
            if citas_m < menor_citas:
                menor_citas = citas_m
                mejor = m
        if mejor:
            cita.medico_id = mejor.id

    cita.estado = 'Confirmada'
    cita.fecha  = fecha_dt
    db.session.commit()

    # Generar tiquete y enviar correo al paciente
    try:
        pdf = generar_tiquete_pdf(cita)
        subir_pdf_drive(f'tiquete_cita_{id}_{cita.paciente.identificacion}.pdf', pdf, subcarpeta='tiquetes')
        if cita.paciente.email:
            from .correo_service import enviar_cita_confirmada
            enviar_cita_confirmada(
                email_paciente   = cita.paciente.email,
                nombre_paciente  = cita.paciente.nombre,
                medico           = cita.medico.nombre if cita.medico else 'Por asignar',
                especialidad     = cita.especialidad.nombre,
                fecha_hora       = fecha_dt.strftime('%d/%m/%Y a las %H:%M'),
                pdf_bytes        = pdf,
                cita_id          = cita.id
            )
    except Exception as e:
        print(f"Error enviando confirmación: {e}")

    registrar_auditoria('CONFIRMAR', 'Citas', f'Cita {id} confirmada — paciente {cita.paciente.nombre}')
    flash(f'Cita confirmada. Se envió tiquete a {cita.paciente.email or "paciente"}.', 'success')
    return redirect(url_for('main.lista_citas'))


@main.route('/cita/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_cita(id):
    cita   = Cita.query.get_or_404(id)
    motivo = request.form.get('motivo', '').strip()
    cita.estado = 'Cancelada'
    db.session.commit()
    if cita.paciente.email:
        try:
            from .correo_service import enviar_cita_cancelada
            enviar_cita_cancelada(
                email_paciente      = cita.paciente.email,
                nombre_paciente     = cita.paciente.nombre,
                especialidad        = cita.especialidad.nombre,
                motivo_cancelacion  = motivo
            )
        except Exception as e:
            print(f"Error enviando cancelación: {e}")
    registrar_auditoria('CANCELAR', 'Citas', f'Cita {id} cancelada')
    flash('Cita cancelada. Se notificó al paciente.', 'warning')
    return redirect(url_for('main.lista_citas'))


@main.route('/cita/<int:id>/eliminar', methods=['GET', 'POST'])
@login_required
def eliminar_cita(id):
    cita = Cita.query.get_or_404(id)
    db.session.delete(cita)
    db.session.commit()
    registrar_auditoria('ELIMINAR', 'Citas', f'Cita {id} eliminada')
    flash('Cita eliminada', 'info')
    return redirect(url_for('main.lista_citas'))


# ============================================================
# SOLICITUD PÚBLICA DE CITA (sin login)
# ============================================================
@main.route('/solicitar-cita', methods=['GET', 'POST'])
def solicitar_cita_publica():
    from .models import Especialidad, CodigoVerificacion, CorreoBackup
    especialidades = Especialidad.query.filter_by(activo=True).all()

    if request.method == 'POST':
        paso        = request.form.get('paso', '1')
        nombre      = request.form.get('nombre', '').strip()
        cedula      = request.form.get('cedula', '').strip()
        telefono    = request.form.get('telefono', '').strip()
        email       = request.form.get('email', '').strip()
        esp_id      = request.form.get('especialidad_id', '')
        fecha_pref  = request.form.get('fecha_preferida', '').strip()
        motivo      = request.form.get('motivo', '').strip()

        # ── PASO 1: validar datos y enviar código ──
        if paso == '1':
            if not all([nombre, cedula, email, esp_id]):
                flash('Completa todos los campos obligatorios.', 'danger')
                return render_template('cita/solicitar_publica.html',
                                       especialidades=especialidades, paso=1)
            from .correo_service import generar_codigo, enviar_codigo_validacion_correo
            codigo = generar_codigo()
            expira = datetime.utcnow() + timedelta(minutes=10)
            db.session.add(CodigoVerificacion(
                email=email, codigo=codigo, tipo='solicitud_cita', expira_en=expira))
            db.session.commit()
            enviar_codigo_validacion_correo(email, codigo)
            return render_template('cita/solicitar_publica.html',
                                   especialidades=especialidades, paso=2,
                                   nombre=nombre, cedula=cedula, telefono=telefono,
                                   email=email, esp_id=esp_id,
                                   fecha_pref=fecha_pref, motivo=motivo)

        # ── PASO 2: verificar código y crear cita ──
        if paso == '2':
            codigo_ingresado = request.form.get('codigo', '').strip()
            registro = CodigoVerificacion.query.filter_by(
                email=email, tipo='solicitud_cita', usado=False
            ).order_by(CodigoVerificacion.creado_en.desc()).first()

            if not registro or not registro.esta_vigente():
                flash('Código expirado. Vuelve a intentarlo.', 'danger')
                return render_template('cita/solicitar_publica.html',
                                       especialidades=especialidades, paso=1)

            if registro.codigo != codigo_ingresado:
                flash('Código incorrecto.', 'danger')
                return render_template('cita/solicitar_publica.html',
                                       especialidades=especialidades, paso=2,
                                       nombre=nombre, cedula=cedula, telefono=telefono,
                                       email=email, esp_id=esp_id,
                                       fecha_pref=fecha_pref, motivo=motivo)

            registro.usado = True

            # Buscar o crear paciente
            paciente = Paciente.query.filter_by(identificacion=cedula).first()
            if not paciente:
                paciente = Paciente(
                    nombre=nombre, identificacion=cedula,
                    telefono=telefono, email=email, activo=True
                )
                db.session.add(paciente)
                db.session.flush()

            # Auto-asignar médico con menos citas de esa especialidad
            medico_id = None
            try:
                medicos = (Usuario.query.join(Rol)
                    .filter(Rol.nombre.in_(['medico', 'médico']), Usuario.activo == True)
                    .all())
                mejor, menor = None, float('inf')
                for m in medicos:
                    cnt = Cita.query.filter(
                        Cita.medico_id == m.id,
                        Cita.especialidad_id == int(esp_id),
                        Cita.estado.in_(['Pendiente', 'Confirmada'])
                    ).count()
                    if cnt < menor:
                        menor, mejor = cnt, m
                if mejor:
                    medico_id = mejor.id
            except Exception:
                pass

            # Fecha preferida
            fecha_dt = None
            if fecha_pref:
                try:
                    fecha_dt = datetime.strptime(fecha_pref, '%Y-%m-%d')
                except Exception:
                    pass

            cita = Cita(
                paciente_id     = paciente.id,
                medico_id       = medico_id,
                especialidad_id = int(esp_id),
                fecha           = fecha_dt or datetime.utcnow() + timedelta(days=1),
                estado          = 'Solicitada',
                motivo_consulta = motivo,
            )
            db.session.add(cita)
            db.session.commit()

            # Correo al paciente
            try:
                esp = Especialidad.query.get(int(esp_id))
                from .correo_service import enviar_confirmacion_solicitud
                enviar_confirmacion_solicitud(
                    email_paciente = email,
                    nombre_paciente= nombre,
                    especialidad   = esp.nombre if esp else esp_id,
                    fecha_preferida= fecha_pref,
                    motivo         = motivo
                )
            except Exception as e:
                print(f"Error correo paciente: {e}")

            # Correo a correos del sistema
            try:
                from .correo_service import enviar_notificacion_nueva_solicitud
                from .models import CorreoBackup
                correos_sistema = [c.email for c in CorreoBackup.query.filter_by(verificado=True).all()]
                if correos_sistema:
                    url_sistema = request.host_url + 'citas'
                    enviar_notificacion_nueva_solicitud(
                        emails_sistema  = correos_sistema,
                        nombre_paciente = nombre,
                        cedula          = cedula,
                        especialidad    = esp.nombre if esp else esp_id,
                        fecha_preferida = fecha_pref,
                        motivo          = motivo,
                        url_sistema     = url_sistema
                    )
            except Exception as e:
                print(f"Error correo sistema: {e}")

            return render_template('cita/solicitar_publica.html',
                                   especialidades=especialidades, paso=3,
                                   nombre=nombre, email=email)

    return render_template('cita/solicitar_publica.html',
                           especialidades=especialidades, paso=1,
                           now=datetime.now())


@main.route('/cita/<int:id>/tiquete')
@login_required
def tiquete_cita(id):
    cita = Cita.query.get_or_404(id)
    pdf = generar_tiquete_pdf(cita)
    subir_pdf_drive(f'tiquete_cita_{id}_{cita.paciente.identificacion}.pdf', pdf, subcarpeta='tiquetes')
    response = make_response(pdf)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=tiquete_cita_{id}.pdf'
    return response


# ============================================================
# HISTORIA CLÍNICA  (bloqueo en edición — Opción 2)
# ============================================================
@main.route('/paciente/<int:id>/historia', methods=['GET', 'POST'])
@login_required
def historia_clinica(id):
    paciente = Paciente.query.get_or_404(id)
    historia = HistoriaClinica.query.filter_by(paciente_id=id).first()
    if not historia:
        historia = HistoriaClinica(paciente_id=id)
        db.session.add(historia)
        db.session.commit()

    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        if not contenido:
            flash('El contenido no puede estar vacío', 'danger')
            return redirect(url_for('main.historia_clinica', id=id))

        # Verificar bloqueo por otro usuario
        if historia.esta_bloqueada() and historia.bloqueado_por_id != current_user.id:
            flash(f'La historia clínica está siendo editada por {historia.bloqueado_por.nombre}. Intenta en unos minutos.', 'warning')
            return redirect(url_for('main.historia_clinica', id=id))

        entrada = HistoriaEntrada(
            historia_id=historia.id, autor_id=current_user.id, contenido=contenido
        )
        db.session.add(entrada)
        historia.liberar()
        historia.ultima_actualizacion = datetime.utcnow()
        historia.actualizado_por_id   = current_user.id
        db.session.commit()
        registrar_auditoria('CREAR', 'HistoriaClinica', f'Entrada agregada — paciente {paciente.nombre}')
        flash('Entrada agregada a la historia clínica', 'success')
        return redirect(url_for('main.historia_clinica', id=id))

    entradas = HistoriaEntrada.query.filter_by(historia_id=historia.id).order_by(HistoriaEntrada.fecha.desc()).all()
    return render_template('historia/historia_clinica.html',
                           paciente=paciente, historia=historia, entradas=entradas,
                           now=datetime.now())


@main.route('/historia/<int:historia_id>/bloquear', methods=['POST'])
@login_required
def bloquear_historia(historia_id):
    """Bloquea la historia cuando el usuario empieza a escribir."""
    historia = HistoriaClinica.query.get_or_404(historia_id)
    if not historia.esta_bloqueada():
        historia.bloquear(current_user.id)
        db.session.commit()
    return jsonify({'ok': True})


@main.route('/historia/<int:historia_id>/liberar', methods=['POST'])
@login_required
def liberar_historia(historia_id):
    """Libera el bloqueo cuando el usuario cancela o sale."""
    historia = HistoriaClinica.query.get_or_404(historia_id)
    if historia.bloqueado_por_id == current_user.id:
        historia.liberar()
        db.session.commit()
    return jsonify({'ok': True})


@main.route('/paciente/<int:id>/historia/entrada/<int:entrada_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_entrada_historia(id, entrada_id):
    """Edita una entrada existente de la historia clinica."""
    paciente = Paciente.query.get_or_404(id)
    entrada  = HistoriaEntrada.query.get_or_404(entrada_id)

    # Solo el autor puede editar
    if entrada.autor_id != current_user.id:
        flash('Solo el autor puede editar esta entrada', 'danger')
        return redirect(url_for('main.historia_clinica', id=id))

    if request.method == 'POST':
        nuevo_contenido = request.form.get('contenido', '').strip()
        if not nuevo_contenido:
            flash('El contenido no puede estar vacio', 'danger')
            return redirect(url_for('main.editar_entrada_historia', id=id, entrada_id=entrada_id))

        # Guardar version anterior antes de editar
        historia = entrada.historia
        version = HistoriaVersion(
            historia_id        = historia.id,
            contenido          = entrada.contenido,   # guarda el contenido ANTES del cambio
            actualizado_por_id = current_user.id,
            fecha              = datetime.utcnow()
        )
        db.session.add(version)

        entrada.contenido = nuevo_contenido
        db.session.commit()
        registrar_auditoria('EDITAR', 'HistoriaClinica', f'Entrada editada — paciente {paciente.nombre}')
        flash('Entrada actualizada correctamente', 'success')
        return redirect(url_for('main.historia_clinica', id=id))

    return render_template('historia/editar_entrada.html', paciente=paciente, entrada=entrada)


@main.route('/paciente/<int:id>/historia/entrada/<int:entrada_id>/eliminar', methods=['POST'])
@login_required
def eliminar_entrada_historia(id, entrada_id):
    """Elimina una entrada de la historia clinica."""
    paciente = Paciente.query.get_or_404(id)
    entrada  = HistoriaEntrada.query.get_or_404(entrada_id)

    # Solo el autor puede eliminar
    if entrada.autor_id != current_user.id:
        flash('Solo el autor puede eliminar esta entrada', 'danger')
        return redirect(url_for('main.historia_clinica', id=id))

    # Eliminar versiones asociadas primero
    HistoriaVersion.query.filter_by(entrada_id=entrada.id).delete()
    db.session.delete(entrada)
    db.session.commit()
    registrar_auditoria('ELIMINAR', 'HistoriaClinica', f'Entrada eliminada — paciente {paciente.nombre}')
    flash('Entrada eliminada correctamente', 'success')
    return redirect(url_for('main.historia_clinica', id=id))


@main.route('/paciente/<int:id>/historia/imprimir')
@login_required
def imprimir_historia(id):
    from datetime import date as _d, datetime as _dt
    paciente = Paciente.query.get_or_404(id)
    historia = HistoriaClinica.query.filter_by(paciente_id=id).first()
    entradas = []
    solo_recientes = False

    if historia:
        solo_recientes = request.args.get('solo_recientes', '0') == '1'
        fecha_inicio   = request.args.get('fecha_inicio', '').strip()
        fecha_fin      = request.args.get('fecha_fin', '').strip()

        q = HistoriaEntrada.query.filter_by(historia_id=historia.id)
        if fecha_inicio:
            try: q = q.filter(HistoriaEntrada.fecha >= _dt.strptime(fecha_inicio, '%Y-%m-%d'))
            except: pass
        if fecha_fin:
            try: q = q.filter(HistoriaEntrada.fecha <= _dt.strptime(fecha_fin + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
            except: pass
        elif solo_recientes:
            q = q.filter(HistoriaEntrada.fecha >= datetime.now() - timedelta(days=30))
        entradas = q.order_by(HistoriaEntrada.fecha.desc()).all()

    edad = None
    if paciente.fecha_nacimiento:
        try:
            fn = paciente.fecha_nacimiento
            if isinstance(fn, str): fn = _dt.strptime(fn[:10], '%Y-%m-%d').date()
            elif hasattr(fn, 'date'): fn = fn.date()
            today = _d.today()
            edad = today.year - fn.year
            if today < fn.replace(year=today.year): edad -= 1
            if edad is not None and (edad < 0 or edad > 120): edad = None
        except: edad = None

    fecha_gen = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    _logo = os.path.join(os.path.dirname(__file__), 'static', 'favicon.ico')
    pdf = generar_historia_pdf(paciente, historia, entradas, fecha_gen, edad, solo_recientes, logo_path=_logo)
    nombre_pac = paciente.nombre.replace(' ', '_')
    subir_pdf_drive(f'HC_{nombre_pac}_{paciente.identificacion}.pdf', pdf, subcarpeta='historias')
    response = make_response(pdf)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=historia_{paciente.identificacion}.pdf'
    registrar_auditoria('EXPORTAR', 'HistoriaClinica', f'PDF historia clínica — {paciente.nombre}')
    return response


@main.route('/paciente/<int:id>/historia/descargar')
@login_required
def descargar_historia(id):
    from datetime import date as _d, datetime as _dt
    paciente = Paciente.query.get_or_404(id)
    historia = HistoriaClinica.query.filter_by(paciente_id=id).first()
    entradas = []
    solo_recientes = False

    if historia:
        solo_recientes = request.args.get('solo_recientes', '0') == '1'
        fecha_inicio   = request.args.get('fecha_inicio', '').strip()
        fecha_fin      = request.args.get('fecha_fin', '').strip()

        q = HistoriaEntrada.query.filter_by(historia_id=historia.id)
        if fecha_inicio:
            try: q = q.filter(HistoriaEntrada.fecha >= _dt.strptime(fecha_inicio, '%Y-%m-%d'))
            except: pass
        if fecha_fin:
            try: q = q.filter(HistoriaEntrada.fecha <= _dt.strptime(fecha_fin + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
            except: pass
        elif solo_recientes:
            q = q.filter(HistoriaEntrada.fecha >= datetime.now() - timedelta(days=30))
        entradas = q.order_by(HistoriaEntrada.fecha.desc()).all()

    edad = None
    if paciente.fecha_nacimiento:
        try:
            fn = paciente.fecha_nacimiento
            if isinstance(fn, str): fn = _dt.strptime(fn[:10], '%Y-%m-%d').date()
            elif hasattr(fn, 'date'): fn = fn.date()
            today = _d.today()
            edad = today.year - fn.year
            if today < fn.replace(year=today.year): edad -= 1
            if edad is not None and (edad < 0 or edad > 120): edad = None
        except: edad = None

    fecha_gen = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    _logo = os.path.join(os.path.dirname(__file__), 'static', 'favicon.ico')
    pdf = generar_historia_pdf(paciente, historia, entradas, fecha_gen, edad, solo_recientes, logo_path=_logo)
    nombre_pac = paciente.nombre.replace(' ', '_')
    subir_pdf_drive(f'HC_{nombre_pac}_{paciente.identificacion}.pdf', pdf, subcarpeta='historias')
    response = make_response(pdf)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=historia_{nombre_pac}_{paciente.identificacion}.pdf'
    registrar_auditoria('DESCARGAR', 'HistoriaClinica', f'Descarga PDF — {paciente.nombre}')
    return response


@main.route('/paciente/<int:id>/historia/version/<int:version_id>')
@login_required
def ver_version_historia(id, version_id):
    paciente = Paciente.query.get_or_404(id)
    version  = HistoriaVersion.query.get_or_404(version_id)
    if version.historia.paciente_id != id:
        flash('Versión no encontrada', 'danger')
        return redirect(url_for('main.historia_clinica', id=id))
    return render_template('historia/ver_version.html', paciente=paciente, version=version)


# ============================================================
# REPORTES
# ============================================================
@main.route('/reportes')
@login_required
def menu_reportes():
    stats = {
        'total_pacientes':  Paciente.query.filter_by(activo=True).count(),
        'total_citas':      Cita.query.count(),
        'total_especialidades': Especialidad.query.count(),
        'citas_pendientes': Cita.query.filter_by(estado='Pendiente').count()
    }
    return render_template('reporte/menu_reportes.html', stats=stats)


@main.route('/reporte/pacientes.pdf')
@login_required
def reporte_pacientes_pdf():
    fi = request.args.get('fecha_inicio', '').strip()
    ff = request.args.get('fecha_fin', '').strip()
    q = Paciente.query
    if fi:
        try: q = q.filter(Paciente.creado_en >= datetime.strptime(fi, '%Y-%m-%d'))
        except: pass
    if ff:
        try: q = q.filter(Paciente.creado_en <= datetime.strptime(ff + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except: pass
    pacientes  = q.all()
    fecha_gen  = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    if fi or ff:
        fecha_gen += f'  |  Período: {fi or "inicio"} → {ff or "hoy"}'
    pdf = generar_pacientes_pdf(pacientes, fecha_gen)
    subir_pdf_drive(f'reporte_pacientes_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf', pdf, subcarpeta='reportes')
    response = make_response(pdf)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=reporte_pacientes.pdf'
    registrar_auditoria('EXPORTAR', 'Reportes', 'Reporte PDF pacientes')
    return response


@main.route('/reporte/citas.pdf')
@login_required
def reporte_citas_pdf():
    fi = request.args.get('fecha_inicio', '').strip()
    ff = request.args.get('fecha_fin', '').strip()
    q = Cita.query
    if fi:
        try: q = q.filter(Cita.fecha >= datetime.strptime(fi, '%Y-%m-%d'))
        except: pass
    if ff:
        try: q = q.filter(Cita.fecha <= datetime.strptime(ff + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except: pass
    citas     = q.order_by(Cita.fecha.desc()).all()
    fecha_gen = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    if fi or ff:
        fecha_gen += f'  |  Período: {fi or "inicio"} → {ff or "hoy"}'
    pdf = generar_citas_pdf(citas, fecha_gen)
    subir_pdf_drive(f'reporte_citas_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf', pdf, subcarpeta='reportes')
    response = make_response(pdf)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=reporte_citas.pdf'
    registrar_auditoria('EXPORTAR', 'Reportes', 'Reporte PDF citas')
    return response


@main.route('/reporte/especialidades.pdf')
@login_required
def reporte_especialidades_pdf():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    fi = request.args.get('fecha_inicio', '').strip()
    ff = request.args.get('fecha_fin', '').strip()
    especialidades = Especialidad.query.all()
    fecha_gen = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    if fi or ff:
        fecha_gen += f'  |  Período: {fi or "inicio"} → {ff or "hoy"}'
    pdf = generar_especialidades_pdf(especialidades, fecha_gen)
    subir_pdf_drive(f'reporte_especialidades_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf', pdf, subcarpeta='reportes')
    response = make_response(pdf)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=reporte_especialidades.pdf'
    return response


# ============================================================
# BACKUP (ADMIN)
# ============================================================
@main.route('/admin/backup')
@login_required
def admin_backup():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    backups = BackupRegistro.query.order_by(BackupRegistro.creado_en.desc()).limit(20).all()
    return render_template('admin/backup.html', backups=backups)


@main.route('/admin/backup/generar', methods=['POST'])
@login_required
def generar_backup():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))

    from .backup_service import generar_backup as _generar
    exitoso, backup_id, error = _generar(tipo='manual', usuario_id=current_user.id)

    if exitoso:
        from .models import BackupRegistro, ConfiguracionSistema
        from .correo_service import enviar_backup_por_correo
        registro     = BackupRegistro.query.get(backup_id)
        backup_email = ConfiguracionSistema.obtener('backup_email', '')
        if backup_email and registro and registro.archivo_datos:
            enviar_backup_por_correo(registro.archivo_datos, registro.archivo_nombre, backup_email)
            flash(f'✅ Backup generado y enviado a {backup_email}', 'success')
        else:
            flash('✅ Backup generado. Configura un correo en Configuración para enviarlo automáticamente.', 'success')
        registrar_auditoria('BACKUP_MANUAL', 'Backup', 'Backup generado exitosamente')
    else:
        registrar_auditoria('BACKUP_FALLIDO', 'Backup', f'Error: {error}', exitoso=False)
        flash(f'❌ Error generando backup: {error}', 'danger')

    return redirect(url_for('main.admin_backup'))

@main.route('/admin/backup/descargar/<int:backup_id>')
@login_required
def descargar_backup(backup_id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))

    import io
    from flask import send_file

    registro = BackupRegistro.query.get_or_404(backup_id)

    if not registro.archivo_datos:
        flash('❌ Este backup no tiene archivo disponible.', 'danger')
        return redirect(url_for('main.admin_backup'))

    registrar_auditoria('BACKUP_DESCARGA', 'Backup', f'Descargó backup: {registro.archivo_nombre}')

    return send_file(
        io.BytesIO(registro.archivo_datos),
        mimetype='application/zip',
        as_attachment=True,
        download_name=registro.archivo_nombre
    )


# ============================================================
# AUDITORÍA (ADMIN)
# ============================================================
@main.route('/admin/auditoria')
@login_required
def admin_auditoria():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))

    modulo    = request.args.get('modulo', '')
    accion    = request.args.get('accion', '')
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')

    query = Auditoria.query
    if modulo:
        query = query.filter(Auditoria.modulo == modulo)
    if accion:
        query = query.filter(Auditoria.accion.contains(accion))
    if fecha_ini:
        try:
            query = query.filter(Auditoria.fecha_hora >= datetime.strptime(fecha_ini, '%Y-%m-%d'))
        except:
            pass
    if fecha_fin:
        try:
            query = query.filter(Auditoria.fecha_hora <= datetime.strptime(fecha_fin + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except:
            pass

    registros = query.order_by(Auditoria.fecha_hora.desc()).limit(200).all()
    modulos   = db.session.query(Auditoria.modulo).distinct().all()
    modulos   = [m[0] for m in modulos if m[0]]

    return render_template('admin/auditoria.html', registros=registros, modulos=modulos,
                           filtro_modulo=modulo, filtro_accion=accion,
                           filtro_fecha_ini=fecha_ini, filtro_fecha_fin=fecha_fin)


# ============================================================
# VERSIÓN DEL SISTEMA
# ============================================================
@main.route('/api/version')
def api_version():
    """Endpoint para verificar la versión actual del sistema."""
    ultima = VersionSistema.query.order_by(VersionSistema.publicado_en.desc()).first()
    if ultima:
        return jsonify({
            'version':    ultima.version,
            'es_critica': ultima.es_critica,
            'descripcion':ultima.descripcion,
        })
    return jsonify({'version': '2.0.0', 'es_critica': False})


# ============================================================
# 2FA — VERIFICACIÓN DE CÓDIGO AL LOGIN
# ============================================================
@main.route('/verificar-codigo', methods=['GET', 'POST'])
def verificar_codigo():
    from .forms import CodigoVerificacionForm
    from .models import CodigoVerificacion, ConfiguracionSistema
    from .correo_service import enviar_notificacion_login

    # Debe haber un usuario pendiente en sesión
    from flask import session
    usuario_id = session.get('pendiente_2fa')
    if not usuario_id:
        return redirect(url_for('main.index'))

    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        session.pop('pendiente_2fa', None)
        return redirect(url_for('main.index'))

    # Email parcial para mostrar en pantalla
    partes = usuario.email.split('@')
    email_parcial = partes[0][:3] + '***@' + partes[1] if len(partes) == 2 else '***'

    form = CodigoVerificacionForm()
    if form.validate_on_submit():
        codigo_ingresado = form.codigo.data.strip()
        registro = CodigoVerificacion.query.filter_by(
            email=usuario.email, tipo='2fa', usado=False
        ).order_by(CodigoVerificacion.creado_en.desc()).first()

        if not registro or not registro.esta_vigente():
            flash('El código expiró. Solicita uno nuevo.', 'danger')
            return render_template('auth/verificar_codigo.html', form=form, email_parcial=email_parcial)

        if registro.codigo != codigo_ingresado:
            registrar_auditoria('2FA_FALLIDO', 'Auth', f'Código incorrecto: {usuario.email}', exitoso=False)
            flash('Código incorrecto. Intenta de nuevo.', 'danger')
            return render_template('auth/verificar_codigo.html', form=form, email_parcial=email_parcial)

        # Código correcto
        registro.usado = True
        db.session.commit()
        session.pop('pendiente_2fa', None)
        login_user(usuario)

        usuario.registrar_acceso_exitoso(ip=request.remote_addr)
        db.session.commit()

        # Notificar login por correo
        try:
            enviar_notificacion_login(
                usuario.email, usuario.nombre,
                request.remote_addr,
                datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')
            )
        except:
            pass

        registrar_auditoria('LOGIN', 'Auth', f'Acceso exitoso con 2FA: {usuario.email}')

        if not usuario.password_cambiada:
            flash('Por seguridad, debes cambiar tu contraseña.', 'info')
            return redirect(url_for('main.cambiar_password'))

        flash(f'Bienvenido {usuario.nombre}', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/verificar_codigo.html', form=form, email_parcial=email_parcial)


@main.route('/reenviar-codigo')
def reenviar_codigo():
    from flask import session
    from .models import CodigoVerificacion, ConfiguracionSistema
    from .correo_service import generar_codigo, enviar_codigo_2fa

    usuario_id = session.get('pendiente_2fa')
    if not usuario_id:
        return redirect(url_for('main.index'))

    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return redirect(url_for('main.index'))

    codigo = generar_codigo()
    expira = datetime.utcnow() + timedelta(minutes=5)
    db.session.add(CodigoVerificacion(email=usuario.email, codigo=codigo, tipo='2fa', expira_en=expira))
    db.session.commit()

    enviar_codigo_2fa(usuario.email, usuario.nombre, codigo)
    flash('Se envió un nuevo código a tu correo.', 'info')
    return redirect(url_for('main.verificar_codigo'))


# ============================================================
# VALIDAR CORREO AL CREAR USUARIO
# ============================================================
@main.route('/usuario/validar-correo/<email>', methods=['GET', 'POST'])
@login_required
def validar_correo_usuario(email):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))

    from .forms import ValidarCorreoForm
    from .models import CodigoVerificacion
    from .correo_service import enviar_codigo_validacion_correo, generar_codigo

    form = ValidarCorreoForm()

    if request.method == 'GET':
        # Enviar código al correo
        codigo = generar_codigo()
        expira = datetime.utcnow() + timedelta(minutes=5)
        db.session.add(CodigoVerificacion(email=email, codigo=codigo, tipo='validar_correo', expira_en=expira))
        db.session.commit()
        enviado = enviar_codigo_validacion_correo(email, codigo)
        if enviado:
            flash(f'Código enviado a {email}. Pídele al dueño del correo que te lo diga.', 'info')
        else:
            flash('No se pudo enviar el correo. Verifica que la dirección sea correcta.', 'warning')

    if form.validate_on_submit():
        codigo_ingresado = form.codigo.data.strip()
        registro = CodigoVerificacion.query.filter_by(
            email=email, tipo='validar_correo', usado=False
        ).order_by(CodigoVerificacion.creado_en.desc()).first()

        if not registro or not registro.esta_vigente():
            flash('El código expiró. Vuelve a crear el usuario.', 'danger')
            return redirect(url_for('main.lista_usuarios'))

        if registro.codigo != codigo_ingresado:
            flash('Código incorrecto. Intenta de nuevo.', 'danger')
            return render_template('auth/validar_correo.html', form=form, email=email)

        registro.usado = True
        db.session.commit()

        # Guardar en sesión que este correo fue validado
        from flask import session
        session[f'correo_validado_{email}'] = True
        flash(f'✅ Correo {email} verificado correctamente.', 'success')
        return redirect(url_for('main.lista_usuarios'))

    return render_template('auth/validar_correo.html', form=form, email=email)


# ============================================================
# CONFIGURACIÓN DEL SISTEMA — Toggle 2FA
# ============================================================
@main.route('/admin/configuracion', methods=['GET','POST'])
@login_required
def admin_configuracion():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import ConfiguracionSistema
    if request.method == 'POST':
        backup_email = request.form.get('backup_email','').strip()
        gmail_user   = request.form.get('gmail_user','').strip()
        gmail_pass   = request.form.get('gmail_app_password','').strip()
        ConfiguracionSistema.establecer('backup_email', backup_email)
        if gmail_user:
            os.environ['GMAIL_USER'] = gmail_user
            ConfiguracionSistema.establecer('gmail_user', gmail_user)
        if gmail_pass:
            os.environ['GMAIL_APP_PASSWORD'] = gmail_pass
            ConfiguracionSistema.establecer('gmail_app_password', gmail_pass)
        registrar_auditoria('CONFIG', 'Configuracion', 'Configuración actualizada')
        flash('Configuración guardada exitosamente', 'success')
        return redirect(url_for('main.admin_configuracion'))
    dos_fa_activo  = ConfiguracionSistema.obtener('2fa_activo', 'true') == 'true'
    backup_email   = ConfiguracionSistema.obtener('backup_email', '')
    gmail_user     = ConfiguracionSistema.obtener('gmail_user', os.environ.get('GMAIL_USER',''))
    zip_activo     = ConfiguracionSistema.obtener('zip_activo', 'true') == 'true'
    zip_frecuencia = ConfiguracionSistema.obtener('zip_frecuencia', '2meses')
    zip_hora       = ConfiguracionSistema.obtener('zip_hora', '08:00')

    proximo_zip = None
    try:
        hora_n, min_n = int(zip_hora.split(':')[0]), int(zip_hora.split(':')[1])
        ahora = datetime.utcnow()
        if zip_frecuencia == 'hora':
            proximo = ahora.replace(minute=0, second=0) + timedelta(hours=1)
            proximo_zip = proximo.strftime('%d/%m/%Y %H:%M')
        elif zip_frecuencia == 'dia':
            proximo = ahora.replace(hour=hora_n, minute=min_n, second=0)
            if proximo <= ahora:
                proximo += timedelta(days=1)
            proximo_zip = proximo.strftime('%d/%m/%Y %H:%M')
        elif zip_frecuencia == 'semana':
            proximo = ahora.replace(hour=hora_n, minute=min_n, second=0)
            while proximo <= ahora:
                proximo += timedelta(days=7)
            proximo_zip = proximo.strftime('%d/%m/%Y %H:%M')
        elif zip_frecuencia == 'mes':
            proximo_zip = f'Próximo mes a las {zip_hora}'
        elif zip_frecuencia == '2meses':
            proximo_zip = f'Próximos 2 meses a las {zip_hora}'
    except:
        proximo_zip = 'No calculado'

    return render_template('admin/configuracion.html',
                           **{'2fa_activo': dos_fa_activo,
                              'backup_email': backup_email,
                              'gmail_user': gmail_user,
                              'zip_activo': zip_activo,
                              'zip_frecuencia': zip_frecuencia,
                              'zip_hora': zip_hora,
                              'proximo_zip': proximo_zip})


@main.route('/admin/toggle-2fa', methods=['POST'])
@login_required
def toggle_2fa():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import ConfiguracionSistema
    accion = request.form.get('accion', 'desactivar')
    nuevo_valor = 'true' if accion == 'activar' else 'false'
    ConfiguracionSistema.establecer('2fa_activo', nuevo_valor)
    registrar_auditoria(f'2FA_{accion.upper()}', 'Configuracion', f'2FA {"activado" if nuevo_valor=="true" else "desactivado"} por {current_user.email}')
    flash(f'2FA {"activado" if nuevo_valor=="true" else "desactivado"} correctamente.', 'success' if nuevo_valor=='true' else 'warning')
    return redirect(url_for('main.admin_configuracion'))


# ============================================================
# CORREOS DE BACKUP (ADMIN)
# ============================================================
@main.route('/admin/correos-backup')
@login_required
def lista_correos_backup():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import CorreoBackup
    correos = CorreoBackup.query.order_by(CorreoBackup.creado_en.desc()).all()
    return render_template('admin/correos_backup.html', correos=correos)


@main.route('/admin/correos-backup/agregar', methods=['POST'])
@login_required
def agregar_correo_backup():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import CorreoBackup, CodigoVerificacion
    from .correo_service import generar_codigo, enviar_codigo_validacion_correo

    email = request.form.get('email','').strip().lower()
    if not email:
        flash('Correo requerido', 'danger')
        return redirect(url_for('main.lista_correos_backup'))

    if CorreoBackup.query.count() >= 5:
        flash('Máximo 5 correos de backup permitidos', 'warning')
        return redirect(url_for('main.lista_correos_backup'))

    if CorreoBackup.query.filter_by(email=email).first():
        flash('Ese correo ya está registrado', 'warning')
        return redirect(url_for('main.lista_correos_backup'))

    # Crear correo sin verificar
    nuevo = CorreoBackup(email=email, verificado=False)
    db.session.add(nuevo)
    db.session.commit()

    # Enviar código de verificación
    codigo = generar_codigo()
    expira = datetime.utcnow() + timedelta(minutes=5)
    db.session.add(CodigoVerificacion(email=email, codigo=codigo, tipo='backup_email', expira_en=expira))
    db.session.commit()
    enviar_codigo_validacion_correo(email, codigo)

    flash(f'Código enviado a {email}. Verifícalo para activarlo.', 'info')
    return redirect(url_for('main.verificar_correo_backup', email=email))


@main.route('/admin/correos-backup/verificar/<email>', methods=['GET','POST'])
@login_required
def verificar_correo_backup(email):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import CorreoBackup, CodigoVerificacion
    from .forms import ValidarCorreoForm

    form = ValidarCorreoForm()
    if form.validate_on_submit():
        codigo_ingresado = form.codigo.data.strip()
        registro = CodigoVerificacion.query.filter_by(
            email=email, tipo='backup_email', usado=False
        ).order_by(CodigoVerificacion.creado_en.desc()).first()

        if not registro or not registro.esta_vigente():
            flash('Código expirado. Vuelve a agregar el correo.', 'danger')
            cb = CorreoBackup.query.filter_by(email=email, verificado=False).first()
            if cb:
                db.session.delete(cb)
                db.session.commit()
            return redirect(url_for('main.lista_correos_backup'))

        if registro.codigo != codigo_ingresado:
            flash('Código incorrecto.', 'danger')
            return render_template('admin/verificar_correo_backup.html', form=form, email=email)

        registro.usado = True
        cb = CorreoBackup.query.filter_by(email=email).first()
        if cb:
            cb.verificado = True
        db.session.commit()
        registrar_auditoria('AGREGAR', 'CorreosBackup', f'Correo de backup verificado: {email}')
        flash(f'✅ Correo {email} verificado y activado para backups.', 'success')
        return redirect(url_for('main.lista_correos_backup'))

    return render_template('admin/verificar_correo_backup.html', form=form, email=email)


@main.route('/admin/correos-backup/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_correo_backup(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import CorreoBackup, CodigoVerificacion
    from .correo_service import generar_codigo, enviar_codigo_validacion_correo

    cb = CorreoBackup.query.get_or_404(id)
    email = cb.email

    # Enviar código al correo para confirmar eliminación
    codigo = generar_codigo()
    expira = datetime.utcnow() + timedelta(minutes=5)
    db.session.add(CodigoVerificacion(email=email, codigo=codigo, tipo='eliminar_backup', expira_en=expira))
    db.session.commit()
    enviar_codigo_validacion_correo(email, codigo)

    flash(f'Se envió un código a {email} para confirmar la eliminación.', 'info')
    return redirect(url_for('main.confirmar_eliminar_correo_backup', id=id))


@main.route('/admin/correos-backup/confirmar-eliminar/<int:id>', methods=['GET','POST'])
@login_required
def confirmar_eliminar_correo_backup(id):
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import CorreoBackup, CodigoVerificacion
    from .forms import ValidarCorreoForm

    cb = CorreoBackup.query.get_or_404(id)
    form = ValidarCorreoForm()

    if form.validate_on_submit():
        codigo_ingresado = form.codigo.data.strip()
        registro = CodigoVerificacion.query.filter_by(
            email=cb.email, tipo='eliminar_backup', usado=False
        ).order_by(CodigoVerificacion.creado_en.desc()).first()

        if not registro or not registro.esta_vigente():
            flash('Código expirado.', 'danger')
            return redirect(url_for('main.lista_correos_backup'))

        if registro.codigo != codigo_ingresado:
            flash('Código incorrecto.', 'danger')
            return render_template('admin/confirmar_eliminar_backup.html', form=form, correo=cb)

        registro.usado = True
        email = cb.email
        db.session.delete(cb)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'CorreosBackup', f'Correo backup eliminado: {email}')
        flash(f'Correo {email} eliminado de los backups.', 'success')
        return redirect(url_for('main.lista_correos_backup'))

    return render_template('admin/confirmar_eliminar_backup.html', form=form, correo=cb)


@main.route('/admin/toggle-zip-backup', methods=['POST'])
@login_required
def toggle_zip_backup():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import ConfiguracionSistema
    actual = ConfiguracionSistema.obtener('zip_activo', 'true') == 'true'
    nuevo  = 'false' if actual else 'true'
    ConfiguracionSistema.establecer('zip_activo', nuevo)
    # Reprogramar scheduler
    from . import _reprogramar_zip
    _reprogramar_zip()
    registrar_auditoria('ZIP_BACKUP', 'Configuracion', f'ZIP backup {"activado" if nuevo=="true" else "desactivado"}')
    flash(f'ZIP al correo {"activado" if nuevo=="true" else "desactivado"} correctamente.', 'success' if nuevo=='true' else 'warning')
    return redirect(url_for('main.admin_configuracion'))


@main.route('/admin/configurar-zip-backup', methods=['POST'])
@login_required
def configurar_zip_backup():
    if not _solo_admin():
        return redirect(url_for('main.dashboard'))
    from .models import ConfiguracionSistema
    frecuencia = request.form.get('zip_frecuencia', '2meses')
    hora       = request.form.get('zip_hora', '08:00')
    ConfiguracionSistema.establecer('zip_frecuencia', frecuencia)
    ConfiguracionSistema.establecer('zip_hora', hora)
    # Reprogramar scheduler
    from . import _reprogramar_zip
    _reprogramar_zip()
    registrar_auditoria('ZIP_CONFIG', 'Configuracion', f'ZIP backup: frecuencia={frecuencia} hora={hora}')
    flash('Configuración de ZIP guardada correctamente.', 'success')
    return redirect(url_for('main.admin_configuracion'))


# ============================================================
# GOOGLE DRIVE (ADMIN)
# ============================================================
@main.route('/admin/drive/estado')
@login_required
def drive_estado():
    if not _solo_admin():
        return jsonify({'error': 'Sin acceso'}), 403
    from .drive_service import estado_drive, correo_autorizado, _reautorizando
    estado = estado_drive()
    correo = correo_autorizado() if estado == 'autorizado' else None
    return jsonify({
        'estado':      estado,
        'correo':      correo,
        'autorizando': _reautorizando
    })


@main.route('/admin/drive/reautorizar', methods=['POST'])
@login_required
def drive_reautorizar():
    if not _solo_admin():
        return jsonify({'error': 'Sin acceso'}), 403
    from .drive_service import reautorizar_drive
    ok, mensaje = reautorizar_drive()
    return jsonify({'ok': ok, 'mensaje': mensaje})


# ============================================================
# CONTEXT PROCESSOR - Variables globales para todas las plantillas
# ============================================================
@main.context_processor
def inject_globals():
    from .models import ConfiguracionSistema
    try:
        neon_porcentaje = float(ConfiguracionSistema.obtener('neon_porcentaje', '0'))
        neon_mb_usado   = float(ConfiguracionSistema.obtener('neon_mb_usado', '0'))
    except:
        neon_porcentaje = 0
        neon_mb_usado   = 0

    return dict(
        neon_porcentaje=neon_porcentaje,
        neon_mb_usado=neon_mb_usado
    )