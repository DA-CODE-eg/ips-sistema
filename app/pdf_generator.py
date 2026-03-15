# pdf_generator.py
# Generador de PDFs con ReportLab — sin dependencias externas
# Tema: Rojo / Blanco / Negro — Fundación Eudes

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, KeepTogether, Image)
from reportlab.platypus.flowables import HRFlowable
from io import BytesIO
from datetime import datetime
import os

# ─── Colores corporativos ────────────────────────────────────────────────────
ROJO      = colors.HexColor('#C0392B')
ROJO_OSC  = colors.HexColor('#922B21')
ROJO_CLAR = colors.HexColor('#FDEDEC')
NEGRO     = colors.HexColor('#1A1A1A')
GRIS      = colors.HexColor('#555555')
GRIS_CLAR = colors.HexColor('#F5F5F5')
BLANCO    = colors.white
VERDE     = colors.HexColor('#1E8449')
NARANJA   = colors.HexColor('#D35400')
AZUL      = colors.HexColor('#1A5276')

# ─── Logo ───────────────────────────────────────────────────────────────────
_LOGO_PATH = os.path.join(os.path.dirname(__file__), 'logo_eudes.png')
if not os.path.exists(_LOGO_PATH):
    _LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logo_eudes.png')


def _get_logo(ancho=2.5*cm, alto=2.5*cm):
    try:
        if os.path.exists(_LOGO_PATH):
            return Image(_LOGO_PATH, width=ancho, height=alto)
    except Exception:
        pass
    return Paragraph('', ParagraphStyle('x'))


def _p(text, style, escape=True):
    import html as html_mod
    if text is None:
        text = ''
    text = str(text)
    if escape:
        text = html_mod.escape(text)
    return Paragraph(text, style)


def _ph(text, style):
    return Paragraph(str(text) if text else '', style)


# ─── Canvas: marca de agua + número de página ────────────────────────────────
def _make_canvas(watermark='IPS FULANO', landscape_mode=False):
    def _canvas(canv, doc):
        W, H = (landscape(A4) if landscape_mode else A4)
        canv.saveState()
        canv.setFont('Helvetica-Bold', 54)
        canv.setFillGray(0.93)
        canv.translate(W/2, H/2)
        canv.rotate(45)
        canv.drawCentredString(0, 0, watermark)
        canv.restoreState()
        canv.saveState()
        canv.setFont('Helvetica', 8)
        canv.setFillColor(GRIS)
        canv.drawCentredString(W/2, 1.0*cm, f'Pagina {doc.page}')
        canv.restoreState()
    return _canvas



# ════════════════════════════════════════════════════════════════════════════
# 1. HISTORIA CLINICA
# ════════════════════════════════════════════════════════════════════════════
def generar_historia_pdf(paciente, historia, entradas, fecha_generacion,
                         edad, solo_recientes, campos_extra=None, logo_path=None):
    import html as _html, sys

    buf    = BytesIO()
    MARGEN = 1.8*cm
    W_DOC  = A4[0] - 2*MARGEN
    H_HDR  = 2.6*cm
    TOP    = MARGEN + H_HDR + 0.5*cm      # página 1
    BOTTOM = 3.8*cm

    cod_historia   = f'HC-{str(historia.id).zfill(4)}' if historia else 'HC-0000'
    fecha_apertura = (historia.fecha_creacion.strftime('%d/%m/%Y')
                      if historia and historia.fecha_creacion else fecha_generacion[:10])
    nombre_firma   = entradas[0].autor.nombre if entradas else ''
    rol_firma      = entradas[0].autor.rol.nombre.upper() if entradas else ''

    def _logo_path():
        # Si se pasó explícitamente desde routes.py, usar esa
        if logo_path and os.path.exists(logo_path):
            return logo_path
        rutas = [
            os.path.join(os.path.dirname(__file__), 'logo_eudes.png'),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logo_eudes.png'),
            os.path.join(os.getcwd(), 'app', 'logo_eudes.png'),
            os.path.join(os.getcwd(), 'logo_eudes.png'),
        ]
        base = getattr(sys, '_MEIPASS', None)
        if base:
            rutas.insert(0, os.path.join(base, 'app', 'logo_eudes.png'))
            rutas.insert(0, os.path.join(base, 'logo_eudes.png'))
        for r in rutas:
            if os.path.exists(r):
                return r
        return None

    def _logo_path():
        if logo_path and os.path.exists(logo_path):
            return logo_path
        rutas = [
            # Favicon primero
            os.path.join(os.path.dirname(__file__), 'static', 'favicon.png'),
            os.path.join(os.path.dirname(__file__), 'static', 'favicon.ico'),
            os.path.join(os.path.dirname(__file__), 'logo_eudes.png'),
            os.path.join(os.getcwd(), 'app', 'static', 'favicon.png'),
            os.path.join(os.getcwd(), 'app', 'static', 'favicon.ico'),
            os.path.join(os.getcwd(), 'app', 'logo_eudes.png'),
            os.path.join(os.getcwd(), 'logo_eudes.png'),
        ]
        base = getattr(sys, '_MEIPASS', None)
        if base:
            rutas.insert(0, os.path.join(base, 'app', 'static', 'favicon.png'))
            rutas.insert(0, os.path.join(base, 'app', 'static', 'favicon.ico'))
            rutas.insert(0, os.path.join(base, 'app', 'logo_eudes.png'))
        for r in rutas:
            if os.path.exists(r):
                return r
        return None

    LOGO = _logo_path()
    _total_pags = [1]

    # Colores suaves
    ROJO_HDR  = colors.HexColor('#C0392B')
    GRIS_HDR  = colors.HexColor('#F2F2F2')   # fondo encabezado pág 2+
    NEGRO_TXT = colors.HexColor('#1A1A1A')
    GRIS_TXT  = colors.HexColor('#666666')
    BORDE     = colors.HexColor('#E0E0E0')

    def _cabecera(canv, doc):
        PW, PH = A4

        # Marca de agua suave
        canv.saveState()
        canv.setFont('Helvetica-Bold', 70); canv.setFillGray(0.955)
        canv.translate(PW/2, PH/2); canv.rotate(42)
        canv.drawCentredString(0, 0, 'IPS FULANO')
        canv.restoreState()
        canv.saveState()

        if doc.page == 1:
            # ── PÁGINA 1: encabezado completo ──
            Y_H = PH - MARGEN - H_HDR
            WL=3.0*cm; WR=3.8*cm; WM=W_DOC-WL-WR

            canv.setFillColor(BLANCO); canv.setStrokeColor(BORDE); canv.setLineWidth(0.5)
            canv.rect(MARGEN, Y_H, W_DOC, H_HDR, fill=1, stroke=1)
            canv.setFillColor(ROJO_HDR)
            canv.rect(MARGEN, Y_H, 0.25*cm, H_HDR, fill=1, stroke=0)

            # Logo / favicon
            if LOGO:
                try:
                    canv.drawImage(LOGO, MARGEN+0.45*cm, Y_H+(H_HDR-2.0*cm)/2,
                                   width=2.0*cm, height=2.0*cm,
                                   preserveAspectRatio=True, mask='auto')
                except Exception:
                    pass

            canv.setFillColor(NEGRO_TXT); canv.setFont('Helvetica-Bold', 22)
            canv.drawCentredString(MARGEN+WL+WM/2, Y_H+H_HDR*0.60, 'HISTORIA CLÍNICA')
            canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica', 8)
            canv.drawCentredString(MARGEN+WL+WM/2, Y_H+H_HDR*0.26, 'IPS FULANO')
            canv.setStrokeColor(BORDE); canv.setLineWidth(0.5)
            canv.line(MARGEN+WL+WM, Y_H+0.2*cm, MARGEN+WL+WM, Y_H+H_HDR-0.2*cm)
            xi = MARGEN+WL+WM+8
            canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica-Bold', 7)
            canv.drawString(xi, Y_H+H_HDR*0.72, 'CÓDIGO:')
            canv.setFillColor(NEGRO_TXT); canv.setFont('Helvetica-Bold', 9)
            canv.drawString(xi, Y_H+H_HDR*0.50, cod_historia)
            canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica-Bold', 7)
            canv.drawString(xi, Y_H+H_HDR*0.30, 'FECHA:')
            canv.setFillColor(NEGRO_TXT); canv.setFont('Helvetica', 8)
            canv.drawString(xi, Y_H+H_HDR*0.10, fecha_apertura)
            canv.setStrokeColor(ROJO_HDR); canv.setLineWidth(2)
            canv.line(MARGEN, Y_H-0.05*cm, MARGEN+W_DOC, Y_H-0.05*cm)

        else:
            # ── PÁGINAS SIGUIENTES: barra delgada simple ──
            H_S = 0.7*cm
            Y_S = PH - MARGEN - H_S
            canv.setFillColor(GRIS_HDR); canv.setStrokeColor(BORDE); canv.setLineWidth(0.3)
            canv.rect(MARGEN, Y_S, W_DOC, H_S, fill=1, stroke=1)
            canv.setFillColor(ROJO_HDR)
            canv.rect(MARGEN, Y_S, 0.2*cm, H_S, fill=1, stroke=0)
            canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica', 7)
            canv.drawString(MARGEN+0.35*cm, Y_S+0.22*cm, f'IPS FULANO  —  {cod_historia}')
            canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica', 7)
            canv.drawRightString(MARGEN+W_DOC-4, Y_S+0.22*cm, f'Página {doc.page}')
            canv.setStrokeColor(ROJO_HDR); canv.setLineWidth(1)
            canv.line(MARGEN, Y_S-0.03*cm, MARGEN+W_DOC, Y_S-0.03*cm)

        # PIE siempre
        canv.setFillColor(NEGRO_TXT); canv.setFont('Helvetica-Bold', 8)
        canv.drawCentredString(PW/2, 1.6*cm, 'IPS FULANO')
        canv.setStrokeColor(BORDE); canv.setLineWidth(0.5)
        canv.line(MARGEN, 1.4*cm, MARGEN+W_DOC, 1.4*cm)
        canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica', 6.8)
        canv.drawCentredString(PW/2, 1.15*cm,
            'ipsfulano@fundacioneudes.co  ·  Tel: 601-7559343  ·  (+57) 3173665722  ·  Línea de Vida: 320 999 03337')
        canv.setFillColor(colors.HexColor('#BBBBBB')); canv.setFont('Helvetica', 6)
        canv.drawCentredString(PW/2, 0.85*cm,
            'Documento confidencial — Información médica protegida por ley')

        # Firma solo en última página
        if doc.page == _total_pags[0] and nombre_firma:
            fy = 2.2*cm
            canv.setStrokeColor(NEGRO_TXT); canv.setLineWidth(0.7)
            canv.line(MARGEN, fy+1.0*cm, MARGEN+5.5*cm, fy+1.0*cm)
            canv.setFillColor(NEGRO_TXT); canv.setFont('Helvetica-Bold', 9)
            canv.drawString(MARGEN, fy+0.70*cm, nombre_firma)
            canv.setFillColor(GRIS_TXT); canv.setFont('Helvetica', 8)
            canv.drawString(MARGEN, fy+0.42*cm, rol_firma)
            canv.setFillColor(ROJO_HDR); canv.setFont('Helvetica-Bold', 8)
            canv.drawString(MARGEN, fy+0.15*cm, 'IPS FULANO')
        canv.restoreState()

    st_lbl = ParagraphStyle('lbl', fontSize=7.5, textColor=GRIS, fontName='Helvetica-Bold', leading=10)
    st_val = ParagraphStyle('val', fontSize=8.5, textColor=NEGRO, leading=11)
    st_sec = ParagraphStyle('sec', fontSize=10,  textColor=NEGRO, fontName='Helvetica-Bold',
                             leading=13, spaceBefore=6, spaceAfter=2)
    st_cnt = ParagraphStyle('cnt', fontSize=8.5, textColor=NEGRO, leading=13)
    st_nm  = ParagraphStyle('nm',  fontSize=8.5, textColor=GRIS,  leading=12)

    CL=3.5*cm; CV=W_DOC-CL

    def _p(t, s): return Paragraph(_html.escape(str(t) if t else ''), s)
    def _ph(t, s): return Paragraph(str(t) if t else '', s)

    def _fila(lbl, val):
        t = Table([[_p(lbl, st_lbl), _p(val, st_val)]], colWidths=[CL, CV])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(0,0), GRIS_CLAR),
            ('BACKGROUND',    (1,0),(1,0), BLANCO),
            ('BOX',           (0,0),(-1,-1), 0.4, colors.HexColor('#E5E5E5')),
            ('LEFTPADDING',   (0,0),(-1,-1), 8),
            ('RIGHTPADDING',  (0,0),(-1,-1), 8),
            ('TOPPADDING',    (0,0),(-1,-1), 5),
            ('BOTTOMPADDING', (0,0),(-1,-1), 5),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('LINEBEFORE',    (0,0),(0,-1),  2.5, ROJO),
        ]))
        return t

    def _sec(titulo):
        return [_ph(titulo, st_sec),
                HRFlowable(width='100%', thickness=1, color=ROJO, spaceAfter=2)]

    def _build_story():
        s = []
        # Edad calculada desde fecha_nacimiento
        from datetime import date as _date
        edad_str = '-'
        try:
            fn = paciente.fecha_nacimiento
            if fn:
                if isinstance(fn, str):
                    from datetime import datetime as _dt
                    fn = _dt.strptime(fn[:10], '%Y-%m-%d').date()
                elif hasattr(fn, 'date'):
                    fn = fn.date()
                hoy = _date.today()
                dias_total = (hoy - fn).days
                if dias_total < 0 or dias_total > 120*365:
                    # Fecha inválida
                    if edad is not None and 0 <= edad <= 120:
                        edad_str = f'{edad} años'
                elif dias_total < 7:
                    edad_str = f'{dias_total} día{"s" if dias_total != 1 else ""}'
                elif dias_total < 30:
                    semanas = dias_total // 7
                    edad_str = f'{semanas} semana{"s" if semanas != 1 else ""}'
                elif dias_total < 365:
                    meses = dias_total // 30
                    edad_str = f'{meses} mes{"es" if meses != 1 else ""}'
                else:
                    edad_calc = hoy.year - fn.year
                    if hoy < fn.replace(year=hoy.year):
                        edad_calc -= 1
                    edad_str = f'{edad_calc} año{"s" if edad_calc != 1 else ""}'
            elif edad is not None and 0 <= edad <= 120:
                edad_str = f'{edad} años'
        except Exception:
            if edad is not None and 0 <= edad <= 120:
                edad_str = f'{edad} años'

        filas_pac = [
            _fila('NOMBRE',           paciente.nombre),
            _fila('IDENTIFICACIÓN',   paciente.identificacion),
            _fila('EDAD',             edad_str),
            _fila('SEXO',             paciente.sexo or '-'),
            _fila('TELÉFONO',         paciente.telefono or '-'),
            _fila('EMAIL',            paciente.email or '-'),
        ]
        if paciente.direccion:
            filas_pac.append(_fila('DIRECCIÓN', paciente.direccion))
        for v in sorted(paciente.campos_extra, key=lambda v: v.campo.orden):
            filas_pac.append(_fila(v.campo.nombre.upper(), v.valor or '-'))
        s.append(KeepTogether(_sec('Información del Paciente') + filas_pac))
        s.append(Spacer(1, 6))

        titulo_sec = 'Entradas de Historia Clínica'
        if solo_recientes:
            titulo_sec += '  —  Últimos 30 días'
        s += _sec(titulo_sec)

        if entradas:
            for entrada in entradas:
                fecha_e = entrada.fecha.strftime('%d/%m/%Y  %H:%M')
                autor_e = f'{entrada.autor.nombre}  |  {entrada.autor.rol.nombre.upper()}'
                cab = Table([[
                    _ph(f'<b>{fecha_e}</b>',
                        ParagraphStyle('ef', fontSize=7.5, textColor=BLANCO, fontName='Helvetica-Bold')),
                    _ph(f'<b>{autor_e}</b>',
                        ParagraphStyle('ea', fontSize=7.5, alignment=TA_RIGHT,
                                       textColor=colors.HexColor('#FFCCCC'))),
                ]], colWidths=[W_DOC*0.5, W_DOC*0.5])
                cab.setStyle(TableStyle([
                    ('BACKGROUND',   (0,0),(-1,-1), ROJO),
                    ('LEFTPADDING',  (0,0),(-1,-1), 9),
                    ('RIGHTPADDING', (0,0),(-1,-1), 9),
                    ('TOPPADDING',   (0,0),(-1,-1), 5),
                    ('BOTTOMPADDING',(0,0),(-1,-1), 5),
                ]))
                cuerpo = Table([[_p(entrada.contenido or '', st_cnt)]], colWidths=[W_DOC])
                cuerpo.setStyle(TableStyle([
                    ('BOX',           (0,0),(-1,-1), 0.4, colors.HexColor('#E5E5E5')),
                    ('BACKGROUND',    (0,0),(-1,-1), BLANCO),
                    ('LEFTPADDING',   (0,0),(-1,-1), 10),
                    ('RIGHTPADDING',  (0,0),(-1,-1), 10),
                    ('TOPPADDING',    (0,0),(-1,-1), 8),
                    ('BOTTOMPADDING', (0,0),(-1,-1), 8),
                ]))
                s.append(KeepTogether([cab, cuerpo, Spacer(1, 5)]))
        else:
            s.append(_p('No hay entradas registradas.', st_nm))
            s.append(Spacer(1, 6))

        if historia and hasattr(historia, 'versiones') and historia.versiones:
            ultima = sorted(historia.versiones, key=lambda v: v.fecha, reverse=True)[0]
            t_meta = Table([[_ph(
                f'<b>Última modificación:</b> {ultima.fecha.strftime("%d/%m/%Y %H:%M")}'
                f'  |  <b>Por:</b> {ultima.autor.nombre} ({ultima.autor.rol.nombre})',
                ParagraphStyle('mm', fontSize=7.5, textColor=GRIS))]],
                colWidths=[W_DOC])
            t_meta.setStyle(TableStyle([
                ('BACKGROUND',   (0,0),(-1,-1), GRIS_CLAR),
                ('LEFTPADDING',  (0,0),(-1,-1), 8),
                ('TOPPADDING',   (0,0),(-1,-1), 4),
                ('BOTTOMPADDING',(0,0),(-1,-1), 4),
                ('BOX',          (0,0),(-1,-1), 0.4, colors.HexColor('#E5E5E5')),
            ]))
            s.append(t_meta)
        return s

    # Paso 1: contar páginas
    buf_tmp = BytesIO()
    doc_tmp = SimpleDocTemplate(buf_tmp, pagesize=A4,
        leftMargin=MARGEN, rightMargin=MARGEN, topMargin=TOP, bottomMargin=BOTTOM)
    doc_tmp.build(_build_story(), onFirstPage=lambda c,d: None, onLaterPages=lambda c,d: None)
    _total_pags[0] = doc_tmp.page

    # Paso 2: PDF final
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=MARGEN, rightMargin=MARGEN, topMargin=TOP, bottomMargin=BOTTOM)
    doc.build(_build_story(), onFirstPage=_cabecera, onLaterPages=_cabecera)
    return buf.getvalue()

def generar_pacientes_pdf(pacientes, fecha_generacion):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []

    st_titulo = ParagraphStyle('t', fontSize=20, textColor=ROJO,
                               alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=4)
    st_sub    = ParagraphStyle('s', fontSize=10, textColor=GRIS, alignment=TA_CENTER, spaceAfter=8)
    st_foot   = ParagraphStyle('f', fontSize=8, textColor=GRIS, alignment=TA_CENTER)
    st_num    = ParagraphStyle('n', fontSize=18, textColor=ROJO,
                               fontName='Helvetica-Bold', alignment=TA_CENTER)
    st_lbl    = ParagraphStyle('l', fontSize=8, textColor=GRIS, alignment=TA_CENTER)

    logo = _get_logo(2*cm, 2*cm)
    t_h = Table([[logo, [_p('IPS FULANO', st_titulo),
                         _p('Reporte de Pacientes Registrados', st_sub)]
                ]], colWidths=[2.5*cm, 14.5*cm])
    t_h.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4)]))
    story.append(t_h)
    story.append(HRFlowable(width='100%', thickness=3, color=ROJO, spaceAfter=10))

    t_info = Table([[_ph(f'<b>Fecha:</b> {fecha_generacion}   |   <b>Total pacientes:</b> {len(pacientes)}',
                        ParagraphStyle('ib', fontSize=10))]], colWidths=[17*cm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), ROJO_CLAR),
        ('LINEBEFORE', (0,0), (0,-1), 4, ROJO),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING',  (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0),(-1,-1), 8),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 10))

    activos   = sum(1 for p in pacientes if p.activo)
    inactivos = len(pacientes) - activos
    t_stats = Table([
        [_p(str(len(pacientes)), st_num), _p(str(activos), st_num), _p(str(inactivos), st_num)],
        [_p('Total Pacientes', st_lbl), _p('Activos', st_lbl), _p('Inactivos', st_lbl)]
    ], colWidths=[5.67*cm]*3)
    t_stats.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), GRIS_CLAR),
        ('BOX', (0,0), (-1,-1), 1.5, ROJO),
        ('TOPPADDING',   (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 12))

    if pacientes:
        st_td    = ParagraphStyle('td',  fontSize=9)
        st_td_sm = ParagraphStyle('tds', fontSize=8, textColor=GRIS)
        header = [_p(h, ParagraphStyle('th', fontSize=9, textColor=BLANCO,
                                        fontName='Helvetica-Bold', alignment=TA_CENTER))
                  for h in ['#', 'Nombre Completo', 'Identificacion', 'Telefono', 'Email', 'Estado']]
        rows = [header]
        for i, p in enumerate(pacientes, 1):
            rows.append([
                _p(str(i), st_td), _p(p.nombre, st_td), _p(p.identificacion, st_td),
                _p(p.telefono or '-', st_td), _p(p.email or '-', st_td_sm),
                _p('Activo' if p.activo else 'Inactivo',
                   ParagraphStyle('est', fontSize=9,
                   textColor=VERDE if p.activo else ROJO, fontName='Helvetica-Bold')),
            ])
            if hasattr(p, 'campos_extra') and p.campos_extra:
                campos_str = '   '.join(
                    f'{v.campo.nombre}: {v.valor or "-"}'
                    for v in sorted(p.campos_extra, key=lambda v: v.campo.orden)
                )
                rows.append([
                    _p('', st_td),
                    _ph(f'<i>{campos_str}</i>',
                        ParagraphStyle('ce', fontSize=8, textColor=GRIS)),
                    _p('', st_td), _p('', st_td), _p('', st_td), _p('', st_td),
                ])
        t = Table(rows, colWidths=[1*cm, 5*cm, 3*cm, 2.5*cm, 3.5*cm, 2*cm])
        ts = [
            ('BACKGROUND',    (0,0), (-1,0), ROJO),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [BLANCO, GRIS_CLAR]),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
            ('LEFTPADDING',   (0,0), (-1,-1), 6),
            ('RIGHTPADDING',  (0,0), (-1,-1), 6),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ]
        t.setStyle(TableStyle(ts))
        story.append(t)
    else:
        story.append(_p('No hay pacientes registrados.', st_sub))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=1, color=ROJO))
    story.append(Spacer(1, 4))
    story.append(_p('Generado automaticamente por el Sistema de Gestion IPS FULANO', st_foot))

    _cv = _make_canvas()
    doc.build(story, onFirstPage=_cv, onLaterPages=_cv)
    return buf.getvalue()

# ════════════════════════════════════════════════════════════════════════════
# 3. REPORTE CITAS
# ════════════════════════════════════════════════════════════════════════════
def generar_citas_pdf(citas, fecha_generacion):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []

    st_titulo = ParagraphStyle('t', fontSize=18, textColor=ROJO,
                               alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=4)
    st_sub    = ParagraphStyle('s', fontSize=10, textColor=GRIS, alignment=TA_CENTER, spaceAfter=8)
    st_foot   = ParagraphStyle('f', fontSize=8, textColor=GRIS, alignment=TA_CENTER)
    st_num    = ParagraphStyle('n', fontSize=16, textColor=ROJO,
                               fontName='Helvetica-Bold', alignment=TA_CENTER)
    st_lbl    = ParagraphStyle('l', fontSize=8, textColor=GRIS, alignment=TA_CENTER)

    logo = _get_logo(1.8*cm, 1.8*cm)
    t_h = Table([[logo, [_p('IPS FULANO', st_titulo),
                         _p('Reporte de Citas Medicas', st_sub)]
                ]], colWidths=[2.3*cm, 25*cm])
    t_h.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4)]))
    story.append(t_h)
    story.append(HRFlowable(width='100%', thickness=3, color=ROJO, spaceAfter=10))

    t_info = Table([[_ph(f'<b>Fecha:</b> {fecha_generacion}   |   <b>Total citas:</b> {len(citas)}',
                        ParagraphStyle('ib', fontSize=10))]], colWidths=[26*cm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), ROJO_CLAR),
        ('LINEBEFORE', (0,0), (0,-1), 4, ROJO),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING',  (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0),(-1,-1), 8),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 10))

    pendientes = sum(1 for c in citas if c.estado == 'Pendiente')
    realizadas = sum(1 for c in citas if c.estado == 'Realizada')
    canceladas = sum(1 for c in citas if c.estado == 'Cancelada')
    t_stats = Table([
        [_p(str(len(citas)), st_num), _p(str(pendientes), st_num),
         _p(str(realizadas), st_num), _p(str(canceladas), st_num)],
        [_p('Total', st_lbl), _p('Pendientes', st_lbl),
         _p('Realizadas', st_lbl), _p('Canceladas', st_lbl)]
    ], colWidths=[6.5*cm]*4)
    t_stats.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), GRIS_CLAR),
        ('BOX', (0,0), (-1,-1), 1.5, ROJO),
        ('TOPPADDING',   (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 12))

    if citas:
        st_td = ParagraphStyle('td', fontSize=8)
        header = [_p(h, ParagraphStyle('th', fontSize=8, textColor=BLANCO,
                                        fontName='Helvetica-Bold', alignment=TA_CENTER))
                  for h in ['#', 'Fecha/Hora', 'Paciente', 'Medico', 'Especialidad', 'ID', 'Estado']]
        rows = [header]
        for i, c in enumerate(citas, 1):
            estado = c.estado
            color_est = NARANJA if estado=='Pendiente' else (VERDE if estado=='Realizada' else ROJO)
            rows.append([
                _p(str(i), st_td),
                _p(c.fecha.strftime('%d/%m/%Y %H:%M'), st_td),
                _p(c.paciente.nombre, st_td),
                _p(c.medico.nombre, st_td),
                _p(c.especialidad.nombre, st_td),
                _p(c.paciente.identificacion, st_td),
                _p(estado, ParagraphStyle('est', fontSize=8, textColor=color_est,
                   fontName='Helvetica-Bold')),
            ])
        t = Table(rows, colWidths=[1*cm, 3.5*cm, 5*cm, 4*cm, 5*cm, 3.5*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), ROJO),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [BLANCO, GRIS_CLAR]),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
            ('LEFTPADDING',   (0,0), (-1,-1), 5),
            ('RIGHTPADDING',  (0,0), (-1,-1), 5),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(t)
    else:
        story.append(_p('No hay citas registradas.', st_sub))

    story.append(Spacer(1, 15))
    story.append(HRFlowable(width='100%', thickness=1, color=ROJO))
    story.append(Spacer(1, 4))
    story.append(_p('Generado automaticamente por el Sistema de Gestion IPS FULANO', st_foot))

    _cv = _make_canvas(landscape_mode=True)
    doc.build(story, onFirstPage=_cv, onLaterPages=_cv)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════
# 4. REPORTE ESPECIALIDADES
# ════════════════════════════════════════════════════════════════════════════
def generar_especialidades_pdf(especialidades, fecha_generacion):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []

    st_titulo = ParagraphStyle('t', fontSize=20, textColor=ROJO,
                               alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=4)
    st_sub    = ParagraphStyle('s', fontSize=10, textColor=GRIS, alignment=TA_CENTER, spaceAfter=8)
    st_foot   = ParagraphStyle('f', fontSize=8, textColor=GRIS, alignment=TA_CENTER)
    st_num    = ParagraphStyle('n', fontSize=18, textColor=ROJO,
                               fontName='Helvetica-Bold', alignment=TA_CENTER)
    st_lbl    = ParagraphStyle('l', fontSize=8, textColor=GRIS, alignment=TA_CENTER)
    st_td     = ParagraphStyle('td', fontSize=9)
    st_medico = ParagraphStyle('med', fontSize=8, textColor=GRIS)

    logo = _get_logo(2*cm, 2*cm)
    t_h = Table([[logo, [_p('IPS FULANO', st_titulo),
                         _p('Reporte de Especialidades Medicas', st_sub)]
                ]], colWidths=[2.5*cm, 14.5*cm])
    t_h.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4)]))
    story.append(t_h)
    story.append(HRFlowable(width='100%', thickness=3, color=ROJO, spaceAfter=10))

    t_info = Table([[_ph(f'<b>Fecha:</b> {fecha_generacion}   |   <b>Total especialidades:</b> {len(especialidades)}',
                        ParagraphStyle('ib', fontSize=10))]], colWidths=[17*cm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), ROJO_CLAR),
        ('LINEBEFORE', (0,0), (0,-1), 4, ROJO),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING',  (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0),(-1,-1), 8),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 10))

    con_citas   = sum(1 for e in especialidades if len(e.citas) > 0)
    total_citas = sum(len(e.citas) for e in especialidades)
    t_stats = Table([
        [_p(str(len(especialidades)), st_num), _p(str(con_citas), st_num), _p(str(total_citas), st_num)],
        [_p('Total Especialidades', st_lbl), _p('Con Citas Activas', st_lbl), _p('Total de Citas', st_lbl)]
    ], colWidths=[5.67*cm]*3)
    t_stats.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), GRIS_CLAR),
        ('BOX',        (0,0), (-1,-1), 1.5, ROJO),
        ('TOPPADDING',   (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 12))

    if especialidades:
        header = [_p(h, ParagraphStyle('th', fontSize=9, textColor=BLANCO, fontName='Helvetica-Bold'))
                  for h in ['#', 'Especialidad', 'Total Citas', 'Medicos Asignados']]
        rows = [header]
        for i, esp in enumerate(especialidades, 1):
            medicos_unicos, seen = [], set()
            for cita in esp.citas:
                if cita.medico_id not in seen:
                    seen.add(cita.medico_id)
                    medicos_unicos.append(cita.medico.nombre)
            medicos_str = ('• ' + '\n• '.join(medicos_unicos)) if medicos_unicos else 'Sin medicos asignados'
            rows.append([
                _p(str(i), st_td),
                _ph(f'<b>{esp.nombre}</b>', st_td),
                _ph(f'<b>{len(esp.citas)}</b>', ParagraphStyle('cen', fontSize=9, alignment=TA_CENTER)),
                _p(medicos_str, st_medico),
            ])
        t = Table(rows, colWidths=[1.5*cm, 6*cm, 3*cm, 6.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), ROJO),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [BLANCO, ROJO_CLAR]),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
            ('RIGHTPADDING',  (0,0), (-1,-1), 8),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(t)
        story.append(Spacer(1, 16))

        max_esp   = max(especialidades, key=lambda e: len(e.citas), default=None)
        sin_citas = sum(1 for e in especialidades if len(e.citas) == 0)
        t_res = Table([
            [_ph('<b>Resumen Ejecutivo</b>', ParagraphStyle('rh', fontSize=11, textColor=ROJO, fontName='Helvetica-Bold'))],
            [_ph(f'<b>Especialidad mas solicitada:</b> {max_esp.nombre if max_esp else "N/A"} ({len(max_esp.citas) if max_esp else 0} citas)',
                ParagraphStyle('rb', fontSize=9))],
            [_ph(f'<b>Especialidades sin citas:</b> {sin_citas}', ParagraphStyle('rb', fontSize=9))],
        ], colWidths=[17*cm])
        t_res.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), GRIS_CLAR),
            ('LINEBEFORE', (0,0), (0,-1), 4, ROJO),
            ('LEFTPADDING',  (0,0), (-1,-1), 12),
            ('TOPPADDING',   (0,0), (-1,-1), 6),
            ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ]))
        story.append(KeepTogether(t_res))
    else:
        story.append(_p('No hay especialidades registradas.', st_sub))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=1, color=ROJO))
    story.append(Spacer(1, 4))
    story.append(_p('Generado automaticamente por el Sistema de Gestion IPS FULANO', st_foot))

    _cv = _make_canvas()
    doc.build(story, onFirstPage=_cv, onLaterPages=_cv)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════
# 5. TIQUETE DE CITA
# ════════════════════════════════════════════════════════════════════════════
def generar_tiquete_pdf(cita):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=3*cm, rightMargin=3*cm,
                            topMargin=3*cm, bottomMargin=3*cm)
    story = []

    st_titulo = ParagraphStyle('t', fontSize=18, textColor=ROJO,
                               alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=4)
    st_sub    = ParagraphStyle('s', fontSize=11, textColor=GRIS, alignment=TA_CENTER, spaceAfter=12)
    st_label  = ParagraphStyle('l', fontSize=10, fontName='Helvetica-Bold', textColor=ROJO)
    st_valor  = ParagraphStyle('v', fontSize=10, textColor=NEGRO)
    st_foot   = ParagraphStyle('f', fontSize=9, textColor=GRIS, alignment=TA_CENTER)

    logo = _get_logo(2.5*cm, 2.5*cm)
    story.append(Table([[logo, _p('IPS FULANO', st_titulo)]], colWidths=[3*cm, 12*cm]))
    story.append(HRFlowable(width='100%', thickness=2, color=ROJO, spaceAfter=16))
    story.append(_p('Comprobante de Cita Medica', st_sub))

    datos = [
        ('Paciente',     f'{cita.paciente.nombre} ({cita.paciente.identificacion})'),
        ('Medico',       cita.medico.nombre),
        ('Especialidad', cita.especialidad.nombre),
        ('Fecha y Hora', cita.fecha.strftime('%d/%m/%Y a las %H:%M')),
        ('Estado',       cita.estado),
    ]
    t = Table([[_p(lbl, st_label), _p(val, st_valor)] for lbl, val in datos],
              colWidths=[5*cm, 10*cm])
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [ROJO_CLAR, BLANCO]),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ('RIGHTPADDING',  (0,0), (-1,-1), 10),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
        ('LINEBEFORE',    (0,0), (0,-1),  3, ROJO),
    ]))
    story.append(t)
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width='100%', thickness=1, color=ROJO))
    story.append(Spacer(1, 8))
    story.append(_p('Por favor, presente este documento el dia de su cita.', st_foot))
    story.append(_p('Correo: ipsfulano@fundacioneudes.co  |  Tel: 601-7559343', st_foot))

    doc.build(story)
    return buf.getvalue()
