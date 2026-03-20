import streamlit as st
import threading
import time
from datetime import datetime
import pytz
from bot_engine import BotState, bot_engine
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(
    page_title="NEUROTRADER OTC - AUTOMÁTICO",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (mismo que antes)
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0a0c15 0%, #121724 100%);
        font-family: 'Segoe UI', 'Poppins', sans-serif;
    }
    section[data-testid="stSidebar"] {
        background: rgba(18, 23, 36, 0.95);
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(0, 163, 255, 0.2);
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #1e2435, #151b2a);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        border: 1px solid rgba(0, 163, 255, 0.2);
        transition: transform 0.2s;
    }
    .stButton > button {
        background: linear-gradient(90deg, #00a3ff, #0066cc);
        border: none;
        border-radius: 30px;
        color: white;
        font-weight: bold;
        padding: 10px 20px;
        transition: all 0.3s;
        box-shadow: 0 4px 10px rgba(0,163,255,0.3);
    }
    .stButton > button:hover {
        transform: scale(1.02);
        background: linear-gradient(90deg, #00b4ff, #0077ee);
        box-shadow: 0 6px 15px rgba(0,163,255,0.5);
    }
    .status-card {
        background: linear-gradient(145deg, #1a2032, #0f1422);
        border-radius: 20px;
        padding: 20px;
        margin: 15px 0;
        box-shadow: 0 20px 35px -10px rgba(0,0,0,0.5);
        border: 1px solid rgba(0, 163, 255, 0.3);
    }
    .trade-card {
        background: linear-gradient(145deg, #1a2032, #0f1422);
        border-radius: 20px;
        padding: 20px;
        margin: 10px 0;
        border-left: 5px solid;
    }
    .trade-win {
        border-left-color: #00ff88;
    }
    .trade-loss {
        border-left-color: #ff4b4b;
    }
    .trade-pending {
        border-left-color: #ffaa00;
    }
    .asset-name {
        font-size: 1.2rem;
        font-weight: bold;
        margin-bottom: 5px;
        color: #fff;
    }
    .entry-time {
        font-family: monospace;
        font-size: 0.9rem;
        color: #ffaa00;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar estado compartido (si no existe)
if 'bot_state' not in st.session_state:
    st.session_state.bot_state = BotState()

state = st.session_state.bot_state

# Control de hilo del motor
if 'engine_thread' not in st.session_state:
    st.session_state.engine_thread = None

def start_engine():
    if st.session_state.engine_thread is None or not st.session_state.engine_thread.is_alive():
        st.session_state.engine_thread = threading.Thread(target=bot_engine, args=(state,), daemon=True)
        st.session_state.engine_thread.start()

# Sidebar
with st.sidebar:
    st.markdown("## 🤖 NEUROTRADER OTC - AUTOMÁTICO")
    st.markdown("---")
    email = st.text_input("📧 Correo electrónico")
    password = st.text_input("🔑 Contraseña", type="password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 CONECTAR", use_container_width=True):
            if email and password:
                try:
                    api = IQ_Option(email, password)
                    check, reason = api.connect()
                    if check:
                        state.api = api
                        state.api.change_balance(state.tipo_cuenta)
                        saldo = state.api.get_balance()
                        state.saldo = saldo if saldo is not None else 0.0
                        state.add_log(f"✅ Conectado - Saldo: {state.saldo}")
                    else:
                        st.error(f"Error de conexión: {reason}")
                except Exception as e:
                    st.error(f"Excepción: {e}")
            else:
                st.warning("Ingresa credenciales")
    with col2:
        if st.button("⛔ DESCONECTAR", use_container_width=True):
            state.api = None
            state.running = False
            state.add_log("🔌 Desconectado")

    st.markdown("---")
    st.markdown("### ⚙️ Configuración")
    tipo_cuenta = st.radio("Tipo de cuenta", ["PRACTICE", "REAL"], index=0, horizontal=True)
    if tipo_cuenta != state.tipo_cuenta:
        state.tipo_cuenta = tipo_cuenta
        if state.api:
            state.api.change_balance(tipo_cuenta)
            saldo = state.api.get_balance()
            state.saldo = saldo if saldo is not None else 0.0
            state.add_log(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {state.saldo}")

    monto = st.number_input("💵 Monto por operación ($)", min_value=0.5, max_value=100.0, value=1.0, step=0.5)
    state.monto = monto

    st.markdown("---")
    if state.api:
        if not state.running:
            if st.button("▶️ INICIAR BOT", use_container_width=True, type="primary"):
                state.running = True
                start_engine()
                state.add_log("🚀 Bot automático iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER BOT", use_container_width=True, type="secondary"):
                state.running = False
                state.add_log("🛑 Bot detenido")
                st.rerun()

    if state.api:
        st.metric("💰 Saldo", f"${state.saldo:.2f}")

# Área principal
if state.api:
    st.title("🤖 Bot Automático - 1 minuto")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${state.saldo:.2f}")
    with col2:
        st.metric("Estado", "ACTIVO" if state.running else "DETENIDO")
    with col3:
        if state.current_trade:
            st.metric("Operación", "En curso")
        else:
            st.metric("Operación", "Listo")

    if state.current_trade:
        t = state.current_trade
        st.markdown(f"""
        <div class="status-card trade-card trade-pending">
            <div class="asset-name">🔄 OPERACIÓN EN CURSO</div>
            <div><strong>{t['asset']}</strong> - {t['direccion']}</div>
            <div>Monto: ${t['monto']}</div>
            <div class="entry-time">Entrada: {t['entrada']}</div>
            <div class="entry-time">Vencimiento: {t['vencimiento']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay operación en curso. El bot analizará en el próximo minuto.")

    if state.trades:
        st.subheader("📋 Historial de operaciones")
        for trade in state.trades[-10:]:
            card_class = "trade-win" if trade['estado'] == "GANADA" else "trade-loss" if trade['estado'] == "PERDIDA" else "trade-pending"
            st.markdown(f"""
            <div class="trade-card {card_class}">
                <div class="asset-name">{trade['asset']} - {trade['direccion']}</div>
                <div>Monto: ${trade['monto']}</div>
                <div>Entrada: {trade['entrada']} | Vencimiento: {trade['vencimiento']}</div>
                <div>Resultado: {trade['estado']}</div>
            </div>
            """, unsafe_allow_html=True)

    with st.expander("📋 Log de eventos", expanded=True):
        for linea in state.logs[-30:]:
            st.text(linea)

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
