"""
Helper para registrar eventos de auditoría en el sistema.
Usar en cualquier ruta con: registrar_auditoria(accion, modulo, descripcion)
"""
from .models import db, Auditoria
from flask import request
from flask_login import current_user


def registrar_auditoria(accion, modulo='', descripcion='', exitoso=True, usuario_id=None, usuario_email=None):
    try:
        uid   = usuario_id or (current_user.id if current_user.is_authenticated else None)
        email = usuario_email or (current_user.email if current_user.is_authenticated else None)
        ip    = request.remote_addr if request else None

        entrada = Auditoria(
            usuario_id    = uid,
            usuario_email = email,
            accion        = accion[:50],
            modulo        = modulo[:50],
            descripcion   = descripcion[:500] if descripcion else '',
            ip_origen     = ip,
            exitoso       = exitoso
        )
        db.session.add(entrada)
        db.session.commit()
    except Exception as e:
        print(f"Error registrando auditoría: {e}")
