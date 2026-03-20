import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejor_activo,
    obtener_activos_otc
)

st.set_page_config(
    page_title="NEUROTRADER OTC 1MIN",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (similares a anteriores)
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
        position: relative;
        overflow: hidden;
    }
    .signal-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 25px 40px -12px rgba(0,0,0,0.6);
        border-color: #00a3ff;
    }
    .signal-title {
        font-size: 1.4rem;
        font-weight: bold;
        margin-bottom: 10px;
        color: #fff;
        text-shadow: 0 2px 5px rgba(0,0,0,0.3);
    }
    .signal-status {
        font-size: 0.9rem;
        padding: 4px 12px;
        border-radius: 20px;
        display: inline-block;
        background: rgba(0,0,0,0.5);
        margin-bottom: 15px;
    }
    .call {
        border-left: 5px solid #00ff88;
        background: linear-gradient(90deg, rgba(0,255,136,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .put {
        border-left: 5px solid #ff4b4b;
        background: linear-gradient(90deg, rgba(255,75,75,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .force-bar {
        background: #2a2f3a;
        border-radius: 10px;
        height: 8px;
        margin: 10px 0;
        overflow: hidden;
    }
    .force-fill {
        background: linear-gradient(90deg, #00a3ff, #00ff88);
        width: 0%;
        height: 100%;
        border-radius: 10px;
        transition: width 0.5s;
    }
    .entry-time {
        font-family: monospace;
        font-size: 1.1rem;
        color: #ffaa00;
        margin-top: 5px;
    }
    hr {
        border-color: #2a2f3a;
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
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'ultima_evaluacion' not in st.session_state:
    st.session_state.ultima_evaluacion = None

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
    st.markdown("## ⚡ NEUROTRADER OTC 1MIN")
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

    umbral_fuerza = st.slider("Fuerza mínima para señal (%)", 0, 100, 50, 5)
    st.info("La señal se generará en el segundo 59 de cada minuto.")

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
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
    st.title("⚡ Señales OTC 1 Minuto - Segundo 59")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Estado", "ACTIVO" if st.session_state.monitoreando else "DETENIDO")
    with col3:
        st.metric("Última señal", "Sí" if st.session_state.senal_actual else "No")

    # Mostrar señal actual si existe
    if st.session_state.senal_actual:
        s = st.session_state.senal_actual
        card_class = "call" if s['direccion'] == "CALL" else "put"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if s['direccion'] == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-status">✅ SEÑAL ACTIVA</div>
            <div><strong>Activo:</strong> {s['asset']}</div>
            <div><strong>Descripción:</strong> {s['descripcion']}</div>
            <div><strong>Fuerza:</strong> {s['fuerza']:.1f}%</div>
            <div class="force-bar"><div class="force-fill" style="width: {s['fuerza']}%;"></div></div>
            <div><strong>Tipo activo:</strong> {s['tipo_activo']}</div>
            <div class="entry-time">⏱️ Entrada: {s['entrada']} | Vencimiento: {s['vencimiento']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa. Esperando próximo minuto...")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)
        segundo = now.second

        # Si hay señal activa, esperar a que expire (1 min después de entrada)
        if st.session_state.senal_actual:
            entrada_dt = datetime.strptime(st.session_state.senal_actual['entrada'], "%H:%M:%S").time()
            entrada_completa = datetime.combine(now.date(), entrada_dt)
            entrada_completa = ecuador.localize(entrada_completa)
            if entrada_completa > now:
                entrada_completa -= timedelta(days=1)
            expiracion = entrada_completa + timedelta(minutes=1)
            if now >= expiracion:
                st.session_state.senal_actual = None
                st.session_state.log.append("🗑️ Señal expirada")
                st.rerun()
            else:
                # Mostrar tiempo restante
                seg_rest = (expiracion - now).total_seconds()
                st.info(f"⏳ Señal activa. Vence en {int(seg_rest)} segundos...")
                time.sleep(1)
                st.rerun()
        else:
            # No hay señal, evaluar en el segundo 59
            if segundo == 59:
                # Realizar análisis
                with st.spinner("Analizando activos OTC..."):
                    activos = obtener_activos_otc(st.session_state.api)
                    if not activos:
                        st.session_state.log.append("⚠️ No hay activos OTC disponibles")
                    else:
                        mejor = seleccionar_mejor_activo(st.session_state.api, activos)
                        if mejor and mejor['fuerza'] >= umbral_fuerza:
                            # Calcular entrada y vencimiento
                            entrada_dt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                            entrada_str = entrada_dt.strftime("%H:%M:%S")
                            vencimiento_dt = entrada_dt + timedelta(minutes=1)
                            vencimiento_str = vencimiento_dt.strftime("%H:%M:%S")
                            st.session_state.senal_actual = {
                                'asset': mejor['asset'],
                                'direccion': mejor['direccion'],
                                'descripcion': mejor['descripcion'],
                                'fuerza': mejor['fuerza'],
                                'tipo_activo': mejor['tipo_activo'],
                                'entrada': entrada_str,
                                'vencimiento': vencimiento_str
                            }
                            st.session_state.log.append(f"🚀 SEÑAL: {mejor['asset']} - {mejor['direccion']} a las {entrada_str}")
                        else:
                            st.session_state.log.append("🔍 No se encontró señal con fuerza suficiente")
                # Esperar a que pase el segundo 59 para no repetir en el mismo minuto
                time.sleep(1)
                st.rerun()
            else:
                # Mostrar tiempo restante hasta el segundo 59
                seg_rest = 59 - segundo if segundo < 59 else 59 + (60 - segundo)
                st.info(f"⏳ Próximo análisis en {seg_rest} segundos...")
                time.sleep(1)
                st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
