import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# 1. Configuración de la página
st.set_page_config(page_title="Reporte Productivo", page_icon="🍞", layout="wide")

# 2. Conexión a Supabase (usaremos los secretos de Streamlit)
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("⚠️ Configura las credenciales de Supabase en los secretos de Streamlit.")
    st.stop()

# 3. Funciones para traer los datos maestros (Catálogos)
@st.cache_data(ttl=600)
def get_plantas():
    response = supabase.table("plantas").select("*").execute()
    return response.data

@st.cache_data(ttl=600)
def get_productos():
    response = supabase.table("productos").select("*").execute()
    return response.data

# Traemos los datos de la base de datos
plantas_db = get_plantas()
productos_db = get_productos()

# Extraemos solo los nombres para los menús desplegables
nombres_plantas = [p['nombre'] for p in plantas_db]
nombres_productos = [p['nombre'] for p in productos_db]

# --- INTERFAZ DE USUARIO ---
st.title("🍞 Registro de Producción")

# --- Sección 1: Cabecera del Turno ---
st.header("1. Apertura de Turno")
col1, col2, col3 = st.columns(3)

with col1:
    fecha = st.date_input("Fecha de Producción", datetime.now())
with col2:
    planta = st.selectbox("Planta", nombres_plantas)
with col3:
    turno = st.selectbox("Turno", ["Mañana", "Tarde", "Noche"])

st.divider()

# --- Sección 2: Registro por Áreas ---
st.header("2. Detalle Operativo")
st.caption("Ingresa los datos correspondientes a cada etapa del proceso.")

# Creamos las pestañas para ordenar el flujo
tab_masa, tab_corte, tab_horno, tab_camara, tab_envasado = st.tabs([
    "Masa", "Corte", "Horno", "Cámara", "Envasado"
])

with tab_masa:
    st.subheader("Preparación de Masa")
    prod_masa = st.selectbox("Producto", nombres_productos, key="prod_masa")
    
    col_m1, col_m2, col_m3 = st.columns(3)
    batch = col_m1.number_input("Batches", min_value=0, step=1, key="batch_m")
    reproceso = col_m2.number_input("Reproceso (Batches)", min_value=0, step=1, key="rep_m")
    barrido = col_m3.number_input("Barrido (kg)", min_value=0.0, step=0.5, key="bar_m")

with tab_corte:
    st.subheader("Líneas de Corte")
    linea_corte = st.selectbox("Línea", ["C1", "C2", "C3"])
    prod_corte = st.selectbox("Producto", nombres_productos, key="prod_corte")
    
    col_c1, col_c2, col_c3 = st.columns(3)
    carros = col_c1.number_input("Carros", min_value=0, step=1, key="car_c")
    harina = col_c2.number_input("Harina (sacos/kg)", min_value=0.0, step=1.0, key="har_c")
    semilla = col_c3.number_input("Semillas (sacos/kg)", min_value=0.0, step=1.0, key="sem_c")

# Dejé las otras pestañas (Horno, Cámara, Envasado) vacías por ahora para que probemos la base primero.

st.divider()
st.button("💾 Guardar Reporte de Turno", type="primary", use_container_width=True)
