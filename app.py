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

# Inicializar variables de sesión para el login
if 'usuario_logeado' not in st.session_state:
    st.session_state.usuario_logeado = False
    st.session_state.rol = None
    st.session_state.nombre_usuario = None

# --- 2. SISTEMA DE LOGIN ---
if not st.session_state.usuario_logeado:
    st.title("🔐 Acceso al Sistema")
    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")
        
        if submit:
            # Buscar usuario en la BD
            res = supabase.table("usuarios").select("*").eq("usuario", usuario).eq("clave", clave).execute()
            
            if len(res.data) > 0:
                user_data = res.data[0]
                st.session_state.usuario_logeado = True
                st.session_state.rol = user_data['rol']
                st.session_state.nombre_usuario = user_data['usuario']
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.stop() # Detiene la ejecución del resto del código si no hay login

# --- 3. BARRA LATERAL (CERRAR SESIÓN) ---
with st.sidebar:
    st.write(f"👤 **Usuario:** {st.session_state.nombre_usuario}")
    st.write(f"🛡️ **Rol:** {st.session_state.rol.capitalize()}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logeado = False
        st.session_state.rol = None
        st.session_state.nombre_usuario = None
        st.rerun()

# --- 4. FUNCIONES DE BASE DE DATOS ---
@st.cache_data(ttl=60)
def fetch_data(table):
    return supabase.table(table).select("*").execute().data

def get_id(db, nombre):
    return next((item['id'] for item in db if item['nombre'].lower() == nombre.lower()), None)

# --- 5. VISTAS SEGÚN ROL ---
# Si el usuario es administrador, mostramos pestañas principales para separar la operación del mantenedor
if st.session_state.rol == 'admin':
    menu_principal = st.tabs(["🍞 Registro de Producción", "⚙️ Mantenedor de Usuarios"])
    vista_operacion = menu_principal[0]
    vista_mantenedor = menu_principal[1]
else:
    # Si es operador, solo ve la operación
    vista_operacion = st.container()

# ==========================================
# VISTA: REGISTRO DE PRODUCCIÓN
# ==========================================
with vista_operacion:
    st.title("Registro de Producción")
    
    plantas_db = fetch_data("plantas")
    productos_db = fetch_data("productos")
    areas_db = fetch_data("areas")
    metricas_db = fetch_data("metricas")

    nombres_plantas = [p['nombre'] for p in plantas_db] if plantas_db else []
    nombres_productos = [p['nombre'] for p in productos_db] if productos_db else []

    if not nombres_plantas or not nombres_productos:
        st.warning("No se encontraron plantas o productos en la base de datos.")
        st.stop()

    st.header("1. Apertura de Turno")
    col1, col2, col3 = st.columns(3)
    with col1: fecha = st.date_input("Fecha", datetime.now())
    with col2: planta = st.selectbox("Planta", nombres_plantas)
    with col3: turno = st.selectbox("Turno", ["Mañana", "Tarde", "Noche"])

    st.divider()

    st.header("2. Detalle Operativo")
    tab_masa, tab_corte, tab_horno, tab_camara, tab_envasado = st.tabs([
        "Masa", "Corte", "Horno", "Cámara", "Envasado"
    ])

    with tab_masa:
        prod_masa = st.selectbox("Producto Masa", nombres_productos, key="prod_masa")
        col_m1, col_m2, col_m3 = st.columns(3)
        batch_m = col_m1.number_input("Batches", min_value=0, step=1, key="batch_m")
        rep_m = col_m2.number_input("Reproceso (Batches)", min_value=0, step=1, key="rep_m")
        bar_m = col_m3.number_input("Barrido (kg)", min_value=0.0, step=0.5, key="bar_m")

    with tab_corte:
        linea_corte = st.selectbox("Línea", ["C1", "C2", "C3"])
        prod_corte = st.selectbox("Producto Corte", nombres_productos, key="prod_corte")
        col_c1, col_c2, col_c3 = st.columns(3)
        car_c = col_c1.number_input("Carros", min_value=0, step=1, key="car_c")
        har_c = col_c2.number_input("Harina (sacos/kg)", min_value=0.0, step=1.0, key="har_c")
        sem_c = col_c3.number_input("Semillas (sacos/kg)", min_value=0.0, step=1.0, key="sem_c")

    with tab_horno:
        prod_horno = st.selectbox("Producto Horno", nombres_productos, key="prod_horno")
        col_h1, col_h2, col_h3 = st.columns(3)
        car_h = col_h1.number_input("Carros Horneados", min_value=0, step=1, key="car_h")
        aba_h = col_h2.number_input("Abatidor (Carros)", min_value=0, step=1, key="aba_h")
        cru_h = col_h3.number_input("Crudo (Carros)", min_value=0, step=1, key="cru_h")

    with tab_camara:
        prod_camara = st.selectbox("Producto Cámara", nombres_productos, key="prod_cam")
        col_cam1, col_cam2, col_cam3 = st.columns(3)
        bat_cam = col_cam1.number_input("Batches Cámara", min_value=0, step=1, key="bat_cam")
        rep_cam = col_cam2.number_input("Reproceso", min_value=0, step=1, key="rep_cam")
        mer_cam = col_cam3.number_input("Merma Reproceso (kg)", min_value=0.0, step=0.5, key="mer_cam")

    with tab_envasado:
        prod_envasado = st.selectbox("Producto Envasado", nombres_productos, key="prod_env")
        col_e1, col_e2 = st.columns(2)
        caj_env = col_e1.number_input("Cajas", min_value=0, step=1, key="caj_env")
        mer_env = col_e2.number_input("Merma Envasado (kg)", min_value=0.0, step=0.5, key="mer_env")

    st.divider()

    if st.button("💾 Guardar Reporte de Turno", type="primary", use_container_width=True):
        planta_id = get_id(plantas_db, planta)
        data_turno = {"fecha": str(fecha), "planta_id": planta_id, "turno": turno}
        
        try:
            res_turno = supabase.table("reporte_turnos").insert(data_turno).execute()
            turno_id = res_turno.data[0]['id']
            detalles_a_insertar = []
            
            def agregar_detalle(area, prod, metrica, valor, sub_area=None):
                if valor > 0:
                    detalles_a_insertar.append({
                        "reporte_id": turno_id,
                        "area_id": get_id(areas_db, area),
                        "producto_id": get_id(productos_db, prod),
                        "metrica_id": get_id(metricas_db, metrica),
                        "sub_area": sub_area,
                        "valor": valor
                    })

            agregar_detalle("Masa", prod_masa, "Batch", batch_m)
            agregar_detalle("Masa", prod_masa, "Reproceso", rep_m)
            agregar_detalle("Masa", prod_masa, "Barrido", bar_m)
            agregar_detalle("Corte", prod_corte, "Carros", car_c, linea_corte)
            agregar_detalle("Corte", prod_corte, "Harina", har_c, linea_corte)
            agregar_detalle("Corte", prod_corte, "Semilla", sem_c, linea_corte)
            agregar_detalle("Horno", prod_horno, "Carros", car_h)
            agregar_detalle("Horno", prod_horno, "Abatidor", aba_h)
            agregar_detalle("Horno", prod_horno, "Crudo", cru_h)
            agregar_detalle("Cámara", prod_camara, "Batch", bat_cam)
            agregar_detalle("Cámara", prod_camara, "Reproceso", rep_cam)
            agregar_detalle("Cámara", prod_camara, "Merma", mer_cam)
            agregar_detalle("Envasado", prod_envasado, "Cajas", caj_env)
            agregar_detalle("Envasado", prod_envasado, "Merma", mer_env)

            if detalles_a_insertar:
                supabase.table("reporte_detalles").insert(detalles_a_insertar).execute()
            
            st.success(f"✅ Reporte guardado. ID: {turno_id}")
            st.balloons()
        except Exception as e:
            st.error(f"Error: {e}")

# ==========================================
# VISTA: MANTENEDOR (SOLO ADMIN)
# ==========================================
if st.session_state.rol == 'admin':
    with vista_mantenedor:
        st.subheader("Gestión de Usuarios")
        
        # Formulario para crear usuario
        with st.form("crear_usuario"):
            st.write("Nuevo Usuario")
            nuevo_user = st.text_input("Nombre de Usuario")
            nueva_clave = st.text_input("Contraseña", type="password")
            nuevo_rol = st.selectbox("Rol", ["operador", "admin"])
            
            if st.form_submit_button("Crear Usuario"):
                if nuevo_user and nueva_clave:
                    try:
                        supabase.table("usuarios").insert({
                            "usuario": nuevo_user, 
                            "clave": nueva_clave, 
                            "rol": nuevo_rol
                        }).execute()
                        st.success(f"Usuario {nuevo_user} creado.")
                        st.rerun()
                    except Exception as e:
                        st.error("Error al crear. El usuario podría ya existir.")
                else:
                    st.warning("Completa todos los campos.")

        st.divider()
        
        # Lista y eliminación de usuarios
        st.write("Usuarios Actuales")
        usuarios_db = supabase.table("usuarios").select("*").execute().data
        
        for u in usuarios_db:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"👤 {u['usuario']}")
            c2.write(f"🛡️ {u['rol']}")
            if u['usuario'] != 'admin': # Proteger al admin principal
                if c3.button("Eliminar", key=f"del_{u['id']}", type="secondary"):
                    supabase.table("usuarios").delete().eq("id", u['id']).execute()
                    st.rerun()
