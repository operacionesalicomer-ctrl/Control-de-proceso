import streamlit as st
import pandas as pd
import re
import unicodedata
import time
from datetime import datetime, timedelta
from supabase import create_client, Client
from google import genai
from google.genai import types

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Reporte Productivo", page_icon="🍞", layout="wide")

MODELO_GEMINI = "gemini-3.8-flash"

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_resource
def init_gemini():
    api_key = st.secrets.get("GEMINI_API_KEY", None)
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error(f"⚠️ Error de conexión a Supabase: {e}")
    st.stop()

client_ai = init_gemini()

def llamar_gemini_con_reintento(prompt, temperatura=0.2, max_intentos=4):
    """Llama a Gemini con reintento automático (usado solo para el Reporte Semanal)."""
    for intento in range(max_intentos):
        try:
            response = client_ai.models.generate_content(
                model=MODELO_GEMINI,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperatura)
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            if ("503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str) and intento < max_intentos - 1:
                time.sleep(3 * (intento + 1))
            else:
                raise e

# --- 2. SISTEMA DE LOGIN Y MEMORIA ---
if 'usuario_logeado' not in st.session_state:
    st.session_state.usuario_logeado = False
    st.session_state.rol = None
    st.session_state.nombre_usuario = None

if 'form_data' not in st.session_state:
    st.session_state.form_data = {}

def get_val(key, default):
    return st.session_state.form_data.get(key, default)

def set_val(key, val):
    st.session_state.form_data[key] = val

def safe_index(lst, val):
    return lst.index(val) if val in lst else 0

if not st.session_state.usuario_logeado:
    st.title("🔐 Acceso al Sistema")
    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")
        if submit:
            res = supabase.table("usuarios").select("*").eq("usuario", usuario).eq("clave", clave).execute()
            if len(res.data) > 0:
                user_data = res.data[0]
                st.session_state.usuario_logeado = True
                st.session_state.rol = user_data['rol']
                st.session_state.nombre_usuario = user_data['usuario']
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.stop()

# --- 3. DATOS MAESTROS ---
@st.cache_data(ttl=10)
def fetch_data(table):
    return supabase.table(table).select("*").order("id").execute().data

def get_id(db, nombre):
    if not isinstance(nombre, str):
        return None
    objetivo = nombre.strip().lower()
    return next((item['id'] for item in db if item['nombre'].strip().lower() == objetivo), None)

plantas_db = fetch_data("plantas")
productos_db = fetch_data("productos")
areas_db = fetch_data("areas")
metricas_db = fetch_data("metricas")
usuarios_db = fetch_data("usuarios")

nombres_plantas = [p['nombre'] for p in plantas_db] if plantas_db else []
nombres_productos = [p['nombre'] for p in productos_db] if productos_db else []
nombres_areas = [a['nombre'] for a in areas_db] if areas_db else []
nombres_metricas = [m['nombre'] for m in metricas_db] if metricas_db else []

opciones_dinamicas = ["Seleccione un producto...", "Línea Detenida"] + nombres_productos

# --- 4. BARRA LATERAL ---
with st.sidebar:
    st.write(f"👤 **Usuario:** {st.session_state.nombre_usuario}")
    st.write(f"🛡️ **Rol:** {st.session_state.rol.title()}")
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.usuario_logeado = False
        st.session_state.rol = None
        st.session_state.nombre_usuario = None
        st.session_state.form_data = {}
        st.rerun()
    st.divider()

    modo_app = st.radio(
        "📌 Módulo",
        ["⚡ Carga WhatsApp (Plantilla)", "📊 Reporte Semanal (IA)", "📝 Formulario Manual"]
    )
    st.divider()

    if st.session_state.rol == 'admin':
        st.subheader("🛠️ Administración")

        with st.expander("⚙️ Mantenedor Usuarios"):
            with st.form("crear_usuario"):
                nuevo_user = st.text_input("Nuevo Usuario")
                nueva_clave = st.text_input("Contraseña", type="password")
                nuevo_rol = st.selectbox("Rol", ["jefe de turno", "admin"])
                if st.form_submit_button("Crear"):
                    supabase.table("usuarios").insert({"usuario": nuevo_user, "clave": nueva_clave, "rol": nuevo_rol}).execute()
                    fetch_data.clear()
                    st.rerun()
            for u in usuarios_db:
                c1, c2 = st.columns([4, 1])
                c1.write(f"👤 {u['usuario']}")
                if u['usuario'] != 'admin' and c2.button("❌", key=f"del_u_{u['id']}"):
                    supabase.table("usuarios").delete().eq("id", u['id']).execute()
                    fetch_data.clear()
                    st.rerun()

        with st.expander("🥖 Mantenedor Productos"):
            with st.form("crear_producto"):
                nuevo_prod = st.text_input("Nuevo Producto")
                if st.form_submit_button("Agregar") and nuevo_prod:
                    try:
                        supabase.table("productos").insert({"nombre": nuevo_prod.strip()}).execute()
                        fetch_data.clear()
                        st.rerun()
                    except Exception:
                        st.error("⚠️ Error: El producto ya existe o no se pudo guardar.")

            for p in productos_db:
                cp1, cp2 = st.columns([4, 1])
                cp1.caption(f"🥖 {p['nombre']}")
                if cp2.button("❌", key=f"del_p_{p['id']}"):
                    supabase.table("productos").delete().eq("id", p['id']).execute()
                    fetch_data.clear()
                    st.rerun()

        with st.expander("⬆️ Carga Masiva (Excel)"):
            st.caption("Columnas: Fecha | Planta | Turno | Area | Maquina | Producto | Metrica | Valor")
            archivo_subido = st.file_uploader("Sube historial en Excel", type=["xlsx", "xls"])

            if archivo_subido is not None:
                if st.button("Procesar y Cargar Data", use_container_width=True):
                    try:
                        df = pd.read_excel(archivo_subido)
                        df.columns = df.columns.str.strip().str.title()
                        errores = 0
                        turnos_unicos = df[['Fecha', 'Planta', 'Turno']].drop_duplicates()

                        with st.spinner('Cargando datos a Supabase...'):
                            for _, fila_turno in turnos_unicos.iterrows():
                                p_id = get_id(plantas_db, str(fila_turno['Planta']))
                                if p_id:
                                    data_t = {
                                        "fecha": str(pd.to_datetime(fila_turno['Fecha']).date()),
                                        "planta_id": p_id,
                                        "turno": str(fila_turno['Turno'])
                                    }
                                    try:
                                        res_t = supabase.table("reporte_turnos").insert(data_t).execute()
                                        if res_t.data:
                                            turno_id = res_t.data[0]['id']
                                            detalles_df = df[
                                                (df['Fecha'] == fila_turno['Fecha']) &
                                                (df['Turno'] == fila_turno['Turno']) &
                                                (df['Planta'] == fila_turno['Planta'])
                                            ]
                                            detalles_insert = []
                                            for _, det in detalles_df.iterrows():
                                                a_id = get_id(areas_db, str(det['Area']))
                                                pr_id = get_id(productos_db, str(det['Producto']))
                                                m_id = get_id(metricas_db, str(det['Metrica']))
                                                val = float(det['Valor']) if pd.notna(det['Valor']) else 0.0

                                                if a_id and pr_id and m_id and val > 0:
                                                    sub_area = str(det['Maquina']) if pd.notna(det['Maquina']) and str(det['Maquina']).strip() != "" else None
                                                    detalles_insert.append({
                                                        "reporte_id": turno_id, "area_id": a_id,
                                                        "producto_id": pr_id, "metrica_id": m_id,
                                                        "sub_area": sub_area, "valor": val
                                                    })
                                            if detalles_insert:
                                                supabase.table("reporte_detalles").insert(detalles_insert).execute()
                                    except Exception:
                                        errores += 1

                        if errores > 0:
                            st.warning(f"⚠️ Se omitieron {errores} turnos (probablemente ya existían).")
                        else:
                            st.success("✅ Carga masiva completada con éxito.")
                    except Exception as e:
                        st.error(f"❌ Error leyendo el archivo. Detalle: {e}")

# ==========================================
# MÓDULO A: PARSER BLINDADO LÍNEA POR LÍNEA
# ==========================================
def _validar_fecha_dmy(d_str, m_str, y_str):
    """Valida y normaliza una fecha D/M/Y a YYYY-MM-DD. Devuelve None si es imposible."""
    try:
        d, m = int(d_str), int(m_str)
        y = int(f"20{y_str}") if len(y_str) == 2 else int(y_str)
        if not (2020 <= y <= 2035):
            return None
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None

TURNOS_VALIDOS = ("Mañana", "Tarde", "Noche")

def _normalizar_unicode(texto):
    """Normaliza Unicode a NFC (evita bugs iOS/WhatsApp tipo 'MañAna' o 'PeñAloza') y limpia caracteres invisibles."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFC", str(texto))
    for ch in ("\u200e", "\u200f", "\ufeff", "\u200b"):
        t = t.replace(ch, "")
    return t.replace("\u202f", " ").replace("\u00a0", " ")

def _sin_tildes(texto):
    """Devuelve texto sin tildes ni diacríticos para comparaciones seguras."""
    t = unicodedata.normalize("NFD", _normalizar_unicode(texto))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

def normalizar_turno(texto_raw):
    """Lista blanca estricta: solo permite Mañana, Tarde o Noche. Nunca deja pasar texto libre."""
    limpio = _normalizar_unicode(texto_raw).strip()
    if not limpio:
        return "Sin definir", "Turno vacío"
    base = _sin_tildes(limpio).lower()
    coincidencias = []
    if any(k in base for k in ["manana", "dia", "am"]):
        coincidencias.append("Mañana")
    if "tarde" in base:
        coincidencias.append("Tarde")
    if "noche" in base:
        coincidencias.append("Noche")

    if len(coincidencias) == 1:
        return coincidencias[0], None
    if len(coincidencias) > 1:
        return "Sin definir", "Turno dejó la plantilla sin elegir (Mañana/Tarde/Noche)"
    return "Sin definir", f"Turno no reconocido ('{limpio[:20]}')"

def normalizar_jefe(texto_raw):
    """Normaliza nombre del jefe de turno en NFC sin espacios duplicados."""
    limpio = re.sub(r'\s+', ' ', _normalizar_unicode(texto_raw)).strip(" -:|.")
    return limpio.title() if limpio else ""

def extraer_bloques_whatsapp(texto_completo):
    """Separa un chat exportado (.txt) y devuelve lista de (texto_mensaje, fecha_chat_fallback)."""
    texto_limpio = _normalizar_unicode(texto_completo)
    patron_mensaje = r'(?=\[?\d{1,2}[/-]\d{1,2}[/-]\d{2,4},?\s+\d{1,2}:\d{2})'
    mensajes = re.split(patron_mensaje, texto_limpio)

    resultados = []
    for m in mensajes:
        m_strip = m.strip()
        if "REPORTE DE TURNO" not in m_strip.upper():
            continue
        m_ts = re.match(r'^\[?(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', m_strip)
        fecha_wa = _validar_fecha_dmy(*m_ts.groups()) if m_ts else None
        resultados.append((m_strip, fecha_wa))

    if not resultados and "REPORTE DE TURNO" in texto_limpio.upper():
        resultados.append((texto_limpio.strip(), None))
    return resultados

def _limpiar_texto(texto):
    """Normaliza Unicode NFC, elimina negritas/tachados y junta decimales separados por espacio."""
    t = _normalizar_unicode(texto).replace("*", "").replace("~", "")
    t = re.sub(r'(\d)[ \t]+([.,])[ \t]*(\d)', r'\1\2\3', t)
    t = re.sub(r'(\d)[ \t]*([.,])[ \t]+(\d)', r'\1\2\3', t)
    return t

def _num(texto):
    """Extrae el primer número positivo válido (entero o decimal)."""
    if not texto:
        return 0.0
    limpio = re.sub(r'[_\-]+', ' ', texto).strip()
    m = re.search(r'(\d+(?:[.,]\d+)?)', limpio)
    if not m:
        return 0.0
    try:
        val = float(m.group(1).replace(',', '.'))
        if val <= 0 or val > 50000:
            return 0.0
        return val
    except ValueError:
        return 0.0

def _suma_nums(texto):
    """Si hay sumas tipo '6 rústico + 11 europastry', suma el primer número de cada término."""
    if not texto:
        return 0.0
    limpio = re.sub(r'[_\-]+', ' ', texto).strip()
    if '+' in limpio:
        return sum(_num(p) for p in limpio.split('+'))
    return _num(limpio)

def _valor_linea(bloque, patron_etiqueta, sumar_mas=False):
    """Evalúa ESTRICTAMENTE línea por línea. Nunca salta ni roba números de la línea siguiente."""
    for linea in bloque.splitlines():
        m = re.match(rf'^[ \t]*(?:{patron_etiqueta})(?:[ \t]*\([^)]*\))?[ \t]*[:=]?[ \t]*(.*)$', linea, flags=re.IGNORECASE)
        if m:
            resto = m.group(1).strip()
            return _suma_nums(resto) if sumar_mas else _num(resto)
    return 0.0

def _texto_linea(bloque, patron_etiqueta):
    """Busca una etiqueta en una sola línea y devuelve el texto limpio."""
    for linea in bloque.splitlines():
        m = re.match(rf'^[ \t]*(?:{patron_etiqueta})[ \t]*[:=][ \t]*(.*)$', linea, flags=re.IGNORECASE)
        if m:
            return re.sub(r'_+', '', m.group(1)).strip(" -:|.")
    return ""

def parsear_reporte_plantilla(texto_crudo, fecha_wa_fallback=None):
    """Parser blindado línea por línea tolerante a typos y variantes reales de planta."""
    texto = _limpiar_texto(texto_crudo)
    alertas = []

    patrones_sec = [
        ("masas", r'(?im)^[ \t]*(?:1[ \t]*[\.\-\)][ \t]*)?MASAS?\b'),
        ("camara", r'(?im)^[ \t]*(?:2[ \t]*[\.\-\)][ \t]*)?C[AÁ]MARAS?\b'),
        ("corte", r'(?im)^[ \t]*(?:3[ \t]*[\.\-\)][ \t]*)?CORTES?\b'),
        ("horno", r'(?im)^[ \t]*(?:4[ \t]*[\.\-\)][ \t]*)?HORNOS?\b'),
        ("envasado", r'(?im)^[ \t]*(?:5[ \t]*[\.\-\)][ \t]*)?ENVASADOS?\b'),
        ("merma_cocido", r'(?im)^[ \t]*(?:6[ \t]*[\.\-\)][ \t]*)?MER[ \t]*MA[ \t]+PAN\b'),
        ("merma_masa", r'(?im)^[ \t]*(?:7[ \t]*[\.\-\)][ \t]*)?MER[ \t]*MA[ \t]+DE[ \t]+MASA\b'),
        ("insumos", r'(?im)^[ \t]*(?:[58][ \t]*[\.\-\)][ \t]*)?INSUMOS?\b'),
        ("novedades", r'(?im)^[ \t]*(?:9[ \t]*[\.\-\)][ \t]*)?NOVEDAD(?:ES)?\b'),
    ]

    posiciones = []
    for nombre, pat in patrones_sec:
        m = re.search(pat, texto)
        if m:
            posiciones.append((m.start(), nombre))
    posiciones.sort()

    secciones = {}
    if posiciones:
        secciones["header"] = texto[:posiciones[0][0]]
        for i, (pos, nombre) in enumerate(posiciones):
            fin = posiciones[i + 1][0] if i + 1 < len(posiciones) else len(texto)
            secciones[nombre] = texto[pos:fin]
    else:
        secciones["header"] = texto
        alertas.append("Sin secciones numeradas reconocibles")

    detalles = []

    def add(area, producto, metrica, valor, sub_area=None):
        if valor and valor > 0:
            detalles.append({
                "area": area,
                "producto": producto,
                "metrica": metrica,
                "sub_area": sub_area,
                "valor": round(float(valor), 2)
            })

    # --- CABECERA ---
    hdr = secciones.get("header", "")
    m_fecha = re.search(r'(?i)Fecha[ \t]*[:=]?[ \t]*(\d{1,2})[ \t]*[/\-\.][ \t]*(\d{1,2})[ \t]*[/\-\.][ \t]*(\d{2,4})', hdr)
    fecha_iso = _validar_fecha_dmy(*m_fecha.groups()) if m_fecha else None

    if not fecha_iso:
        if fecha_wa_fallback:
            fecha_iso = fecha_wa_fallback
            alertas.append("Fecha faltante/inválida (se usó fecha del chat)")
        else:
            fecha_iso = str(datetime.now().date())
            alertas.append("Fecha faltante (se usó fecha de hoy)")

    turno_raw = _texto_linea(hdr, r'Turno')
    turno, alerta_turno = normalizar_turno(turno_raw)
    if alerta_turno:
        alertas.append(alerta_turno)

    jefe_turno = normalizar_jefe(_texto_linea(hdr, r'Jefe[ \t]+de[ \t]+turno'))
    if not jefe_turno:
        alertas.append("Falta Jefe de turno")

    dotacion_total = _valor_linea(hdr, r'Dotaci[oó]n')
    if dotacion_total == 0:
        m_dot_alt = re.search(r'(?i)(?:se[ \t]+trabaj[oó][ \t]+con|dotaci[oó]n(?:[ \t]+personal)?)[ \t]*[:=]?[ \t]*(\d+)[ \t]*personas?', texto)
        if m_dot_alt:
            dotacion_total = float(m_dot_alt.group(1))
    add("General", "General", "Operarios", dotacion_total)

    # --- 1. MASAS (batch) ---
    s_masas = secciones.get("masas", "")
    add("Masa", "Integral", "Batch", _valor_linea(s_masas, r'Integral'))
    add("Masa", "Rustica", "Batch", _valor_linea(s_masas, r'R[uú]stic[ao]'))
    add("Masa", "Toscano", "Batch", _valor_linea(s_masas, r'Toscano'))
    add("Masa", "Europastry", "Batch", _valor_linea(s_masas, r'Europastr[iy]'))
    add("Masa", "Otros", "Batch", _valor_linea(s_masas, r'Otros?'))
    add("Masa", "General", "Reproceso", _valor_linea(s_masas, r'Reproceso'))

    # --- 2. CÁMARA (batch) ---
    s_cam = secciones.get("camara", "")
    add("Cámara", "Integral", "Batch", _valor_linea(s_cam, r'Integral'))
    add("Cámara", "Rustica", "Batch", _valor_linea(s_cam, r'R[uú]stic[ao]'))
    add("Cámara", "Toscano", "Batch", _valor_linea(s_cam, r'Toscano'))
    add("Cámara", "Europastry", "Batch", _valor_linea(s_cam, r'Europastr[iy]'))
    add("Cámara", "General", "Reproceso", _valor_linea(s_cam, r'Reproceso'))

    # --- 3. CORTE ---
    s_corte = secciones.get("corte", "")
    batch_por_linea = False
    for num_l in ["1", "2", "3"]:
        linea_nom = f"C{num_l}"
        for lin in s_corte.splitlines():
            m_lin = re.match(rf'^[ \t]*C[ \t]*{num_l}[ \t]*[:\-](.*)$', lin, flags=re.IGNORECASE)
            if m_lin:
                txt_l = m_lin.group(1)
                m_b = re.search(r'(?i)ba(?:t)?ch[ \t]*[:=_]?[ \t]*(\d+(?:[.,]\d+)?)', txt_l)
                m_r = re.search(r'(?i)reproce(?:so)?[ \t]*[:=_]?[ \t]*(\d+(?:[.,]\d+)?)', txt_l)
                m_d = re.search(r'(?i)dotaci[oó]n[ \t]*[:=_]?[ \t]*(\d+(?:[.,]\d+)?)', txt_l)
                txt_sin_dot = re.split(r'(?i)dotaci[oó]n', txt_l)[0]
                m_c = re.search(r'(?i)carros?[ \t]*[:=_]?[ \t]*([^|/]*)', txt_sin_dot)
                if m_b:
                    add("Corte", "General", "Batch", _num(m_b.group(1)), linea_nom)
                    batch_por_linea = True
                if m_r:
                    add("Corte", "General", "Reproceso", _num(m_r.group(1)), linea_nom)
                if m_c:
                    add("Corte", "General", "Carros", _suma_nums(m_c.group(1)), linea_nom)
                if m_d:
                    add("Corte", "General", "Operarios", _num(m_d.group(1)), linea_nom)

    if not batch_por_linea:
        for lin in s_corte.splitlines():
            m_tb = re.search(r'(?i)Total[ \t]+(?:de[ \t]+)?ba(?:t)?ch(?:es)?[ \t]*[:=]?[ \t]*(\d+(?:[.,]\d+)?)', lin)
            if m_tb:
                add("Corte", "General", "Batch", _num(m_tb.group(1)), None)
                m_tr = re.search(r'(?i)(\d+(?:[.,]\d+)?)[ \t]*reproce', lin)
                if m_tr:
                    add("Corte", "General", "Reproceso", _num(m_tr.group(1)), None)

    # --- 4. HORNO (carros) ---
    s_horno = secciones.get("horno", "")
    h_rus = _valor_linea(s_horno, r'R[uú]stic[ao]')
    h_tos = _valor_linea(s_horno, r'Toscano')
    h_int = _valor_linea(s_horno, r'Integral')
    h_eur = _valor_linea(s_horno, r'Europastr[iy]')
    if any([h_rus, h_tos, h_int, h_eur]):
        add("Horno", "Rustica", "Carros", h_rus)
        add("Horno", "Toscano", "Carros", h_tos)
        add("Horno", "Integral", "Carros", h_int)
        add("Horno", "Europastry", "Carros", h_eur)
    else:
        add("Horno", "General", "Carros", _valor_linea(s_horno, r'Horneados'))

    add("Horno", "General", "Abatidor", _valor_linea(s_horno, r'(?:A[ \t]+)?abatidor', sumar_mas=True))
    add("Horno", "General", "Ultracongelado", _valor_linea(s_horno, r'(?:A[ \t]+)?ultra[ \t]*co[ng]+elado', sumar_mas=True))
    add("Horno", "General", "Crudo", _valor_linea(s_horno, r'Quedan[ \t]+por[ \t]+hornear|Crudos?'))

    # --- 5. ENVASADO (cajas) ---
    s_env = secciones.get("envasado", "")
    add("Envasado", "Integral", "Cajas", _valor_linea(s_env, r'Integral'))
    add("Envasado", "Rustica Familiar", "Cajas", _valor_linea(s_env, r'R[uú]stic[ao][ \t]+familiar'))
    add("Envasado", "Rustica", "Cajas", _valor_linea(s_env, r'R[uú]stic[ao](?![ \t]+(?:familiar|c[oó]ctel))'))
    add("Envasado", "Toscano", "Cajas", _valor_linea(s_env, r'Toscano'))
    add("Envasado", "Europastry", "Cajas", _valor_linea(s_env, r'Europastr[iy]'))
    add("Envasado", "Otros", "Cajas", _valor_linea(s_env, r'Otros?'))

    # --- 6. MERMA PAN COCIDO (kg) ---
    s_mc = secciones.get("merma_cocido", "")
    add("Mermas y Polveo", "General", "Merma Deforme", _valor_linea(s_mc, r'Deforme'))
    add("Mermas y Polveo", "General", "Merma Sin Greña", _valor_linea(s_mc, r'Sin[ \t]+gre[ñn]a'))
    add("Mermas y Polveo", "General", "Merma Crudo", _valor_linea(s_mc, r'Crudo'))
    add("Mermas y Polveo", "General", "Merma Sobre Cocción", _valor_linea(s_mc, r'Sobre[ \t]+cocci[oó]n'))
    add("Mermas y Polveo", "General", "Merma Pan a Piso", _valor_linea(s_mc, r'(?:Pan[ \t]+)?a(?:l)?[ \t]+piso'))
    add("Mermas y Polveo", "General", "Merma Manchado", _valor_linea(s_mc, r'(?:Merma[ \t]+pan[ \t]+)?manchado'))

    # --- 7. MERMA DE MASA Y OTROS (kg) ---
    s_mm = secciones.get("merma_masa", "")
    add("Mermas y Polveo", "General", "Merma Cruda", _valor_linea(s_mm, r'Merma[ \t]+de[ \t]+masa'))
    add("Mermas y Polveo", "General", "Reproceso", _valor_linea(s_mm, r'Reproceso'))
    add("Mermas y Polveo", "General", "Barrido", _valor_linea(s_mm, r'Barrido'))

    # --- 8. INSUMOS ---
    s_ins = secciones.get("insumos", "")
    add("Insumos", "General", "Semilla", _valor_linea(s_ins, r'Semilla[ \t]+usada'))
    add("Insumos", "General", "Harina", _valor_linea(s_ins, r'Harina[ \t]+usada'))
    add("Insumos", "General", "Polveo", _valor_linea(s_ins, r'Harina[ \t]+polvor?eo'))
    add("Insumos", "General", "Limpieza Insumos", _valor_linea(s_ins, r'Semilla[ \t]+y[ \t]+harina[ \t]+de[ \t]+limpieza'))

    for lin in s_ins.splitlines():
        m_rec = re.match(r'^[ \t]*Recuperado[ \t]*[:=](.*)$', lin, flags=re.IGNORECASE)
        if m_rec:
            txt_rec = m_rec.group(1)
            m_rs = re.search(r'(?i)semilla[ \t]*[:=_]?[ \t]*(\d+(?:[.,]\d+)?)', txt_rec)
            m_rh = re.search(r'(?i)harina[ \t]*[:=_]?[ \t]*(\d+(?:[.,]\d+)?)', txt_rec)
            if m_rs: add("Insumos", "General", "Semilla Recuperada", _num(m_rs.group(1)))
            if m_rh: add("Insumos", "General", "Harina Recuperada", _num(m_rh.group(1)))

    # --- 9. NOVEDADES ---
    s_nov = secciones.get("novedades", "")
    causa = _texto_linea(s_nov, r'Causa[ \t]+principal[ \t]+de[ \t]+merma')
    fallas = _texto_linea(s_nov, r'Detenciones[ \t]+o[ \t]+fallas')
    if causa or fallas:
        partes_nov = []
        if causa: partes_nov.append(f"Causa principal de merma: {causa}")
        if fallas: partes_nov.append(f"Detenciones o fallas: {fallas}")
        novedades_final = " | ".join(partes_nov)
    else:
        lineas_nov = [re.sub(r'_+', '', l).strip() for l in s_nov.splitlines()[1:] if re.sub(r'_+', '', l).strip()]
        novedades_final = " | ".join(lineas_nov)

    if len(detalles) == 0:
        alertas.append("Sin métricas numéricas (posible plantilla vacía)")

    return {
        "fecha": fecha_iso,
        "turno": turno,
        "jefe_turno": jefe_turno,
        "novedades": novedades_final,
        "detalles": detalles,
        "alertas": alertas,
        "estado": "🟢 Listo" if not alertas else ("🔴 Vacío" if len(detalles) == 0 else "⚠️ Revisar"),
        "incluir": len(detalles) > 0,
        "texto_original": texto_crudo
    }

def auditar_duplicados(resultados, planta_id):
    """Cruza los reportes contra Supabase y contra sí mismos para evitar choques."""
    existentes_bd = set()
    if planta_id:
        try:
            res = supabase.table("reporte_turnos").select("fecha, turno").eq("planta_id", planta_id).execute()
            existentes_bd = {(r['fecha'], _sin_tildes(str(r['turno'])).strip().lower()) for r in res.data}
        except Exception:
            pass

    ultima_pos = {}
    for idx, rep in enumerate(resultados):
        clave = (rep['fecha'], _sin_tildes(rep['turno']).strip().lower())
        ultima_pos[clave] = idx

    for idx, rep in enumerate(resultados):
        clave = (rep['fecha'], _sin_tildes(rep['turno']).strip().lower())
        if clave in existentes_bd:
            rep['estado'] = "🟡 Ya en BD"
            rep['incluir'] = False
            rep['alertas'].append("Turno ya registrado en Supabase")
        elif ultima_pos[clave] != idx:
            rep['estado'] = "🟠 Reemplazado"
            rep['incluir'] = False
            rep['alertas'].append("Hay una versión posterior de este mismo turno en el archivo")

    return resultados

def render_carga_whatsapp():
    st.title("⚡ Carga Blindada desde WhatsApp")

    planta_sel = st.selectbox("🏭 Planta correspondiente a los reportes", nombres_plantas)

    tab_txt, tab_pegar = st.tabs(["📄 Subir archivo .txt del chat", "📋 Pegar un reporte suelto"])
    texto_crudo = ""

    with tab_txt:
        archivo_txt = st.file_uploader("Sube el chat exportado de WhatsApp sin multimedia (.txt)", type=["txt"])
        if archivo_txt:
            texto_crudo = archivo_txt.read().decode("utf-8", errors="ignore")

    with tab_pegar:
        texto_pegado = st.text_area("Pega aquí el mensaje de WhatsApp", height=250)
        if texto_pegado:
            texto_crudo = texto_pegado

    if texto_crudo:
        bloques = extraer_bloques_whatsapp(texto_crudo)
        st.info(f"🔎 Se detectaron **{len(bloques)}** mensajes con 'REPORTE DE TURNO'.")

        if len(bloques) > 0:
            if st.button("⚡ Analizar y Validar Reportes", type="primary"):
                inicio = time.time()
                p_id = get_id(plantas_db, planta_sel)
                resultados = [parsear_reporte_plantilla(txt, f_wa) for txt, f_wa in bloques]
                resultados = auditar_duplicados(resultados, p_id)
                duracion = time.time() - inicio
                st.session_state.wa_resultados = resultados
                st.session_state.wa_planta = planta_sel
                st.success(f"✅ {len(resultados)} reportes analizados y auditados en **{duracion:.2f} segundos**.")

    if "wa_resultados" in st.session_state and st.session_state.wa_resultados:
        res_list = st.session_state.wa_resultados
        st.divider()
        st.subheader(f"📋 Panel de Validación — Planta: {st.session_state.wa_planta}")

        n_listos = sum(1 for r in res_list if r['estado'] == "🟢 Listo")
        n_revisar = sum(1 for r in res_list if r['estado'] == "⚠️ Revisar")
        n_dup = sum(1 for r in res_list if r['estado'] in ["🟡 Ya en BD", "🟠 Reemplazado"])
        n_vacios = sum(1 for r in res_list if r['estado'] == "🔴 Vacío")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🟢 Listos", n_listos)
        k2.metric("⚠️ Con alertas", n_revisar)
        k3.metric("🟡 Ya en BD / Dup.", n_dup)
        k4.metric("🔴 Vacíos", n_vacios)

        df_resumen = pd.DataFrame([
            {
                "ID": i,
                "Guardar": r["incluir"],
                "Estado": r["estado"],
                "Fecha": r["fecha"],
                "Turno": r["turno"],
                "Jefe": r["jefe_turno"] or "-",
                "Datos": len(r["detalles"]),
                "Observaciones": " | ".join(r["alertas"]) if r["alertas"] else "OK"
            }
            for i, r in enumerate(res_list)
        ])

        ocultar_bd = st.checkbox("Ocultar reportes que ya existen en BD o fueron reemplazados", value=True)
        df_vista = df_resumen[~df_resumen["Estado"].isin(["🟡 Ya en BD", "🟠 Reemplazado"])] if ocultar_bd else df_resumen

        df_resumen_edit = st.data_editor(
            df_vista,
            use_container_width=True,
            hide_index=True,
            disabled=["ID", "Estado", "Datos", "Observaciones"],
            column_config={
                "Guardar": st.column_config.CheckboxColumn("Guardar", default=True),
                "Fecha": st.column_config.TextColumn("Fecha (YYYY-MM-DD)"),
                "Turno": st.column_config.SelectboxColumn("Turno", options=["Mañana", "Tarde", "Noche", "Sin definir"]),
            },
            key="tabla_resumen_wa"
        )

        for _, row in df_resumen_edit.iterrows():
            idx_r = int(row["ID"])
            res_list[idx_r]["incluir"] = bool(row["Guardar"])
            res_list[idx_r]["fecha"] = str(row["Fecha"]).strip()
            res_list[idx_r]["turno"] = str(row["Turno"]).strip()
            res_list[idx_r]["jefe_turno"] = "" if row["Jefe"] == "-" else str(row["Jefe"]).strip()

        st.divider()
        st.subheader("🔍 Inspeccionar o corregir un reporte específico")
        opciones_insp = [
            f"#{i} | {r['estado']} | {r['fecha']} | {r['turno']} | {r['jefe_turno'] or 'Sin jefe'} ({len(r['detalles'])} datos)"
            for i, r in enumerate(res_list)
        ]
        sel_insp = st.selectbox("Selecciona el reporte a revisar en detalle:", opciones_insp)
        idx_sel = int(sel_insp.split("|")[0].replace("#", "").strip())
        rep_sel = res_list[idx_sel]

        if rep_sel["alertas"]:
            st.warning("⚠️ Alertas detectadas: " + " • ".join(rep_sel["alertas"]))

        col_ed, col_orig = st.columns([2, 1])
        with col_ed:
            rep_sel["novedades"] = st.text_area("Novedades", rep_sel.get("novedades", ""), key=f"nov_sel_{idx_sel}")
            df_det = pd.DataFrame(rep_sel.get("detalles", []))
            if df_det.empty:
                df_det = pd.DataFrame(columns=["area", "producto", "metrica", "sub_area", "valor"])

            df_det_edit = st.data_editor(
                df_det,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "area": st.column_config.SelectboxColumn("Área", options=nombres_areas, required=True),
                    "producto": st.column_config.SelectboxColumn("Producto", options=nombres_productos, required=True),
                    "metrica": st.column_config.SelectboxColumn("Métrica", options=nombres_metricas, required=True),
                    "sub_area": st.column_config.TextColumn("Línea / Máquina"),
                    "valor": st.column_config.NumberColumn("Valor", min_value=0.0, format="%.2f")
                },
                key=f"det_sel_{idx_sel}"
            )
            rep_sel["detalles"] = df_det_edit.to_dict(orient="records")

        with col_orig:
            st.caption("📱 Mensaje original de WhatsApp")
            st.text_area("Original", rep_sel.get("texto_original", ""), height=320, disabled=True, label_visibility="collapsed", key=f"orig_{idx_sel}")

        st.divider()
        a_guardar = [r for r in res_list if r.get("incluir", False)]
        col_g1, col_g2 = st.columns([3, 1])

        if col_g1.button(f"💾 Confirmar y Guardar {len(a_guardar)} Reportes en Supabase", type="primary", use_container_width=True, disabled=(len(a_guardar) == 0)):
            p_id = get_id(plantas_db, st.session_state.wa_planta)
            guardados, omitidos, filas_descartadas = 0, 0, 0
            barra = st.progress(0)

            for pos, rep in enumerate(a_guardar):
                turno_id = None
                try:
                    datetime.strptime(rep['fecha'], "%Y-%m-%d")

                    turno_canonico, _ = normalizar_turno(rep.get('turno', ''))
                    if turno_canonico not in TURNOS_VALIDOS:
                        raise ValueError(f"Turno inválido ('{rep.get('turno')}'). Solo se permite Mañana, Tarde o Noche.")
                    rep['turno'] = turno_canonico
                    rep['jefe_turno'] = normalizar_jefe(rep.get('jefe_turno', ''))

                    detalles_insert = []
                    for d in rep.get('detalles', []):
                        a_id = get_id(areas_db, str(d.get('area', '')))
                        pr_id = get_id(productos_db, str(d.get('producto', '')))
                        m_id = get_id(metricas_db, str(d.get('metrica', '')))
                        val = float(d.get('valor', 0)) if pd.notna(d.get('valor')) else 0.0

                        if a_id and pr_id and m_id and val > 0:
                            sub_a = str(d.get('sub_area')).strip() if pd.notna(d.get('sub_area')) and str(d.get('sub_area')).strip() not in ["", "None"] else None
                            detalles_insert.append({
                                "area_id": a_id,
                                "producto_id": pr_id,
                                "metrica_id": m_id,
                                "sub_area": sub_a,
                                "valor": val
                            })
                        elif val > 0:
                            filas_descartadas += 1

                    if not detalles_insert:
                        raise ValueError("No tiene métricas válidas (> 0) para guardar.")

                    data_turno = {
                        "fecha": rep['fecha'],
                        "planta_id": p_id,
                        "turno": rep['turno'],
                        "jefe_turno": rep.get('jefe_turno') or None,
                        "novedades": rep.get('novedades') or None
                    }
                    res_t = supabase.table("reporte_turnos").insert(data_turno).execute()
                    turno_id = res_t.data[0]['id']

                    for d_ins in detalles_insert:
                        d_ins["reporte_id"] = turno_id

                    supabase.table("reporte_detalles").insert(detalles_insert).execute()
                    guardados += 1

                except Exception as e:
                    if turno_id:
                        try:
                            supabase.table("reporte_turnos").delete().eq("id", turno_id).execute()
                        except Exception:
                            pass
                    omitidos += 1
                    st.warning(f"⚠️ Omitido {rep.get('fecha')} ({rep.get('turno')}): {e}")

                barra.progress((pos + 1) / len(a_guardar))

            st.success(f"✅ Proceso finalizado: **{guardados}** reportes guardados, **{omitidos}** omitidos.")
            if filas_descartadas > 0:
                st.info(f"ℹ️ {filas_descartadas} filas fueron ignoradas por no coincidir con el catálogo maestro.")
            if guardados > 0:
                del st.session_state.wa_resultados

        if col_g2.button("🗑️ Limpiar vista previa", use_container_width=True):
            del st.session_state.wa_resultados
            st.rerun()

# ==========================================
# MÓDULO B: REPORTE SEMANAL Y OBJETIVOS (IA)
# ==========================================
def render_reporte_semanal():
    st.title("📊 Reporte Semanal y Objetivos de Gestión")

    c1, c2, c3 = st.columns(3)
    hoy = datetime.now().date()
    fecha_ini = c1.date_input("Desde", value=hoy - timedelta(days=7))
    fecha_fin = c2.date_input("Hasta", value=hoy)
    planta_filtro = c3.selectbox("Planta", ["Todas"] + nombres_plantas)

    query = supabase.table("vista_reportes_looker").select("*").gte("fecha", str(fecha_ini)).lte("fecha", str(fecha_fin))
    if planta_filtro != "Todas":
        query = query.eq("planta", planta_filtro)

    data = query.execute().data

    if not data:
        st.info("No hay reportes registrados en ese rango de fechas. Carga primero algunos reportes desde WhatsApp.")
        return

    df = pd.DataFrame(data)

    total_turnos = df['reporte_id'].nunique()
    total_cajas = df[df['metrica'] == 'Cajas']['valor'].sum()
    total_batch = df[(df['area'] == 'Masa') & (df['metrica'] == 'Batch')]['valor'].sum()
    total_merma_kg = df[df['area'] == 'Mermas y Polveo']['valor'].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Turnos Registrados", f"{total_turnos}")
    k2.metric("Batches Masa", f"{total_batch:,.0f}")
    k3.metric("Cajas Envasadas", f"{total_cajas:,.0f}")
    k4.metric("Total Mermas / Barrido (kg)", f"{total_merma_kg:,.1f} kg")

    st.divider()

    resumen_metricas = df.groupby(['planta', 'area', 'metrica', 'producto'], dropna=False)['valor'].sum().reset_index()
    novedades_unicas = df[['fecha', 'planta', 'turno', 'jefe_turno', 'novedades']].drop_duplicates()

    with st.expander("📋 Ver detalle consolidado del período"):
        st.dataframe(resumen_metricas, use_container_width=True)
        st.markdown("**Novedades de Turno:**")
        st.dataframe(novedades_unicas, use_container_width=True)

    if not client_ai:
        st.error("⚠️ Configura `GEMINI_API_KEY` en Secrets para generar el análisis semanal con IA.")
        return

    if st.button("🧠 Generar Reporte Semanal y Objetivos con IA", type="primary", use_container_width=True):
        with st.spinner("Analizando producción, mermas y novedades de planta..."):
            prompt_semanal = f"""
            Eres el Jefe de Gestión y Mejora Continua de una planta panadera industrial.
            Analiza los datos reales de producción del período {fecha_ini} al {fecha_fin} (Planta: {planta_filtro}) y redacta un Reporte Semanal Ejecutivo en español.

            DATOS CONSOLIDADOS (Planta | Area | Metrica | Producto | Total):
            {resumen_metricas.to_string(index=False)}

            NOVEDADES, CAUSAS DE MERMA Y FALLAS DE LOS JEFES DE TURNO:
            {novedades_unicas.to_string(index=False)}

            ESTRUCTURA OBLIGATORIA DEL INFORME:
            1. **Resumen Ejecutivo de Producción:** Balance de volumen (batches, horneado, cajas envasadas, consumo de insumos y dotación).
            2. **Análisis de Mermas y Desviaciones (Pareto):** Identifica los principales focos de pérdida en kg y cruza los números con las causas de merma y detenciones reportadas en piso.
            3. **Objetivos de Gestión para la Semana Siguiente (3 a 5 objetivos SMART):** Cada objetivo debe tener:
               - Meta cuantificable o verificable.
               - Acción concreta en planta.
               - Área / Rol responsable sugerido.
            4. **Mensaje Resumen para WhatsApp:** Un bloque breve (máximo 8 líneas) listo para copiar y enviar al grupo de jefatura/gerencia.

            Sé directo, técnico y orientado a acción en planta. No inventes datos que no estén en la tabla.
            """

            try:
                st.session_state.reporte_semanal_md = llamar_gemini_con_reintento(
                    prompt_semanal,
                    temperatura=0.2
                )
            except Exception as e:
                st.error(f"Error al generar el reporte con Gemini: {e}")

    if "reporte_semanal_md" in st.session_state:
        st.divider()
        st.markdown(st.session_state.reporte_semanal_md)
        st.download_button(
            label="⬇️ Descargar Reporte Semanal (.md)",
            data=st.session_state.reporte_semanal_md,
            file_name=f"reporte_semanal_{fecha_ini}_a_{fecha_fin}.md",
            mime="text/markdown",
            use_container_width=True
        )

# ==========================================
# ENRUTAMIENTO PRINCIPAL
# ==========================================
if modo_app == "⚡ Carga WhatsApp (Plantilla)":
    render_carga_whatsapp()
    st.stop()
elif modo_app == "📊 Reporte Semanal (IA)":
    render_reporte_semanal()
    st.stop()

# ==========================================
# MÓDULO C: FORMULARIO MANUAL (WIZARD ORIGINAL)
# ==========================================
def render_apertura():
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    set_val('fecha', c1.date_input("Fecha", value=get_val('fecha', datetime.now()), key="t_f"))
    set_val('planta', c2.selectbox("Planta", nombres_plantas, index=safe_index(nombres_plantas, get_val('planta', nombres_plantas[0] if nombres_plantas else "")), key="t_p"))
    set_val('letra_turno', c3.radio("Letra", ["A", "B", "C"], index=safe_index(["A", "B", "C"], get_val('letra_turno', 'A')), horizontal=True, key="t_l"))
    set_val('num_turno', c4.radio("Número", ["1", "2", "3"], index=safe_index(["1", "2", "3"], get_val('num_turno', '1')), horizontal=True, key="t_n"))

def render_masa():
    c_dot = st.columns([1, 3])
    set_val('dotacion_masa', c_dot[0].number_input("👥 N° Trabajadores (Masa)", min_value=0, step=1, value=get_val('dotacion_masa', 0), key="dot_masa"))
    st.divider()

    st.caption("Agrega todas las variedades de masa preparadas.")
    count = get_val('masa_count', 1)
    for i in range(count):
        st.markdown(f"**🥣 Masa {i+1}**")
        v_prod = st.selectbox(f"Prod Masa {i+1}", opciones_dinamicas, index=safe_index(opciones_dinamicas, get_val(f'masa_prod_{i}', opciones_dinamicas[0])), key=f"tmp_mp_{i}", label_visibility="collapsed")
        set_val(f'masa_prod_{i}', v_prod)
        if v_prod not in ["Seleccione un producto...", "Línea Detenida"]:
            c1, c2 = st.columns(2)
            set_val(f'masa_batch_{i}', c1.number_input("Batches", min_value=0, step=1, value=get_val(f'masa_batch_{i}', 0), key=f"tmp_mb_{i}"))
            set_val(f'masa_rep_{i}', c2.number_input("Reproceso (Batches)", min_value=0, step=1, value=get_val(f'masa_rep_{i}', 0), key=f"tmp_mr_{i}"))
        st.divider()
    if st.button("➕ Añadir otra masa"):
        set_val('masa_count', count + 1)
        st.rerun()

def render_camara():
    c_dot = st.columns([1, 3])
    set_val('dotacion_camara', c_dot[0].number_input("👥 N° Trabajadores (Cámara)", min_value=0, step=1, value=get_val('dotacion_camara', 0), key="dot_camara"))
    st.divider()

    st.caption("Control de productos ingresados a la cámara.")
    count = get_val('camara_count', 1)
    for i in range(count):
        st.markdown(f"**❄️ Producto {i+1}**")
        v_prod = st.selectbox(f"Prod Camara {i+1}", opciones_dinamicas, index=safe_index(opciones_dinamicas, get_val(f'cam_prod_{i}', opciones_dinamicas[0])), key=f"tmp_cp_{i}", label_visibility="collapsed")
        set_val(f'cam_prod_{i}', v_prod)
        if v_prod not in ["Seleccione un producto...", "Línea Detenida"]:
            c1, c2 = st.columns(2)
            set_val(f'cam_bat_{i}', c1.number_input("Batches Cámara", min_value=0, step=1, value=get_val(f'cam_bat_{i}', 0), key=f"tmp_cb_{i}"))
            set_val(f'cam_rep_{i}', c2.number_input("Reproceso", min_value=0, step=1, value=get_val(f'cam_rep_{i}', 0), key=f"tmp_cr_{i}"))
        st.divider()
    if st.button("➕ Añadir otro producto a la Cámara"):
        set_val('camara_count', count + 1)
        st.rerun()

def render_corte():
    st.caption("Estado de las líneas de corte. Selecciona los trabajadores de cada línea y sus productos.")
    for linea in ["C1", "C2", "C3", "Kornspitz", "Amasado"]:
        icono = "🟢" if "C" in linea else "🟡"

        col_tit, col_dot = st.columns([2, 1])
        col_tit.markdown(f"### {icono} Línea {linea}")
        set_val(f'dotacion_corte_{linea}', col_dot.number_input("👥 N° Trabajadores", min_value=0, step=1, value=get_val(f'dotacion_corte_{linea}', 0), key=f"dot_corte_{linea}"))

        count = get_val(f'corte_count_{linea}', 1)
        for i in range(count):
            titulo_select = f"Producto {i+1} en Línea {linea}" if i > 0 else f"Producto en Línea {linea}"
            v_prod = st.selectbox(titulo_select, opciones_dinamicas, index=safe_index(opciones_dinamicas, get_val(f'corte_prod_{linea}_{i}', opciones_dinamicas[0])), key=f"tmp_cop_{linea}_{i}")
            set_val(f'corte_prod_{linea}_{i}', v_prod)

            if v_prod not in ["Seleccione un producto...", "Línea Detenida"]:
                c1, c2, c3 = st.columns(3)
                set_val(f'corte_bat_{linea}_{i}', c1.number_input("Batches Cortados", min_value=0, step=1, value=get_val(f'corte_bat_{linea}_{i}', 0), key=f"tmp_cob_{linea}_{i}"))
                set_val(f'corte_car_{linea}_{i}', c2.number_input("Carros", min_value=0, step=1, value=get_val(f'corte_car_{linea}_{i}', 0), key=f"tmp_coc_{linea}_{i}"))
                set_val(f'corte_sem_{linea}_{i}', c3.number_input("Semillas (sacos 25kg)", min_value=0.0, step=0.5, value=get_val(f'corte_sem_{linea}_{i}', 0.0), key=f"tmp_cos_{linea}_{i}"))

        if st.button(f"➕ Añadir otro producto a {linea}", key=f"btn_add_{linea}"):
            set_val(f'corte_count_{linea}', count + 1)
            st.rerun()
        st.divider()

def render_horno():
    c_dot = st.columns([1, 3])
    set_val('dotacion_horno', c_dot[0].number_input("👥 N° Trabajadores (Horno)", min_value=0, step=1, value=get_val('dotacion_horno', 0), key="dot_horno"))
    st.divider()

    st.caption("Registro de horneado por producto.")
    count = get_val('horno_count', 1)
    for i in range(count):
        st.markdown(f"**🔥 Producto {i+1}**")
        v_prod = st.selectbox(f"Prod Horno {i+1}", opciones_dinamicas, index=safe_index(opciones_dinamicas, get_val(f'horno_prod_{i}', opciones_dinamicas[0])), key=f"tmp_hp_{i}", label_visibility="collapsed")
        set_val(f'horno_prod_{i}', v_prod)
        if v_prod not in ["Seleccione un producto...", "Línea Detenida"]:
            c1, c2, c3 = st.columns(3)
            set_val(f'horno_car_{i}', c1.number_input("Carros Horneados", min_value=0, step=1, value=get_val(f'horno_car_{i}', 0), key=f"tmp_hc_{i}"))
            set_val(f'horno_aba_{i}', c2.number_input("Abatidor (Carros)", min_value=0, step=1, value=get_val(f'horno_aba_{i}', 0), key=f"tmp_ha_{i}"))
            set_val(f'horno_cru_{i}', c3.number_input("Crudo (Carros)", min_value=0, step=1, value=get_val(f'horno_cru_{i}', 0), key=f"tmp_hcr_{i}"))
        st.divider()
    if st.button("➕ Añadir otro producto al Horno"):
        set_val('horno_count', count + 1)
        st.rerun()

def render_envasado():
    c_dot = st.columns([1, 3])
    set_val('dotacion_envasado', c_dot[0].number_input("👥 N° Trabajadores (Envasado)", min_value=0, step=1, value=get_val('dotacion_envasado', 0), key="dot_env"))
    st.divider()

    st.caption("Cierre y envasado.")
    count = get_val('envasado_count', 1)
    for i in range(count):
        st.markdown(f"**📦 Envasado {i+1}**")
        v_prod = st.selectbox(f"Prod Envasado {i+1}", opciones_dinamicas, index=safe_index(opciones_dinamicas, get_val(f'env_prod_{i}', opciones_dinamicas[0])), key=f"tmp_ep_{i}", label_visibility="collapsed")
        set_val(f'env_prod_{i}', v_prod)
        if v_prod not in ["Seleccione un producto...", "Línea Detenida"]:
            set_val(f'env_caj_{i}', st.number_input("Cajas", min_value=0, step=1, value=get_val(f'env_caj_{i}', 0), key=f"tmp_ec_{i}"))
        st.divider()
    if st.button("➕ Añadir otro producto a Envasado"):
        set_val('envasado_count', count + 1)
        st.rerun()

def render_mermas():
    st.caption("Registro final de mermas generales y harina de polveo.")
    count = get_val('mermas_count', 1)
    for i in range(count):
        st.markdown(f"**🗑️ Registro {i+1}**")
        v_prod = st.selectbox(f"Producto {i+1}", opciones_dinamicas, index=safe_index(opciones_dinamicas, get_val(f'merma_prod_{i}', opciones_dinamicas[0])), key=f"tmp_mermap_{i}", label_visibility="collapsed")
        set_val(f'merma_prod_{i}', v_prod)
        if v_prod not in ["Seleccione un producto...", "Línea Detenida"]:
            c1, c2, c3 = st.columns(3)
            set_val(f'merma_cruda_{i}', c1.number_input("Merma Cruda (kg)", min_value=0.0, step=0.5, value=get_val(f'merma_cruda_{i}', 0.0), key=f"tmp_mcr_{i}"))
            set_val(f'merma_horneada_{i}', c2.number_input("Merma Horneada (kg)", min_value=0.0, step=0.5, value=get_val(f'merma_horneada_{i}', 0.0), key=f"tmp_mho_{i}"))
            set_val(f'polveo_{i}', c3.number_input("Harina de Polveo/Barrido (kg)", min_value=0.0, step=0.5, value=get_val(f'polveo_{i}', 0.0), key=f"tmp_mpol_{i}"))
        st.divider()
    if st.button("➕ Añadir otro registro de mermas"):
        set_val('mermas_count', count + 1)
        st.rerun()

pasos_nombres = ["Apertura de Turno", "Masa", "Cámara", "Corte", "Horno", "Envasado", "Mermas y Polveo"]
paso_actual = get_val('paso_actual', 0)

st.title("Registro de Producción Integral")
st.progress(paso_actual / (len(pasos_nombres) - 1))
st.header(f"Paso {paso_actual + 1}: {pasos_nombres[paso_actual]}")
st.divider()

if paso_actual == 0: render_apertura()
elif paso_actual == 1: render_masa()
elif paso_actual == 2: render_camara()
elif paso_actual == 3: render_corte()
elif paso_actual == 4: render_horno()
elif paso_actual == 5: render_envasado()
elif paso_actual == 6: render_mermas()

st.divider()

col_izq, col_der = st.columns(2)

with col_izq:
    if paso_actual > 0:
        if st.button("⬅️ Atrás", use_container_width=True):
            set_val('paso_actual', paso_actual - 1)
            st.rerun()

with col_der:
    if paso_actual < len(pasos_nombres) - 1:
        if st.button("Siguiente ➡️", type="primary", use_container_width=True):
            set_val('paso_actual', paso_actual + 1)
            st.rerun()
    else:
        if st.button("💾 Guardar Reporte Completo", type="primary", use_container_width=True):
            planta_id = get_id(plantas_db, get_val('planta', ''))
            turno_final = f"{get_val('letra_turno', 'A')}{get_val('num_turno', '1')}"
            data_turno = {"fecha": str(get_val('fecha', datetime.now())), "planta_id": planta_id, "turno": turno_final}

            try:
                res_turno = supabase.table("reporte_turnos").insert(data_turno).execute()
                turno_id = res_turno.data[0]['id']
                detalles_a_insertar = []

                def agregar_detalle(area, prod, metrica, valor, sub_area=None):
                    if valor > 0 and prod not in ["Línea Detenida", "Seleccione un producto...", ""]:
                        detalles_a_insertar.append({
                            "reporte_id": turno_id, "area_id": get_id(areas_db, area),
                            "producto_id": get_id(productos_db, prod), "metrica_id": get_id(metricas_db, metrica),
                            "sub_area": sub_area, "valor": valor
                        })

                if get_val('dotacion_masa', 0) > 0: agregar_detalle("Masa", "General", "Operarios", get_val('dotacion_masa', 0))
                if get_val('dotacion_camara', 0) > 0: agregar_detalle("Cámara", "General", "Operarios", get_val('dotacion_camara', 0))
                for linea in ["C1", "C2", "C3", "Kornspitz", "Amasado"]:
                    if get_val(f'dotacion_corte_{linea}', 0) > 0:
                        agregar_detalle("Corte", "General", "Operarios", get_val(f'dotacion_corte_{linea}', 0), linea)
                if get_val('dotacion_horno', 0) > 0: agregar_detalle("Horno", "General", "Operarios", get_val('dotacion_horno', 0))
                if get_val('dotacion_envasado', 0) > 0: agregar_detalle("Envasado", "General", "Operarios", get_val('dotacion_envasado', 0))

                for i in range(get_val('masa_count', 1)):
                    p = get_val(f'masa_prod_{i}', '')
                    agregar_detalle("Masa", p, "Batch", get_val(f'masa_batch_{i}', 0))
                    agregar_detalle("Masa", p, "Reproceso", get_val(f'masa_rep_{i}', 0))

                for i in range(get_val('camara_count', 1)):
                    p = get_val(f'cam_prod_{i}', '')
                    agregar_detalle("Cámara", p, "Batch", get_val(f'cam_bat_{i}', 0))
                    agregar_detalle("Cámara", p, "Reproceso", get_val(f'cam_rep_{i}', 0))

                for linea in ["C1", "C2", "C3", "Kornspitz", "Amasado"]:
                    count_linea = get_val(f'corte_count_{linea}', 1)
                    for i in range(count_linea):
                        p = get_val(f'corte_prod_{linea}_{i}', '')
                        semilla_kg = get_val(f'corte_sem_{linea}_{i}', 0.0) * 25
                        agregar_detalle("Corte", p, "Batch", get_val(f'corte_bat_{linea}_{i}', 0), linea)
                        agregar_detalle("Corte", p, "Carros", get_val(f'corte_car_{linea}_{i}', 0), linea)
                        agregar_detalle("Corte", p, "Semilla", semilla_kg, linea)

                for i in range(get_val('horno_count', 1)):
                    p = get_val(f'horno_prod_{i}', '')
                    agregar_detalle("Horno", p, "Carros", get_val(f'horno_car_{i}', 0))
                    agregar_detalle("Horno", p, "Abatidor", get_val(f'horno_aba_{i}', 0))
                    agregar_detalle("Horno", p, "Crudo", get_val(f'horno_cru_{i}', 0))

                for i in range(get_val('envasado_count', 1)):
                    p = get_val(f'env_prod_{i}', '')
                    agregar_detalle("Envasado", p, "Cajas", get_val(f'env_caj_{i}', 0))

                for i in range(get_val('mermas_count', 1)):
                    p = get_val(f'merma_prod_{i}', '')
                    agregar_detalle("Mermas y Polveo", p, "Merma Cruda", get_val(f'merma_cruda_{i}', 0.0))
                    agregar_detalle("Mermas y Polveo", p, "Merma Horneada", get_val(f'merma_horneada_{i}', 0.0))
                    agregar_detalle("Mermas y Polveo", p, "Polveo", get_val(f'polveo_{i}', 0.0))

                if detalles_a_insertar:
                    supabase.table("reporte_detalles").insert(detalles_a_insertar).execute()

                st.success(f"✅ Reporte guardado exitosamente. Turno: {turno_final} (Folio interno: {turno_id})")
                st.balloons()

                st.session_state.form_data = {}
                set_val('paso_actual', 0)

            except Exception as e:
                st.error(f"Error al guardar. Si el turno ya existe, no se puede duplicar. Detalle técnico: {e}")
