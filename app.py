import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Reporte Productivo", page_icon="🍞", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("⚠️ Error de conexión a Supabase.")
    st.stop()

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
    if not isinstance(nombre, str): return None
    return next((item['id'] for item in db if item['nombre'].lower() == nombre.lower()), None)

plantas_db = fetch_data("plantas")
productos_db = fetch_data("productos")
areas_db = fetch_data("areas")
metricas_db = fetch_data("metricas")
usuarios_db = fetch_data("usuarios")

nombres_plantas = [p['nombre'] for p in plantas_db] if plantas_db else []
nombres_productos = [p['nombre'] for p in productos_db] if productos_db else []

opciones_dinamicas = ["Seleccione un producto...", "Línea Detenida"] + nombres_productos

# --- 4. BARRA LATERAL (ADMINISTRACIÓN Y CARGA) ---
with st.sidebar:
    st.write(f"👤 **Usuario:** {st.session_state.nombre_usuario}")
    st.write(f"🛡️ **Rol:** {st.session_state.rol.title()}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logeado = False
        st.session_state.rol = None
        st.session_state.nombre_usuario = None
        st.session_state.form_data = {} 
        st.rerun()
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
                    fetch_data.clear(); st.rerun()
            for u in usuarios_db:
                c1, c2 = st.columns([4, 1])
                c1.write(f"👤 {u['usuario']}")
                if u['usuario'] != 'admin' and c2.button("❌", key=f"del_u_{u['id']}"):
                    supabase.table("usuarios").delete().eq("id", u['id']).execute()
                    fetch_data.clear(); st.rerun()
                        
        with st.expander("🥖 Mantenedor Productos"):
            with st.form("crear_producto"):
                nuevo_prod = st.text_input("Nuevo Producto")
                if st.form_submit_button("Agregar") and nuevo_prod:
                    try:
                        supabase.table("productos").insert({"nombre": nuevo_prod}).execute()
                        fetch_data.clear(); st.rerun()
                    except Exception as e:
                        st.error("⚠️ Error: El producto ya existe o no se pudo guardar.")
                        
            for p in productos_db:
                cp1, cp2 = st.columns([4, 1])
                cp1.caption(f"🥖 {p['nombre']}")
                if cp2.button("❌", key=f"del_p_{p['id']}"):
                    supabase.table("productos").delete().eq("id", p['id']).execute()
                    fetch_data.clear(); st.rerun()
                    
        with st.expander("⬆️ Carga Masiva (Excel)"):
            st.caption("Plantilla requerida con columnas: Fecha | Planta | Turno | Area | Maquina | Producto | Metrica | Valor")
            archivo_subido = st.file_uploader("Sube historial en Excel", type=["xlsx", "xls"])
            
            if archivo_subido is not None:
                if st.button("Procesar y Cargar Data", use_container_width=True):
                    try:
                        df = pd.read_excel(archivo_subido)
                        df.columns = df.columns.str.strip().str.title() 
                        errores = 0
                        
                        turnos_unicos = df[['Fecha', 'Planta', 'Turno']].drop_duplicates()
                        
                        with st.spinner('Cargando datos a Supabase...'):
                            for index, fila_turno in turnos_unicos.iterrows():
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
                                            
                                            detalles_df = df[(df['Fecha'] == fila_turno['Fecha']) & 
                                                             (df['Turno'] == fila_turno['Turno']) & 
                                                             (df['Planta'] == fila_turno['Planta'])]
                                            
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
                                    except Exception as e:
                                        errores += 1
                        
                        if errores > 0:
                            st.warning(f"⚠️ Se omitieron {errores} turnos (probablemente ya existían).")
                        else:
                            st.success("✅ Carga masiva completada con éxito.")
                            
                    except Exception as e:
                        st.error(f"❌ Error leyendo el archivo. Detalle: {e}")

# ==========================================
# 5. FUNCIONES DE RENDERIZADO POR PASO
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
        set_val(f'dotacion_corte_{linea}', col_dot.number_input(f"👥 N° Trabajadores", min_value=0, step=1, value=get_val(f'dotacion_corte_{linea}', 0), key=f"dot_corte_{linea}"))
        
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

# ==========================================
# 6. MOTOR DEL WIZARD (FLUJO PASO A PASO)
# ==========================================
pasos_nombres = ["Apertura de Turno", "Masa", "Cámara", "Corte", "Horno", "Envasado", "Mermas y Polveo"]
paso_actual = get_val('paso_actual', 0)

st.title("Registro de Producción Integral")
st.progress(paso_actual / (len(pasos_nombres) - 1))
st.header(f"Paso {paso_actual + 1}: {pasos_nombres[paso_actual]}")
st.divider()

# Mostrar solo la etapa correspondiente
if paso_actual == 0: render_apertura()
elif paso_actual == 1: render_masa()
elif paso_actual == 2: render_camara()
elif paso_actual == 3: render_corte()
elif paso_actual == 4: render_horno()
elif paso_actual == 5: render_envasado()
elif paso_actual == 6: render_mermas()

st.divider()

# Botones de navegación
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
        # BOTÓN FINAL DE GUARDADO 
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

                # GUARDAR DOTACIONES
                if get_val('dotacion_masa', 0) > 0: agregar_detalle("Masa", "General", "Operarios", get_val('dotacion_masa', 0))
                if get_val('dotacion_camara', 0) > 0: agregar_detalle("Cámara", "General", "Operarios", get_val('dotacion_camara', 0))
                for linea in ["C1", "C2", "C3", "Kornspitz", "Amasado"]:
                    if get_val(f'dotacion_corte_{linea}', 0) > 0: 
                        agregar_detalle("Corte", "General", "Operarios", get_val(f'dotacion_corte_{linea}', 0), linea)
                if get_val('dotacion_horno', 0) > 0: agregar_detalle("Horno", "General", "Operarios", get_val('dotacion_horno', 0))
                if get_val('dotacion_envasado', 0) > 0: agregar_detalle("Envasado", "General", "Operarios", get_val('dotacion_envasado', 0))

                # Extraer Masa
                for i in range(get_val('masa_count', 1)):
                    p = get_val(f'masa_prod_{i}', '')
                    agregar_detalle("Masa", p, "Batch", get_val(f'masa_batch_{i}', 0))
                    agregar_detalle("Masa", p, "Reproceso", get_val(f'masa_rep_{i}', 0))
                
                # Extraer Cámara
                for i in range(get_val('camara_count', 1)):
                    p = get_val(f'cam_prod_{i}', '')
                    agregar_detalle("Cámara", p, "Batch", get_val(f'cam_bat_{i}', 0))
                    agregar_detalle("Cámara", p, "Reproceso", get_val(f'cam_rep_{i}', 0))
                    
                # Extraer Corte
                for linea in ["C1", "C2", "C3", "Kornspitz", "Amasado"]:
                    count_linea = get_val(f'corte_count_{linea}', 1)
                    for i in range(count_linea):
                        p = get_val(f'corte_prod_{linea}_{i}', '')
                        semilla_kg = get_val(f'corte_sem_{linea}_{i}', 0.0) * 25
                        agregar_detalle("Corte", p, "Batch", get_val(f'corte_bat_{linea}_{i}', 0), linea)
                        agregar_detalle("Corte", p, "Carros", get_val(f'corte_car_{linea}_{i}', 0), linea)
                        agregar_detalle("Corte", p, "Semilla", semilla_kg, linea)
                    
                # Extraer Horno
                for i in range(get_val('horno_count', 1)):
                    p = get_val(f'horno_prod_{i}', '')
                    agregar_detalle("Horno", p, "Carros", get_val(f'horno_car_{i}', 0))
                    agregar_detalle("Horno", p, "Abatidor", get_val(f'horno_aba_{i}', 0))
                    agregar_detalle("Horno", p, "Crudo", get_val(f'horno_cru_{i}', 0))
                    
                # Extraer Envasado
                for i in range(get_val('envasado_count', 1)):
                    p = get_val(f'env_prod_{i}', '')
                    agregar_detalle("Envasado", p, "Cajas", get_val(f'env_caj_{i}', 0))

                # Extraer Mermas y Polveo
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
