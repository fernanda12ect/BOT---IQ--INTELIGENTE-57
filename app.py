import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejores_de_ronda,
    obtener_activos_abiertos,
    generar_alerta_previa,
    ESTRATEGIAS
)

st.set_page_config(
    page_title="NEUROTRADER RONDAS",
    page_icon="🧠",
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
        padding: 20px;
        margin: 10px 0;
        border-left: 6px solid;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .call-card { border-color: #00ff88; }
    .put-card { border-color: #ff4b4b; }
    .waiting-card { border-color: #ffaa00; }
    .alert-card {
        background-color: #2a2a1e;
        border-left: 4px solid #ffaa00;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .asset-box {
        background-color: #1a2a3a;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 4px solid #00a3ff;
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
if 'activos_seguimiento' not in st.session_state:
    st.session_state.activos_seguimiento = []  # lista de activos seleccionados (máx 2)
if 'alertas' not in st.session_state:
    st.session_state.alertas = []
if 'señales' not in st.session_state:
    st.session_state.señales = []
if 'log' not in st.session_state:
    st.session_state.log = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []

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
            # Obtener lista completa de activos
            st.session_state.activos_totales = obtener_activos_abiertos(api, "AMBOS")
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
    st.markdown("## 🧠 NEUROTRADER RONDAS")
    st.markdown("---")
    email = st.text_input("Correo electrónico")
    password = st.text_input("Contraseña", type="password")

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
    mercado = st.selectbox("Mercado", ["OTC", "REAL", "AMBOS"], index=2)
    tamaño_ronda = st.slider("Activos por ronda", 10, 30, 20, 5)
    pausa_entre_rondas = st.slider("Pausa entre rondas (seg)", 10, 120, 30, 10)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.indice_ronda = 0
                st.session_state.activos_seguimiento = []
                st.session_state.alertas = []
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Ronda actual", f"{st.session_state.indice_ronda + 1}")
    with col3:
        st.metric("Señales generadas", len(st.session_state.señales))

    # Activos en seguimiento
    if st.session_state.activos_seguimiento:
        st.subheader("🎯 ACTIVOS EN SEGUIMIENTO (MÁX 2)")
        for activo in st.session_state.activos_seguimiento:
            st.markdown(f"""
            <div class="asset-box">
                <strong>{activo['asset']}</strong> | Puntuación: {activo['puntuacion']} | Estrategias: {', '.join(activo['estrategias'])}
            </div>
            """, unsafe_allow_html=True)

    # Alertas previas
    if st.session_state.alertas:
        st.subheader("🔔 ALERTAS PREVIAS")
        for alerta in st.session_state.alertas[-5:]:
            st.markdown(f'<div class="alert-card">{alerta}</div>', unsafe_allow_html=True)

    # Señales definitivas
    if st.session_state.señales:
        st.subheader("🚀 SEÑALES LISTAS")
        for señal in st.session_state.señales[-5:]:
            card_class = "call-card" if señal['direccion'] == "CALL" else "put-card"
            st.markdown(f"""
            <div class="signal-card {card_class}">
                <div class="signal-title">{'🔵 COMPRA' if señal['direccion'] == 'CALL' else '🔴 VENTA'}</div>
                <div class="signal-detail"><strong>Activo:</strong> {señal['asset']}</div>
                <div class="signal-detail"><strong>Entrada:</strong> {señal['entrada']}</div>
                <div class="signal-detail"><strong>Vencimiento:</strong> {señal['vencimiento']}</div>
                <div class="signal-detail"><strong>Estrategias:</strong> {', '.join(señal['estrategias'])}</div>
            </div>
            """, unsafe_allow_html=True)

    # Historial
    with st.expander("📋 Log de eventos"):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de rondas
    if st.session_state.monitoreando:
        if len(st.session_state.activos_seguimiento) >= 2:
            # Ya tenemos 2 activos, debemos esperar a que den señal o pasar el tiempo
            st.info("Esperando señal de los activos seleccionados...")
            time.sleep(10)
            st.rerun()
        else:
            # Iniciar nueva ronda
            activos_totales = st.session_state.activos_totales
            if not activos_totales:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_entre_rondas)
                st.rerun()

            # Filtrar por mercado
            if mercado == "OTC":
                activos_filtrados = [a for a in activos_totales if '-OTC' in a]
            elif mercado == "REAL":
                activos_filtrados = [a for a in activos_totales if '-OTC' not in a]
            else:
                activos_filtrados = activos_totales

            # Dividir en rondas de tamaño fijo
            inicio = st.session_state.indice_ronda * tamaño_ronda
            fin = inicio + tamaño_ronda
            ronda_actual = activos_filtrados[inicio:fin]

            if not ronda_actual:
                # Fin de la lista, reiniciar
                st.session_state.indice_ronda = 0
                st.rerun()

            st.info(f"Analizando ronda {st.session_state.indice_ronda + 1} ({len(ronda_actual)} activos)...")
            mejores = seleccionar_mejores_de_ronda(st.session_state.api, ronda_actual, max_activos=2)

            if mejores:
                for activo in mejores:
                    # Añadir a seguimiento si no está ya
                    if len(st.session_state.activos_seguimiento) < 2:
                        st.session_state.activos_seguimiento.append(activo)
                        alerta = generar_alerta_previa(activo['asset'], activo['estrategias'])
                        st.session_state.alertas.append(alerta)
                        st.session_state.log.append(f"✅ Activo añadido: {activo['asset']} (puntuación {activo['puntuacion']})")
            else:
                st.session_state.log.append("⚠️ No se encontraron activos confiables en esta ronda.")

            # Avanzar a la siguiente ronda
            st.session_state.indice_ronda += 1
            time.sleep(pausa_entre_rondas)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
