import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    obtener_activos_otc,
    seleccionar_mejor_senal,
    analizar_activo
)

st.set_page_config(
    page_title="NEUROTRADER OTC - SEGUIMIENTO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS profesionales (igual que antes)
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
    .signal-card {
        background: linear-gradient(145deg, #1a2032, #0f1422);
        border-radius: 20px;
        padding: 20px;
        margin: 15px 0;
        box-shadow: 0 20px 35px -10px rgba(0,0,0,0.5);
        border: 1px solid rgba(0, 163, 255, 0.3);
        transition: all 0.3s ease;
    }
    .call-card {
        border-left: 5px solid #00ff88;
        background: linear-gradient(90deg, rgba(0,255,136,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .put-card {
        border-left: 5px solid #ff4b4b;
        background: linear-gradient(90deg, rgba(255,75,75,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .no-signal-card {
        border-left: 5px solid #ffaa00;
        background: linear-gradient(90deg, rgba(255,170,0,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .asset-name {
        font-size: 1.4rem;
        font-weight: bold;
        margin-bottom: 10px;
        color: #fff;
        text-shadow: 0 2px 5px rgba(0,0,0,0.3);
    }
    .entry-time {
        font-family: monospace;
        font-size: 1.1rem;
        color: #ffaa00;
        margin-top: 5px;
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
if 'current_asset' not in st.session_state:
    st.session_state.current_asset = None  # {'asset': str, 'direccion': str, 'descripcion': str}
if 'ultima_senal' not in st.session_state:
    st.session_state.ultima_senal = None
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
    st.markdown("## 📈 NEUROTRADER OTC - SEGUIMIENTO")
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
    st.markdown("El bot se enfoca en un activo mientras sea estable.")
    st.markdown("Si pierde estabilidad, busca otro automáticamente.")

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
    st.title("📊 Señales de 1 minuto (segundo 59) - Enfoque en un activo")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Estado", "ACTIVO" if st.session_state.monitoreando else "DETENIDO")
    with col3:
        st.metric("Activo actual", st.session_state.current_asset['asset'] if st.session_state.current_asset else "Ninguno")

    # Mostrar última señal
    if st.session_state.ultima_senal:
        s = st.session_state.ultima_senal
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="asset-name">{s['asset']}</div>
            <div><strong>{s['direccion']}</strong> - {s['descripcion']}</div>
            <div class="entry-time">⏱️ Entrada: {s['entrada']}</div>
            <div class="entry-time">⏰ Vencimiento: 1 minuto</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="signal-card no-signal-card">
            <div class="asset-name">SIN SEÑAL</div>
            <div>Esperando condiciones...</div>
        </div>
        """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de sincronización al segundo 59 con seguimiento de un activo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)
        segundo = now.second

        # Si estamos en el segundo 58, preparamos el análisis para el segundo 59
        if segundo == 58:
            # Pequeña espera para llegar al segundo 59 exacto
            time.sleep(0.5)
            # Evaluar el activo actual si existe
            if st.session_state.current_asset:
                asset_name = st.session_state.current_asset['asset']
                # Analizar si el activo actual sigue siendo válido
                res = analizar_activo(st.session_state.api, asset_name)
                if res and res['senal']:
                    # Sigue siendo válido, reutilizar
                    direccion, desc = res['senal']
                    entrada = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    st.session_state.ultima_senal = {
                        'asset': asset_name,
                        'direccion': direccion,
                        'descripcion': desc,
                        'entrada': entrada_str
                    }
                    st.session_state.log.append(f"🔄 SEÑAL (reutilizando {asset_name}): {direccion} a las {entrada_str}")
                else:
                    # El activo actual ya no es estable, buscar otro
                    st.session_state.log.append(f"⚠️ {asset_name} perdió estabilidad. Buscando nuevo activo...")
                    st.session_state.current_asset = None
                    # Realizar búsqueda de un nuevo activo
                    activos = obtener_activos_otc(st.session_state.api)
                    mejor = seleccionar_mejor_senal(st.session_state.api, activos)
                    if mejor:
                        direccion, desc = mejor['senal']
                        entrada = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                        entrada_str = entrada.strftime("%H:%M:%S")
                        st.session_state.current_asset = {
                            'asset': mejor['asset'],
                            'direccion': direccion,
                            'descripcion': desc
                        }
                        st.session_state.ultima_senal = {
                            'asset': mejor['asset'],
                            'direccion': direccion,
                            'descripcion': desc,
                            'entrada': entrada_str
                        }
                        st.session_state.log.append(f"🚀 NUEVO ACTIVO: {mejor['asset']} - {direccion} a las {entrada_str}")
                    else:
                        st.session_state.log.append("🔍 SIN SEÑAL – ESPERAR PROXIMO MINUTO")
            else:
                # No hay activo actual, buscar el mejor
                activos = obtener_activos_otc(st.session_state.api)
                mejor = seleccionar_mejor_senal(st.session_state.api, activos)
                if mejor:
                    direccion, desc = mejor['senal']
                    entrada = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    st.session_state.current_asset = {
                        'asset': mejor['asset'],
                        'direccion': direccion,
                        'descripcion': desc
                    }
                    st.session_state.ultima_senal = {
                        'asset': mejor['asset'],
                        'direccion': direccion,
                        'descripcion': desc,
                        'entrada': entrada_str
                    }
                    st.session_state.log.append(f"🚀 SEÑAL: {mejor['asset']} - {direccion} a las {entrada_str}")
                else:
                    st.session_state.log.append("🔍 SIN SEÑAL – ESPERAR PROXIMO MINUTO")
            # Forzar rerun para mostrar la señal
            time.sleep(0.2)
            st.rerun()
        else:
            # Mostrar cuánto falta para el próximo segundo 59
            if segundo < 58:
                seg_rest = 58 - segundo
            else:
                seg_rest = 60 - segundo + 58
            st.info(f"⏳ Próxima señal en {seg_rest} segundos...")
            time.sleep(1)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
