import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejor_activo,
    obtener_activos_abiertos,
    ESTRATEGIAS
)

st.set_page_config(
    page_title="NEUROTRADER - 10 ESTRATEGIAS",
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
if 'activo_seleccionado' not in st.session_state:
    st.session_state.activo_seleccionado = None
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'proxima_evaluacion' not in st.session_state:
    st.session_state.proxima_evaluacion = None
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
            st.session_state.activos_totales = obtener_activos_abiertos(api, "AMBOS")
            st.session_state.log.append(f"📊 Total activos disponibles: {len(st.session_state.activos_totales)}")
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
    st.session_state.activo_seleccionado = None
    st.session_state.senal_actual = None

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER")
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
    min_votos = st.slider("Mínimo de estrategias para seleccionar", 1, 5, 2, 1)
    umbral_fuerza = st.slider("Umbral de fuerza para mantener activo", 0, 100, 50, 5)
    tamanio_ronda = st.slider("Activos por ronda", 10, 50, 20, 5)
    pausa_rondas = st.slider("Pausa entre rondas (seg)", 5, 30, 10, 5)
    anticipacion = st.slider("Anticipación de señal (seg)", 5, 30, 20, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.indice_ronda = 0
                st.session_state.activo_seleccionado = None
                st.session_state.senal_actual = None
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
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        if st.session_state.activo_seleccionado:
            st.metric("Activo actual", st.session_state.activo_seleccionado['asset'])
        else:
            st.metric("Activo actual", "Ninguno")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))

    if st.session_state.senal_actual:
        s = st.session_state.senal_actual
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA' if s['direccion'] == 'CALL' else '🔴 VENTA'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {s['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {s['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> 5 minutos</div>
            <div class="signal-detail"><strong>Votos:</strong> CALL {s['votos_call']} / PUT {s['votos_put']}</div>
            <div class="signal-detail"><strong>Fuerza:</strong> {s['fuerza']:.1f}</div>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si hay un activo seleccionado, evaluamos cada 5 minutos
        if st.session_state.activo_seleccionado:
            if st.session_state.proxima_evaluacion is None:
                # Sincronizar con el cierre de la vela de 5 minutos
                minutos = now.minute
                resto = minutos % 5
                if resto == 0:
                    prox = now + timedelta(minutes=5)
                else:
                    prox = now + timedelta(minutes=(5 - resto))
                prox = prox.replace(second=0, microsecond=0)
                st.session_state.proxima_evaluacion = prox

            if now >= st.session_state.proxima_evaluacion:
                # Evaluar el activo actual
                res = evaluar_activo(st.session_state.api, st.session_state.activo_seleccionado['asset'])
                if res and res['fuerza'] >= umbral_fuerza and (res['votos_call'] + res['votos_put']) >= min_votos:
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    st.session_state.senal_actual = {
                        'asset': res['asset'],
                        'direccion': res['direccion'],
                        'entrada': entrada_str,
                        'votos_call': res['votos_call'],
                        'votos_put': res['votos_put'],
                        'fuerza': res['fuerza']
                    }
                    st.session_state.log.append(f"🚀 SEÑAL GENERADA: {res['asset']} - {res['direccion']} a las {entrada_str}")
                elif res is None:
                    st.session_state.log.append(f"⚠️ {st.session_state.activo_seleccionado['asset']} perdió fuerza. Buscando otro...")
                    st.session_state.activo_seleccionado = None
                st.session_state.proxima_evaluacion += timedelta(minutes=5)
                time.sleep(1)
                st.rerun()
            else:
                segundos = (st.session_state.proxima_evaluacion - now).total_seconds()
                st.info(f"⏳ Próxima evaluación en {int(segundos)} segundos...")
                time.sleep(1)
                st.rerun()
        else:
            # No hay activo, buscamos uno nuevo
            activos = st.session_state.activos_totales
            if not activos:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_rondas)
                st.rerun()

            inicio = st.session_state.indice_ronda * tamanio_ronda
            fin = inicio + tamanio_ronda
            ronda = activos[inicio:fin]

            if not ronda:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"Analizando ronda {st.session_state.indice_ronda + 1} ({len(ronda)} activos)...")
            mejor = seleccionar_mejor_activo(st.session_state.api, ronda, min_votos)

            if mejor:
                st.session_state.activo_seleccionado = mejor
                st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']} (votos CALL/PUT: {mejor['votos_call']}/{mejor['votos_put']})")
                st.session_state.proxima_evaluacion = None
            else:
                st.session_state.log.append("⚠️ No se encontraron activos con suficientes estrategias.")

            st.session_state.indice_ronda += 1
            time.sleep(pausa_rondas)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
