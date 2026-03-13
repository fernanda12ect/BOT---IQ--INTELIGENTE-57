import streamlit as st
import pandas as pd
import time
from datetime import datetime
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    seleccionar_mejores_senales,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER - 2 ESTRATEGIAS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS
st.markdown("""
<style>
    .stApp { background-color: #0b0f17; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #1a1f2b; border-right: 1px solid #2a2f3a; }
    div[data-testid="stMetric"] { background-color: #1e2430; border-radius: 8px; padding: 15px; border-left: 4px solid #00a3ff; }
    .stButton > button { background-color: #2a2f3a; color: white; border: 1px solid #3a4050; border-radius: 5px; padding: 10px 20px; font-weight: 500; }
    .stButton > button:hover { background-color: #3a4050; border-color: #00a3ff; }
    .signal-card {
        background-color: #1e2a3a;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        border-left: 6px solid;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .call-card { border-color: #00ff88; }
    .put-card { border-color: #ff4b4b; }
    .sr-card { border-color: #00a3ff; }
    .trend-card { border-color: #ffaa00; }
    .asset-title {
        font-size: 1.2rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .signal-detail {
        font-size: 0.9rem;
        color: #ccc;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'conectado' not in st.session_state:
    st.session_state.conectado = False
if 'tipo_cuenta' not in st.session_state:
    st.session_state.tipo_cuenta = "PRACTICE"
if 'saldo' not in st.session_state:
    st.session_state.saldo = 0.0
if 'monitoreando' not in st.session_state:
    st.session_state.monitoreando = False
if 'senales' not in st.session_state:
    st.session_state.senales = []
if 'log' not in st.session_state:
    st.session_state.log = []

# Zona horaria
ecuador = pytz.timezone("America/Guayaquil")

def conectar(email, password):
    try:
        api = IQ_Option(email, password)
        check, reason = api.connect()
        if check:
            st.session_state.api = api
            st.session_state.conectado = True
            api.change_balance(st.session_state.tipo_cuenta)
            saldo = api.get_balance()
            st.session_state.saldo = saldo if saldo is not None else 0.0
            st.session_state.log.append(f"✅ Conectado - Saldo: {st.session_state.saldo}")
            return True
        else:
            st.error(f"Error: {reason}")
            return False
    except Exception as e:
        st.error(f"Excepción: {e}")
        return False

def desconectar():
    st.session_state.api = None
    st.session_state.conectado = False
    st.session_state.monitoreando = False

# Sidebar
with st.sidebar:
    st.markdown("## 📊 NEUROTRADER")
    st.markdown("---")
    email = st.text_input("📧 Correo electrónico")
    password = st.text_input("🔑 Contraseña", type="password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 CONECTAR", use_container_width=True):
            if email and password:
                conectar(email, password)
            else:
                st.warning("Ingresa credenciales")
    with col2:
        if st.button("⛔ DESCONECTAR", use_container_width=True):
            desconectar()

    st.markdown("---")
    st.markdown("### ⚙️ Configuración")

    tipo_mercado = st.selectbox("Mercado", ["OTC", "REAL", "AMBOS"], index=2)
    max_activos = st.slider("Máximo de señales a mostrar", 1, 8, 4, 1)
    umbral_distancia = st.slider("Distancia máxima al nivel (%)", 0.1, 2.0, 0.5, 0.1) / 100
    intervalo_actualizacion = st.slider("Intervalo de actualización (seg)", 5, 60, 15, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("📊 Señales de Trading - 5 minutos")

    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Señales activas", len(st.session_state.senales))
    with col3:
        st.metric("Última actualización", datetime.now(ecuador).strftime("%H:%M:%S"))

    # Mostrar señales en tarjetas
    if st.session_state.senales:
        # Crear columnas para las tarjetas (hasta 4)
        cols = st.columns(min(len(st.session_state.senales), 4))
        for idx, senal in enumerate(st.session_state.senales[:4]):
            with cols[idx % 4]:
                # Determinar estilo según tipo
                if senal['tipo'] == 'soporte/resistencia':
                    card_class = "sr-card"
                else:
                    card_class = "trend-card"
                
                # Color de fondo según dirección
                if senal['direccion'] == 'CALL':
                    bg_color = "#1e3a2e"
                else:
                    bg_color = "#3a1e1e"

                st.markdown(f"""
                <div class="signal-card {card_class}" style="background-color: {bg_color};">
                    <div class="asset-title">{senal['asset']}</div>
                    <div><strong>{senal['tipo'].upper()}</strong> - {senal['subtipo']}</div>
                    <div class="signal-detail">Dirección: {senal['direccion']}</div>
                    <div class="signal-detail">Nivel: {senal['nivel']:.5f}</div>
                    <div class="signal-detail">Distancia: {senal['distancia']:.2f}%</div>
                    <div class="signal-detail">Fuerza: {senal['fuerza']:.0f}%</div>
                    <div class="signal-detail">Vencimiento: 5 min</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No hay señales activas en este momento.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        # Obtener lista de activos
        activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
        if not activos:
            st.warning("No se pudieron obtener activos. Reintentando...")
            time.sleep(intervalo_actualizacion)
            st.rerun()

        # Seleccionar las mejores señales
        nuevas_senales = seleccionar_mejores_senales(
            st.session_state.api,
            activos,
            max_activos=max_activos
        )
        st.session_state.senales = nuevas_senales
        st.session_state.log.append(f"🔄 Actualizado: {len(nuevas_senales)} señales encontradas")

        # Esperar y actualizar
        time.sleep(intervalo_actualizacion)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
