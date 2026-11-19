import streamlit as st
import pandas as pd
import re
import json
import time
from datetime import datetime, timedelta
from supabase import create_client, Client
from google import genai
from google.genai import types

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Reporte Productivo", page_icon="🍞", layout="wide")

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

# --- 4. BARRA LATERAL (NAVEGACIÓN Y ADMINISTRACIÓN) ---
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
        ["📥 Carga WhatsApp (IA)", "📊 Reporte Semanal (IA)", "📝 Formulario Manual"]
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
# MÓDULO A: CARGA WHATSAPP CON IA
# ==========================================
def extraer_bloques_whatsapp(texto_completo):
    """Separa un chat exportado (.txt) de iPhone o Android y filtra solo los reportes de turno."""
    patron_mensaje = r'(?=\[?\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2})'
    mensajes = re.split(patron_mensaje, texto_completo)
    reportes = [m.strip() for m in mensajes if "REPORTE DE TURNO" in m.upper()]
    if not reportes and "REPORTE DE TURNO" in texto_completo.upper():
        reportes = [texto_completo.strip()]
    return reportes

def parsear_reporte_con_ia(texto_reporte, areas, productos, metricas):
    """Convierte el texto crudo de WhatsApp al esquema relacional exacto de Supabase."""
    prompt = f"""
    Eres un analista de datos de producción panadera industrial. Convierte este reporte de turno de WhatsApp en un JSON estructurado.

    REGLAS ESTRICTAS DE CATÁLOGO (usa ÚNICAMENTE los nombres exactos de estas listas):
    - Áreas válidas: {areas}
    - Productos válidos: {productos}
    - Métricas válidas: {metricas}
    - Sub-áreas (líneas/máquinas): "C1", "C2", "C3", "Kornspitz", "Amasado" o null si no aplica.

    REGLAS DE MAPEO E INTERPRETACIÓN:
    1. Ignora errores de ortografía ("resivi", "bach", "kl", "reproce", "polvoreo").
    2. NO incluyas filas con valor 0, vacías o totales redundantes si ya están desglosados por producto/línea.
    3. Fecha obligatoriamente en formato YYYY-MM-DD (si el año viene como /26, corresponde a 2026).
    4. Estandariza el turno a "Día", "Tarde" o "Noche" (o el código de turno si aparece explícitamente, ej. A1, B2).
    5. Mapeo de secciones del reporte:
       - MASAS -> Área "Masa", Métricas "Batch" o "Reproceso". Si un reproceso no especifica producto, usa producto "General".
       - CÁMARA -> Área "Cámara", Métricas "Batch" o "Reproceso".
       - CORTE -> Área "Corte", sub_area ("C1", "C2", "C3"), Métricas "Batch", "Reproceso" o "Carros" (usa producto "General" si el corte no indica el producto).
       - HORNO -> Área "Horno", Métricas "Carros" (horneados), "Abatidor", "Crudo" (por hornear). Producto "General" si no detalla.
       - ENVASADO -> Área "Envasado", Métrica "Cajas", con su producto exacto ("Rustica", "Toscano", "Integral", "Rustica Coctel", etc.).
       - MERMA PAN COCIDO -> Área "Mermas y Polveo", producto "General", usando las métricas específicas: "Merma Deforme", "Merma Sin Greña", "Merma Crudo", "Merma Sobre Cocción", "Merma Pan a Piso", "Merma Manchado".
       - MERMA DE MASA Y OTROS -> Área "Mermas y Polveo", producto "General", usando "Merma Cruda" (para merma de masa), "Reproceso" y "Barrido".
       - INSUMOS -> Área "Insumos", producto "General", usando "Harina" (sacos), "Polveo" (harina polvoreo), "Semilla", "Semilla Recuperada", "Harina Recuperada".
       - DOTACIÓN (ej. "Se trabajó con 25 personas") -> Área "Masa", producto "General", métrica "Operarios".
    6. Si algún texto en un campo numérico aporta contexto (ej. "Integral: proteina" o "ultra congelado"), agrégalo al campo "novedades".

    Devuelve SOLO un JSON válido con esta estructura exacta:
    {{
      "fecha": "YYYY-MM-DD",
      "turno": "string",
      "jefe_turno": "string",
      "novedades": "string",
      "detalles": [
        {{"area": "string", "producto": "string", "metrica": "string", "sub_area": null, "valor": 0.0}}
      ]
    }}

    REPORTE A PROCESAR:
    {texto_reporte}
    """

    response = client_ai.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0
        )
    )
    return json.loads(response.text)

def render_carga_whatsapp():
    st.title("📥 Carga Automática desde WhatsApp (IA)")

    if not client_ai:
        st.error("⚠️ Falta configurar `GEMINI_API_KEY` en los Secrets de Streamlit.")
        return

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
        st.info(f"🔎 Se detectaron **{len(bloques)}** reportes de turno en el texto.")

        if len(bloques) > 0:
            col_lim1, col_lim2 = st.columns([1, 2])
            cantidad_proc = col_lim1.number_input(
                "¿Cuántos reportes procesar (desde los más recientes)?",
                min_value=1,
                max_value=len(bloques),
                value=min(len(bloques), 20),
                step=1
            )
            bloques_a_procesar = bloques[-cantidad_proc:]

            if st.button("🤖 Extraer Datos con IA", type="primary"):
                resultados = []
                barra = st.progress(0)
                estado = st.empty()

                for idx, bloque in enumerate(bloques_a_procesar):
                    estado.text(f"Procesando reporte {idx + 1} de {len(bloques_a_procesar)}...")
                    try:
                        data_json = parsear_reporte_con_ia(bloque, nombres_areas, nombres_productos, nombres_metricas)
                        data_json["incluir"] = True
                        resultados.append(data_json)
                        if len(bloques_a_procesar) > 5:
                            time.sleep(0.5)
                    except Exception as e:
                        st.error(f"Error en reporte #{idx + 1}: {e}")
                    barra.progress((idx + 1) / len(bloques_a_procesar))

                estado.empty()
                st.session_state.wa_resultados = resultados
                st.session_state.wa_planta = planta_sel

    if "wa_resultados" in st.session_state and st.session_state.wa_resultados:
        st.divider()
        st.subheader(f"🔍 Revisión previa ({len(st.session_state.wa_resultados)} reportes) — Planta: {st.session_state.wa_planta}")
        st.caption("Puedes corregir cualquier dato directamente en las tablas o desmarcar reportes antes de guardar.")

        for idx, rep in enumerate(st.session_state.wa_resultados):
            titulo_exp = f"📅 {rep.get('fecha', 'Sin fecha')} | Turno: {rep.get('turno', '-')} | Jefe: {rep.get('jefe_turno', '-')}"
            with st.expander(titulo_exp, expanded=(len(st.session_state.wa_resultados) <= 3)):
                rep["incluir"] = st.checkbox("Guardar este reporte", value=rep.get("incluir", True), key=f"wa_inc_{idx}")
                c1, c2, c3 = st.columns(3)
                rep['fecha'] = c1.text_input("Fecha (YYYY-MM-DD)", rep.get('fecha', ''), key=f"wa_f_{idx}")
                rep['turno'] = c2.text_input("Turno", rep.get('turno', ''), key=f"wa_t_{idx}")
                rep['jefe_turno'] = c3.text_input("Jefe de Turno", rep.get('jefe_turno', ''), key=f"wa_j_{idx}")
                rep['novedades'] = st.text_area("Novedades", rep.get('novedades', ''), key=f"wa_n_{idx}")

                df_det = pd.DataFrame(rep.get('detalles', []))
                if not df_det.empty:
                    df_editado = st.data_editor(
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
                        key=f"wa_df_{idx}"
                    )
                    rep['detalles'] = df_editado.to_dict(orient="records")

        col_g1, col_g2 = st.columns([3, 1])
        if col_g1.button("💾 Confirmar y Guardar en Supabase", type="primary", use_container_width=True):
            p_id = get_id(plantas_db, st.session_state.wa_planta)
            guardados, omitidos, filas_descartadas = 0, 0, 0

            with st.spinner("Guardando reportes en Supabase..."):
                for rep in st.session_state.wa_resultados:
                    if not rep.get("incluir", True):
                        continue
                    try:
                        data_turno = {
                            "fecha": rep['fecha'],
                            "planta_id": p_id,
                            "turno": rep['turno'],
                            "jefe_turno": rep.get('jefe_turno'),
                            "novedades": rep.get('novedades')
                        }
                        res_t = supabase.table("reporte_turnos").insert(data_turno).execute()
                        turno_id = res_t.data[0]['id']

                        detalles_insert = []
                        for d in rep.get('detalles', []):
                            a_id = get_id(areas_db, str(d.get('area', '')))
                            pr_id = get_id(productos_db, str(d.get('producto', '')))
                            m_id = get_id(metricas_db, str(d.get('metrica', '')))
                            val = float(d.get('valor', 0)) if pd.notna(d.get('valor')) else 0.0

                            if a_id and pr_id and m_id and val > 0:
                                sub_a = str(d.get('sub_area')).strip() if pd.notna(d.get('sub_area')) and str(d.get('sub_area')).strip() != "" else None
                                detalles_insert.append({
                                    "reporte_id": turno_id,
                                    "area_id": a_id,
                                    "producto_id": pr_id,
                                    "metrica_id": m_id,
                                    "sub_area": sub_a,
                                    "valor": val
                                })
                            elif val > 0:
                                filas_descartadas += 1

                        if detalles_insert:
                            supabase.table("reporte_detalles").insert(detalles_insert).execute()
                        guardados += 1
                    except Exception as e:
                        omitidos += 1
                        st.warning(f"⚠️ Turno {rep.get('fecha')} ({rep.get('turno')}) omitido (posible duplicado): {e}")

            st.success(f"✅ Listo: **{guardados}** reportes guardados, **{omitidos}** omitidos.")
            if filas_descartadas > 0:
                st.warning(f"ℹ️ Se omitieron {filas_descartadas} filas de detalle porque algún nombre no coincidió con las tablas maestras.")
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

    # KPIs rápidos
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

    # Resumen agrupado para visualizar y alimentar a la IA
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

            DATOS CONSOLIDADOS (Area | Metrica | Producto | Total):
            {resumen_metricas.to_string(index=False)}

            NOVEDADES DE LOS JEFES DE TURNO:
            {novedades_unicas.to_string(index=False)}

            ESTRUCTURA OBLIGATORIA DEL INFORME:
            1. **Resumen Ejecutivo de Producción:** Balance de volumen (batches, horneado, cajas envasadas, consumo de insumos y dotación).
            2. **Análisis de Mermas y Desviaciones (Pareto):** Identifica los principales focos de pérdida en kg y cruza los números con las novedades reportadas en piso (ej. problemas de pH, bandejas pegadas, reprocesos).
            3. **Objetivos de Gestión para la Semana Siguiente (3 a 5 objetivos SMART):** Cada objetivo debe tener:
               - Meta cuantificable o verificable.
               - Acción concreta en planta.
               - Área / Rol responsable sugerido.
            4. **Mensaje Resumen para WhatsApp:** Un bloque breve (máximo 8 líneas) listo para copiar y enviar al grupo de jefatura/gerencia.

            Sé directo, técnico y orientado a acción en planta. No inventes datos que no estén en la tabla.
            """

            try:
                resp = client_ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt_semanal,
                    config=types.GenerateContentConfig(temperature=0.2)
                )
                st.session_state.reporte_semanal_md = resp.text
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
if modo_app == "📥 Carga WhatsApp (IA)":
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
        if v
