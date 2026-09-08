import streamlit as st
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

# Inicialización de variables de sesión
if 'usuario_logeado' not in st.session_state:
    st.session_state.usuario_logeado = False
    st.session_state.rol = None
    st.session_state.nombre_usuario = None
if 'horno_items' not in st.session_state:
    st.session_state.horno_items = 1
if 'masa_items' not in st.session_state:
    st.session_state.masa_items = 1

# --- 2. SISTEMA DE LOGIN ---
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

# --- 3. FUNCIONES DE BASE DE DATOS ---
@st.cache_data(ttl=10)
def fetch_data(table):
    return supabase.table(table).select("*").order("id").execute().data

def get_id(db, nombre):
    return next((item['id'] for item in db if item['nombre'].lower() == nombre.lower()), None)

plantas_db = fetch_data("plantas")
productos_db = fetch_data("productos")
areas_db = fetch_data("areas")
metricas_db = fetch_data("metricas")
usuarios_db = fetch_data("usuarios")

nombres_plantas = [p['nombre'] for p in plantas_db] if plantas_db else []
nombres_productos = [p['nombre'] for p in productos_db] if productos_db else []

# Listas de opciones
opciones_producto = ["Línea Detenida"] + nombres_productos
opciones_dinamicas = ["Seleccione un producto..."] + nombres_productos

# --- 4. BARRA LATERAL Y MANTENEDORES ---
with st.sidebar:
    st.write(f"👤 **Usuario:** {st.session_state.nombre_usuario}")
    st.write(f"🛡️ **Rol:** {st.session_state.rol.title()}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logeado = False
        st.session_state.rol = None
        st.session_state.nombre_usuario = None
        st.session_state.horno_items = 1 
        st.session_state.masa_items = 1 
        st.rerun()
    
    st.divider()

    if st.session_state.rol == 'admin':
        st.subheader("🛠️ Administración")
        
        with st.expander("⚙️ Mantenedor Usuarios"):
            with st.form("crear_usuario"):
                nuevo_user = st.text_input("Nuevo Usuario")
                nueva_clave = st.text_input("Contraseña", type="password")
                nuevo_rol = st.selectbox("Rol", ["jefe de turno", "admin"])
                if st.form_submit_button("Crear Usuario"):
                    if nuevo_user and nueva_clave:
                        try:
                            supabase.table("usuarios").insert({"usuario": nuevo_user, "clave": nueva_clave, "rol": nuevo_rol}).execute()
                            fetch_data.clear()
                            st.success(f"Creado: {nuevo_user}")
                            st.rerun()
                        except Exception:
                            st.error("El usuario ya existe.")
                    else:
                        st.warning("Completa los campos.")

            st.write("**Usuarios Actuales:**")
            for u in usuarios_db:
                c1, c2 = st.columns([4, 1])
                c1.write(f"👤 {u['usuario']} ({u['rol'][:4]})")
                if u['usuario'] != 'admin':
                    if c2.button("❌", key=f"del_user_{u['id']}", help="Eliminar usuario"):
                        supabase.table("usuarios").delete().eq("id", u['id']).execute()
                        fetch_data.clear()
                        st.rerun()
                        
        with st.expander("🥖 Mantenedor Productos"):
            with st.form("crear_producto"):
                nuevo_prod = st.text_input("Nuevo Producto")
                if st.form_submit_button("Agregar Producto"):
                    if nuevo_prod:
                        try:
                            supabase.table("productos").insert({"nombre": nuevo_prod}).execute()
                            fetch_data.clear()
                            st.success(f"Agregado: {nuevo_prod}")
                            st.rerun()
                        except Exception:
                            st.error("Error al crear.")
                    else:
                        st.warning("Ingresa un nombre.")

            st.write("**Productos Actuales:**")
            for p in productos_db:
                cp1, cp2 = st.columns([4, 1])
                cp1.caption(f"🥖 {p['nombre']}")
                if cp2.button("❌", key=f"del_prod_{p['id']}", help="Eliminar producto"):
                    try:
                        supabase.table("productos").delete().eq("id", p['id']).execute()
                        fetch_data.clear()
                        st.rerun()
                    except Exception:
                        st.error("No se puede eliminar (tiene registros).")

# ==========================================
# 5. VISTA PRINCIPAL: REGISTRO DE PRODUCCIÓN
# ==========================================
st.title("Registro de Producción Integral")

st.header("1. Apertura de Turno")
col_f, col_p, col_t1, col_t2 = st.columns([2, 2, 1, 1])

with col_f: fecha = st.date_input("Fecha", datetime.now())
with col_p: planta = st.selectbox("Planta", nombres_plantas)

with col_t1: letra_turno = st.radio("Letra", ["A", "B", "C"], horizontal=True)
with col_t2: num_turno = st.radio("Número", ["1", "2", "3"], horizontal=True)
turno_final = f"{letra_turno}{num_turno}"

st.divider()

st.header("2. Detalle Operativo")
st.caption("Completa las etapas en el orden del flujo. Si una línea no opera, selecciona 'Línea Detenida'.")

# Pestañas en el nuevo orden lógico del proceso
tab_masa, tab_camara, tab_corte, tab_horno, tab_envasado = st.tabs(["Masa", "Cámara", "Corte", "Horno", "Envasado"])

# --- PESTAÑA MASA (Dinámica) ---
with tab_masa:
    st.subheader("Preparación de Masas")
    datos_masa = []
    
    for i in range(st.session_state.masa_items):
        st.markdown(f"**🥣 Masa {i+1}**")
        prod_masa = st.selectbox(f"Seleccionar Producto Masa {i+1}", opciones_dinamicas, key=f"prod_masa_{i}", label_visibility="collapsed")
        
        if prod_masa != "Seleccione un producto...":
            col_m1, col_m2, col_m3 = st.columns(3)
            batch_m = col_m1.number_input("Batches", min_value=0, step=1, key=f"batch_m_{i}")
            rep_m = col_m2.number_input("Reproceso (Batches)", min_value=0, step=1, key=f"rep_m_{i}")
            bar_m = col_m3.number_input("Barrido (kg)", min_value=0.0, step=0.5, key=f"bar_m_{i}")
            datos_masa.append({"producto": prod_masa, "batch": batch_m, "reproceso": rep_m, "barrido": bar_m})
        st.divider()
        
    if st.button("➕ Añadir otra masa"):
        st.session_state.masa_items += 1
        st.rerun()

# --- PESTAÑA CÁMARA ---
with tab_camara:
    st.subheader("Control de Cámara")
    prod_camara = st.selectbox("Producto Cámara", opciones_producto, key="prod_cam")
    if prod_camara != "Línea Detenida":
        col_cam1, col_cam2, col_cam3 = st.columns(3)
        bat_cam = col_cam1.number_input("Batches Cámara", min_value=0, step=1, key="bat_cam")
        rep_cam = col_cam2.number_input("Reproceso", min_value=0, step=1, key="rep_cam")
        mer_cam = col_cam3.number_input("Merma Reproceso (kg)", min_value=0.0, step=0.5, key="mer_cam")

# --- PESTAÑA CORTE ---
with tab_corte:
    datos_corte = {}
    st.subheader("Líneas Principales")
    for linea in ["C1", "C2", "C3"]:
        st.markdown(f"**🟢 Línea {linea}**")
        prod_linea = st.selectbox(f"Estado / Producto ({linea})", opciones_producto, key=f"prod_corte_{linea}")
        if prod_linea != "Línea Detenida":
            col_c1, col_c2, col_c3 = st.columns(3)
            car = col_c1.number_input(f"Carros ({linea})", min_value=0, step=1, key=f"car_{linea}")
            har = col_c2.number_input(f"Harina sacos/kg ({linea})", min_value=0.0, step=1.0, key=f"har_{linea}")
            sem = col_c3.number_input(f"Semillas sacos/kg ({linea})", min_value=0.0, step=1.0, key=f"sem_{linea}")
            datos_corte[linea] = {"producto": prod_linea, "carros": car, "harina": har, "semilla": sem}
        else:
            datos_corte[linea] = {"producto": prod_linea, "carros": 0, "harina": 0, "semilla": 0}
    
    st.divider()
    st.subheader("Líneas Especiales")
    for linea in ["Kornspitz", "Amasado"]:
        st.markdown(f"**🟡 Línea {linea}**")
        prod_linea = st.selectbox(f"Estado / Producto ({linea})", opciones_producto, key=f"prod_corte_{linea}")
        if prod_linea != "Línea Detenida":
            col_c1, col_c2, col_c3 = st.columns(3)
            car = col_c1.number_input(f"Carros ({linea})", min_value=0, step=1, key=f"car_{linea}")
            har = col_c2.number_input(f"Harina sacos/kg ({linea})", min_value=0.0, step=1.0, key=f"har_{linea}")
            sem = col_c3.number_input(f"Semillas sacos/kg ({linea})", min_value=0.0, step=1.0, key=f"sem_{linea}")
            datos_corte[linea] = {"producto": prod_linea, "carros": car, "harina": har, "semilla": sem}
        else:
            datos_corte[linea] = {"producto": prod_linea, "carros": 0, "harina": 0, "semilla": 0}

# --- PESTAÑA HORNO (Dinámica) ---
with tab_horno:
    st.subheader("Registro de Horneado")
    datos_horno = []
    
    for i in range(st.session_state.horno_items):
        st.markdown(f"**🔥 Producto {i+1}**")
        prod_horno = st.selectbox(f"Seleccionar Producto Horno {i+1}", opciones_dinamicas, key=f"prod_horno_{i}", label_visibility="collapsed")
        
        if prod_horno != "Seleccione un producto...":
            col_h1, col_h2, col_h3 = st.columns(3)
            car_h = col_h1.number_input("Carros Horneados", min_value=0, step=1, key=f"car_h_{i}")
            aba_h = col_h2.number_input("Abatidor (Carros)", min_value=0, step=1, key=f"aba_h_{i}")
            cru_h = col_h3.number_input("Crudo (Carros)", min_value=0, step=1, key=f"cru_h_{i}")
            datos_horno.append({"producto": prod_horno, "carros": car_h, "abatidor": aba_h, "crudo": cru_h})
        st.divider()
        
    if st.button("➕ Añadir otro producto al Horno"):
        st.session_state.horno_items += 1
        st.rerun()

# --- PESTAÑA ENVASADO ---
with tab_envasado:
    st.subheader("Cierre y Envasado")
    prod_envasado = st.selectbox("Producto Envasado", opciones_producto, key="prod_env")
    if prod_envasado != "Línea Detenida":
        col_e1, col_e2 = st.columns(2)
        caj_env = col_e1.number_input("Cajas", min_value=0, step=1, key="caj_env")
        mer_env = col_e2.number_input("Merma Envasado (kg)", min_value=0.0, step=0.5, key="mer_env")

st.divider()

# --- GUARDADO ---
if st.button("💾 Guardar Reporte Completo del Turno", type="primary", use_container_width=True):
    planta_id = get_id(plantas_db, planta)
    data_turno = {"fecha": str(fecha), "planta_id": planta_id, "turno": turno_final}
    
    try:
        res_turno = supabase.table("reporte_turnos").insert(data_turno).execute()
        turno_id = res_turno.data[0]['id']
        detalles_a_insertar = []
        
        def agregar_detalle(area, prod, metrica, valor, sub_area=None):
            if valor > 0 and prod not in ["Línea Detenida", "Seleccione un producto..."]:
                detalles_a_insertar.append({
                    "reporte_id": turno_id,
                    "area_id": get_id(areas_db, area),
                    "producto_id": get_id(productos_db, prod),
                    "metrica_id": get_id(metricas_db, metrica),
                    "sub_area": sub_area,
                    "valor": valor
                })

        # Procesar Masa dinámica
        for d_masa in datos_masa:
            agregar_detalle("Masa", d_masa["producto"], "Batch", d_masa["batch"])
            agregar_detalle("Masa", d_masa["producto"], "Reproceso", d_masa["reproceso"])
            agregar_detalle("Masa", d_masa["producto"], "Barrido", d_masa["barrido"])
            
        # Procesar Cámara
        if prod_camara != "Línea Detenida":
            agregar_detalle("Cámara", prod_camara, "Batch", bat_cam)
            agregar_detalle("Cámara", prod_camara, "Reproceso", rep_cam)
            agregar_detalle("Cámara", prod_camara, "Merma", mer_cam)
        
        # Procesar Corte
        for linea, datos in datos_corte.items():
            if datos["producto"] != "Línea Detenida":
                agregar_detalle("Corte", datos["producto"], "Carros", datos["carros"], linea)
                agregar_detalle("Corte", datos["producto"], "Harina", datos["harina"], linea)
                agregar_detalle("Corte", datos["producto"], "Semilla", datos["semilla"], linea)
        
        # Procesar Horno dinámico
        for d_horno in datos_horno:
            agregar_detalle("Horno", d_horno["producto"], "Carros", d_horno["carros"])
            agregar_detalle("Horno", d_horno["producto"], "Abatidor", d_horno["abatidor"])
            agregar_detalle("Horno", d_horno["producto"], "Crudo", d_horno["crudo"])
            
        # Procesar Envasado
        if prod_envasado != "Línea Detenida":
            agregar_detalle("Envasado", prod_envasado, "Cajas", caj_env)
            agregar_detalle("Envasado", prod_envasado, "Merma", mer_env)

        if detalles_a_insertar:
            supabase.table("reporte_detalles").insert(detalles_a_insertar).execute()
        
        st.session_state.horno_items = 1
        st.session_state.masa_items = 1
        st.success(f"✅ Reporte guardado con éxito. Turno: {turno_final} (Folio interno: {turno_id})")
        st.balloons()
    except Exception as e:
        st.error(f"Error al guardar: {e}")
