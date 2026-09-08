import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Reporte Productivo", page_icon="🍞", layout="wide")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("⚠️ Configura las credenciales en los secretos de Streamlit (Advanced Settings > Secrets).")
    st.stop()

# --- 2. CARGA DE DATOS MAESTROS ---
@st.cache_data(ttl=600)
def fetch_data(table):
    response = supabase.table(table).select("*").execute()
    return response.data

plantas_db = fetch_data("plantas")
productos_db = fetch_data("productos")
areas_db = fetch_data("areas")
metricas_db = fetch_data("metricas")

nombres_plantas = [p['nombre'] for p in plantas_db]
nombres_productos = [p['nombre'] for p in productos_db]

# Función auxiliar para buscar IDs
def get_id(db, nombre):
    return next((item['id'] for item in db if item['nombre'].lower() == nombre.lower()), None)

# --- 3. INTERFAZ DE USUARIO ---
st.title("🍞 Registro de Producción")

st.header("1. Apertura de Turno")
col1, col2, col3 = st.columns(3)

with col1:
    fecha = st.date_input("Fecha de Producción", datetime.now())
with col2:
    planta = st.selectbox("Planta", nombres_plantas)
with col3:
    turno = st.selectbox("Turno", ["Mañana", "Tarde", "Noche"])

st.divider()

st.header("2. Detalle Operativo")
tab_masa, tab_corte, tab_horno, tab_camara, tab_envasado = st.tabs([
    "Masa", "Corte", "Horno", "Cámara", "Envasado"
])

with tab_masa:
    st.subheader("Preparación de Masa")
    prod_masa = st.selectbox("Producto", nombres_productos, key="prod_masa")
    col_m1, col_m2, col_m3 = st.columns(3)
    batch_m = col_m1.number_input("Batches", min_value=0, step=1, key="batch_m")
    rep_m = col_m2.number_input("Reproceso (Batches)", min_value=0, step=1, key="rep_m")
    bar_m = col_m3.number_input("Barrido (kg)", min_value=0.0, step=0.5, key="bar_m")

with tab_corte:
    st.subheader("Líneas de Corte")
    linea_corte = st.selectbox("Línea", ["C1", "C2", "C3"])
    prod_corte = st.selectbox("Producto", nombres_productos, key="prod_corte")
    col_c1, col_c2, col_c3 = st.columns(3)
    car_c = col_c1.number_input("Carros", min_value=0, step=1, key="car_c")
    har_c = col_c2.number_input("Harina (sacos/kg)", min_value=0.0, step=1.0, key="har_c")
    sem_c = col_c3.number_input("Semillas (sacos/kg)", min_value=0.0, step=1.0, key="sem_c")

with tab_horno:
    st.subheader("Horneado")
    prod_horno = st.selectbox("Producto", nombres_productos, key="prod_horno")
    col_h1, col_h2, col_h3 = st.columns(3)
    car_h = col_h1.number_input("Carros Horneados", min_value=0, step=1, key="car_h")
    aba_h = col_h2.number_input("Abatidor (Carros)", min_value=0, step=1, key="aba_h")
    cru_h = col_h3.number_input("Crudo (Carros)", min_value=0, step=1, key="cru_h")
    col_h4, col_h5 = st.columns(2)
    sem_rec_h = col_h4.number_input("Semilla Recuperada (kg)", min_value=0.0, step=1.0, key="sem_rec_h")
    har_rec_h = col_h5.number_input("Harina Recuperada (kg)", min_value=0.0, step=1.0, key="har_rec_h")

with tab_camara:
    st.subheader("Cámara")
    prod_camara = st.selectbox("Producto", nombres_productos, key="prod_cam")
    col_cam1, col_cam2, col_cam3 = st.columns(3)
    bat_cam = col_cam1.number_input("Batches", min_value=0, step=1, key="bat_cam")
    rep_cam = col_cam2.number_input("Reproceso Integral", min_value=0, step=1, key="rep_cam")
    mer_cam = col_cam3.number_input("Merma Reproceso (kg)", min_value=0.0, step=0.5, key="mer_cam")

with tab_envasado:
    st.subheader("Envasado")
    prod_envasado = st.selectbox("Producto", nombres_productos, key="prod_env")
    col_e1, col_e2 = st.columns(2)
    caj_env = col_e1.number_input("Cajas", min_value=0, step=1, key="caj_env")
    mer_env = col_e2.number_input("Merma (kg)", min_value=0.0, step=0.5, key="mer_env")

st.divider()

# --- 4. LÓGICA DE GUARDADO ---
if st.button("💾 Guardar Reporte de Turno", type="primary", use_container_width=True):
    
    # Insertar Cabecera
    planta_id = get_id(plantas_db, planta)
    data_turno = {
        "fecha": str(fecha),
        "planta_id": planta_id,
        "turno": turno
    }
    
    try:
        res_turno = supabase.table("reporte_turnos").insert(data_turno).execute()
        turno_id = res_turno.data[0]['id']
        
        # Preparar Detalles (solo guardamos lo que sea mayor a 0 para no ensuciar la BD)
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

        # Recolectar datos de Masa
        agregar_detalle("Masa", prod_masa, "Batch", batch_m)
        agregar_detalle("Masa", prod_masa, "Reproceso", rep_m)
        agregar_detalle("Masa", prod_masa, "Barrido", bar_m)
        
        # Recolectar datos de Corte
        agregar_detalle("Corte", prod_corte, "Carros", car_c, linea_corte)
        agregar_detalle("Corte", prod_corte, "Harina", har_c, linea_corte)
        agregar_detalle("Corte", prod_corte, "Semilla", sem_c, linea_corte)
        
        # Recolectar datos de Horno
        agregar_detalle("Horno", prod_horno, "Carros", car_h)
        agregar_detalle("Horno", prod_horno, "Abatidor", aba_h)
        agregar_detalle("Horno", prod_horno, "Crudo", cru_h)
        agregar_detalle("Horno", prod_horno, "Semilla Recuperada", sem_rec_h)
        agregar_detalle("Horno", prod_horno, "Harina Recuperada", har_rec_h)
        
        # Recolectar datos de Cámara
        agregar_detalle("Cámara", prod_camara, "Batch", bat_cam)
        agregar_detalle("Cámara", prod_camara, "Reproceso", rep_cam)
        agregar_detalle("Cámara", prod_camara, "Merma", mer_cam)
        
        # Recolectar datos de Envasado
        agregar_detalle("Envasado", prod_envasado, "Cajas", caj_env)
        agregar_detalle("Envasado", prod_envasado, "Merma", mer_env)

        # Insertar Detalles en bloque
        if detalles_a_insertar:
            supabase.table("reporte_detalles").insert(detalles_a_insertar).execute()
        
        st.success(f"✅ Reporte ingresado correctamente. ID de Turno: {turno_id}")
        st.balloons()
        
    except Exception as e:
        st.error(f"Error al guardar: {e}")
