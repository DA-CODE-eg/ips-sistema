"""
Servicio Google Drive - OAuth2 con Gmail normal.
Primera vez abre navegador para autorizar.
De ahi en adelante sube solo sin pedir nada.
"""
import os, io, threading

CARPETA_RAIZ = 'IPS Fulano Backups'
SCOPES = ['https://www.googleapis.com/auth/drive']
_cache = {}
_reautorizando = False


def _obtener_base():
    """
    Retorna la carpeta donde estan token.json y oauth_credentials.json.
    - En desarrollo: raiz del proyecto
    - En .exe instalado: AppData/Local/IPS-Fulano (tiene permisos de escritura)
    """
    import sys
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('LOCALAPPDATA', os.path.dirname(sys.executable))
        base = os.path.join(appdata, 'IPS-Fulano')
        os.makedirs(base, exist_ok=True)
        return base
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _obtener_servicio():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    base       = _obtener_base()
    token_path = os.path.join(base, 'token.json')

    if not os.path.exists(token_path):
        raise FileNotFoundError('No hay token.json - autoriza Drive desde el panel admin')

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
            print("Token Drive renovado automaticamente")
        else:
            raise FileNotFoundError('Token expirado - autoriza Drive desde el panel admin')

    return build('drive', 'v3', credentials=creds)


def reautorizar_drive():
    """
    Borra el token viejo y abre el navegador para autorizar con cuenta nueva.
    Se ejecuta en hilo separado para no bloquear Flask.
    """
    global _reautorizando
    if _reautorizando:
        return False, 'Ya hay una autorizacion en proceso'

    def _proceso():
        global _reautorizando, _cache
        _reautorizando = True
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            base       = _obtener_base()
            token_path = os.path.join(base, 'token.json')
            oauth_path = os.path.join(base, 'oauth_credentials.json')

            if not os.path.exists(oauth_path):
                print("Error: no hay oauth_credentials.json en " + base)
                return

            # Borrar token viejo
            if os.path.exists(token_path):
                os.remove(token_path)

            print("Abriendo navegador para autorizar Drive...")
            flow  = InstalledAppFlow.from_client_secrets_file(oauth_path, SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=True)

            with open(token_path, 'w') as f:
                f.write(creds.to_json())

            _cache = {}
            print("Drive reautorizado correctamente en: " + base)

        except Exception as e:
            print(f"Error reautorizando Drive: {e}")
        finally:
            _reautorizando = False

    threading.Thread(target=_proceso, daemon=True).start()
    return True, 'Navegador abierto - autoriza y listo'


def estado_drive():
    """Retorna si Drive esta autorizado o no."""
    base       = _obtener_base()
    token_path = os.path.join(base, 'token.json')
    oauth_path = os.path.join(base, 'oauth_credentials.json')

    if not os.path.exists(oauth_path):
        return 'sin_oauth'
    if _reautorizando:
        return 'autorizando'
    if not os.path.exists(token_path):
        return 'sin_token'

    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        return 'autorizado'
    except:
        return 'sin_token'


def correo_autorizado():
    """Retorna el correo que autorizo Drive."""
    try:
        base       = _obtener_base()
        token_path = os.path.join(base, 'token.json')
        if not os.path.exists(token_path):
            return None
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        creds   = Credentials.from_authorized_user_file(token_path, SCOPES)
        service = build('oauth2', 'v2', credentials=creds)
        info    = service.userinfo().get().execute()
        return info.get('email')
    except:
        return None


def _obtener_o_crear_carpeta(servicio, nombre, padre_id=None):
    clave = f"{padre_id}:{nombre}"
    if clave in _cache:
        return _cache[clave]

    query = f"name='{nombre}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if padre_id:
        query += f" and '{padre_id}' in parents"

    resultado = servicio.files().list(
        q=query, spaces='drive', fields='files(id, name)'
    ).execute()

    archivos = resultado.get('files', [])
    if archivos:
        _cache[clave] = archivos[0]['id']
        return _cache[clave]

    metadata = {'name': nombre, 'mimeType': 'application/vnd.google-apps.folder'}
    if padre_id:
        metadata['parents'] = [padre_id]

    carpeta = servicio.files().create(body=metadata, fields='id').execute()
    _cache[clave] = carpeta['id']
    print(f"Carpeta creada en Drive: {nombre}")
    return _cache[clave]


def _subir_o_actualizar_archivo(servicio, nombre, contenido_bytes, mimetype, carpeta_id):
    from googleapiclient.http import MediaIoBaseUpload

    resultado = servicio.files().list(
        q=f"name='{nombre}' and '{carpeta_id}' in parents and trashed=false",
        spaces='drive', fields='files(id, name)'
    ).execute()

    media    = MediaIoBaseUpload(io.BytesIO(contenido_bytes), mimetype=mimetype, resumable=False)
    archivos = resultado.get('files', [])

    if archivos:
        archivo = servicio.files().update(
            fileId=archivos[0]['id'],
            media_body=media, fields='id, name'
        ).execute()
    else:
        metadata = {'name': nombre, 'parents': [carpeta_id]}
        archivo  = servicio.files().create(
            body=metadata, media_body=media, fields='id, name'
        ).execute()

    return archivo.get('id')


def compartir_carpeta_con_todos(correos):
    """Comparte la carpeta raiz con todos los correos verificados."""
    try:
        servicio = _obtener_servicio()
        raiz_id  = _obtener_o_crear_carpeta(servicio, CARPETA_RAIZ)

        permisos_actuales = servicio.permissions().list(
            fileId=raiz_id,
            fields='permissions(emailAddress)'
        ).execute()
        emails_actuales = {
            p.get('emailAddress', '').lower()
            for p in permisos_actuales.get('permissions', [])
        }

        for correo in correos:
            if correo.lower() in emails_actuales:
                continue
            try:
                servicio.permissions().create(
                    fileId=raiz_id,
                    body={
                        'type': 'user',
                        'role': 'reader',
                        'emailAddress': correo
                    },
                    sendNotificationEmail=False
                ).execute()
                print(f"Carpeta compartida con {correo}")
            except Exception as e:
                print(f"No se pudo compartir con {correo}: {e}")

    except Exception as e:
        print(f"Error compartiendo carpeta: {e}")


def subir_pdf_drive(nombre_archivo, pdf_bytes, subcarpeta='reportes'):
    """
    Sube un PDF individual a Drive en el momento que se genera.
    subcarpeta: 'historias' | 'reportes'
    Retorna (True, url) o (False, error)
    """
    import threading

    def _subir():
        try:
            servicio     = _obtener_servicio()
            raiz_id      = _obtener_o_crear_carpeta(servicio, CARPETA_RAIZ)
            carpeta_id   = _obtener_o_crear_carpeta(servicio, subcarpeta, raiz_id)
            archivo_id   = _subir_o_actualizar_archivo(
                servicio, nombre_archivo, pdf_bytes, 'application/pdf', carpeta_id
            )
            url = f"https://drive.google.com/file/d/{archivo_id}/view"
            print(f"☁️  Drive: {subcarpeta}/{nombre_archivo} → {url}")
        except Exception as e:
            print(f"⚠️  Drive PDF no subido ({nombre_archivo}): {e}")

    # Se sube en hilo separado para no bloquear la respuesta HTTP
    threading.Thread(target=_subir, daemon=True).start()
    return True, None


def sincronizar_con_drive(datos_csv, reportes_pdf, historias_pdf):
    global _cache
    _cache = {}

    try:
        servicio     = _obtener_servicio()
        raiz_id      = _obtener_o_crear_carpeta(servicio, CARPETA_RAIZ)
        datos_id     = _obtener_o_crear_carpeta(servicio, 'datos',     raiz_id)
        reportes_id  = _obtener_o_crear_carpeta(servicio, 'reportes',  raiz_id)
        historias_id = _obtener_o_crear_carpeta(servicio, 'historias', raiz_id)

        for nombre, contenido in datos_csv.items():
            _subir_o_actualizar_archivo(servicio, nombre, contenido, 'text/csv', datos_id)
            print(f"Drive: datos/{nombre}")

        for nombre, contenido in reportes_pdf.items():
            if contenido:
                _subir_o_actualizar_archivo(servicio, nombre, contenido, 'application/pdf', reportes_id)
                print(f"Drive: reportes/{nombre}")

        for nombre, contenido in historias_pdf.items():
            if contenido:
                _subir_o_actualizar_archivo(servicio, nombre, contenido, 'application/pdf', historias_id)
                print(f"Drive: historias/{nombre}")

        print("Drive sincronizado correctamente")
        return True, None

    except Exception as e:
        print(f"Error sincronizando con Drive: {e}")
        return False, str(e)
