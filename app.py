import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    buscar_candidato,
    evaluar_confirmacion_final,
    obtener_activos_disponibles,
    ACTIVOS_TARGET
)

st.set_page_config(
    page_title="NEUROTRADER PRO",
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
if 'candidato' not in st.session_state:
    st.session_state.candidato = None  # activo seleccionado en espera de confirmación
if 'alerta' not in st.session_state:
    st.session_state.alerta = None
if 'señal' not in st.session_state:
    st.session_state.señal = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0
if 'activos_a_analizar' not in st.session_state:
    st.session_state.activos_a_analizar = []  # lista completa de activos a escanear
if 'tiempo_inicio_espera' not in st.session_state:
    st.session_state.tiempo_inicio_espera = None

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
            # Podemos obtener activos de la API o usar la lista predefinida
            # Por ahora, usamos la lista predefinida más algunos OTC si se desea
            st.session_state.activos_a_analizar = ACTIVOS_TARGET.copy()
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
    st.session_state.candidato = None
    st.session_state.alerta = None
    st.session_state.señal = None

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER PRO")
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
    # Opción de usar lista predefinida o todos los activos
    modo_activos = st.radio("Activos a analizar", ["Lista objetivo", "Todos (OTC+REAL)"], index=0)
    tiempo_max_espera = st.slider("Tiempo máximo de espera (min)", 5, 60, 15, 5,
                                   help="Si el candidato no confirma en este tiempo, se descarta")
    pausa_entre_rondas = st.slider("Pausa entre escaneos (seg)", 5, 30, 10, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.candidato = None
                st.session_state.alerta = None
                st.session_state.señal = None
                st.session_state.indice_ronda = 0
                if modo_activos == "Lista objetivo":
                    st.session_state.activos_a_analizar = ACTIVOS_TARGET.copy()
                else:
                    # Obtener todos los activos abiertos
                    st.session_state.activos_a_analizar = obtener_activos_disponibles(st.session_state.api, "AMBOS")
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
        if st.session_state.candidato:
            st.metric("Candidato", st.session_state.candidato['asset'])
        else:
            st.metric("Candidato", "Ninguno")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "SEÑAL" in s]))

    # Alerta (cuando hay candidato en espera)
    if st.session_state.alerta:
        st.markdown(f'<div class="alert-card">{st.session_state.alerta}</div>', unsafe_allow_html=True)

    # Señal definitiva
    if st.session_state.señal:
        card_class = "call-card" if st.session_state.señal['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA' if st.session_state.señal['direccion'] == 'CALL' else '🔴 VENTA'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {st.session_state.señal['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {st.session_state.señal['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {st.session_state.señal['vencimiento']}</div>
            <div class="signal-detail"><strong>Estrategia:</strong> {st.session_state.señal['estrategia']}</div>
        </div>
        """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos"):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si ya hay una señal, esperamos 5 minutos y luego reiniciamos
        if st.session_state.señal:
            tiempo_transcurrido = (now - st.session_state.señal['timestamp']).total_seconds()
            if tiempo_transcurrido > 300:  # 5 minutos
                st.session_state.candidato = None
                st.session_state.alerta = None
                st.session_state.señal = None
                st.session_state.log.append("🔄 Reiniciando búsqueda...")
                time.sleep(2)
                st.rerun()
            else:
                time.sleep(5)
                st.rerun()
        elif st.session_state.candidato:
            # Estamos esperando confirmación de un candidato
            # Verificar timeout
            if st.session_state.tiempo_inicio_espera is None:
                st.session_state.tiempo_inicio_espera = now
            else:
                tiempo_espera = (now - st.session_state.tiempo_inicio_espera).total_seconds() / 60
                if tiempo_espera > tiempo_max_espera:
                    st.session_state.log.append(f"⏰ Timeout: {st.session_state.candidato['asset']} no confirmó. Buscando otro...")
                    st.session_state.candidato = None
                    st.session_state.alerta = None
                    st.session_state.tiempo_inicio_espera = None
                    time.sleep(2)
                    st.rerun()

            # Evaluar confirmación final
            listo, direccion, estrategia = evaluar_confirmacion_final(
                st.session_state.api,
                st.session_state.candidato['asset'],
                st.session_state.candidato
            )
            if listo:
                entrada = now.strftime("%H:%M:%S")
                vencimiento = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
                st.session_state.señal = {
                    'asset': st.session_state.candidato['asset'],
                    'direccion': direccion,
                    'entrada': entrada,
                    'vencimiento': vencimiento,
                    'estrategia': estrategia,
                    'timestamp': now
                }
                st.session_state.log.append(f"🚀 SEÑAL GENERADA: {st.session_state.candidato['asset']} - {direccion} a las {entrada}")
                st.rerun()
            else:
                time.sleep(5)
                st.rerun()
        else:
            # No hay candidato, buscamos uno
            # Tomamos un grupo de activos (por ejemplo, de 10 en 10)
            total_activos = st.session_state.activos_a_analizar
            if not total_activos:
                st.warning("No hay activos en la lista.")
                time.sleep(pausa_entre_rondas)
                st.rerun()

            # Dividir en rondas de 10
            inicio = st.session_state.indice_ronda * 10
            fin = inicio + 10
            ronda = total_activos[inicio:fin]
            if not ronda:
                # Reiniciar rondas
                st.session_state.indice_ronda = 0
                ronda = total_activos[:10]

            st.session_state.log.append(f"Analizando ronda {st.session_state.indice_ronda + 1} ({len(ronda)} activos)...")
            candidato = buscar_candidato(st.session_state.api, ronda)
            if candidato:
                st.session_state.candidato = candidato
                st.session_state.alerta = f"🔔 Candidato seleccionado: {candidato['asset']} ({candidato['tipo']}, dirección {candidato['direccion']}). Esperando confirmación..."
                st.session_state.tiempo_inicio_espera = datetime.now(ecuador)
                st.session_state.log.append(f"✅ Candidato: {candidato['asset']} - {candidato['tipo']} - {candidato['direccion']}")
            else:
                st.session_state.log.append("⚠️ No se encontraron activos con condiciones base.")

            st.session_state.indice_ronda += 1
            time.sleep(pausa_entre_rondas)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
