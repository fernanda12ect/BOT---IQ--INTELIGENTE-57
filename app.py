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
    page_title="NEUROTRADER PRO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS profesionales (3D cards)
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
    .asset-card {
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
    .asset-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 25px 40px -12px rgba(0,0,0,0.6);
        border-color: #00a3ff;
    }
    .asset-name {
        font-size: 1.4rem;
        font-weight: bold;
        margin-bottom: 10px;
        color: #fff;
        text-shadow: 0 2px 5px rgba(0,0,0,0.3);
    }
    .asset-status {
        font-size: 0.9rem;
        padding: 4px 12px;
        border-radius: 20px;
        display: inline-block;
        background: rgba(0,0,0,0.5);
        margin-bottom: 15px;
    }
    .signal-call {
        border-left: 5px solid #00ff88;
        background: linear-gradient(90deg, rgba(0,255,136,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .signal-put {
        border-left: 5px solid #ff4b4b;
        background: linear-gradient(90deg, rgba(255,75,75,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .signal-neutral {
        border-left: 5px solid #ffaa00;
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
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None  # dict con la señal activa
if 'senal_activa' not in st.session_state:
    st.session_state.senal_activa = None
if 'ultima_entrada' not in st.session_state:
    st.session_state.ultima_entrada = None  # datetime de la última entrada
if 'log' not in st.session_state:
    st.session_state.log = []
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0

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
    st.markdown("## 📈 NEUROTRADER PRO")
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
    umbral_fuerza = st.slider("Fuerza mínima para señal (%)", 0, 100, 50, 5)
    pausa_entre_ciclos = st.slider("Pausa entre ciclos (seg)", 30, 120, 60, 10)
    anticipacion = st.slider("Anticipación de señal (seg)", 5, 30, 15, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if st.session_state.activos_totales:
            otc_count = sum(1 for a in st.session_state.activos_totales if '-OTC' in a)
            real_count = len(st.session_state.activos_totales) - otc_count
            st.info(f"📊 Activos disponibles: OTC={otc_count} | REAL={real_count}")
        else:
            st.info("📊 Conectando...")

        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Obtener lista de activos
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                st.session_state.log.append(f"📊 Total activos disponibles: {len(st.session_state.activos_totales)}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("📊 Sistema de Trading con 8 Estrategias")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Señales activas", "1" if st.session_state.senal_activa else "0")
    with col3:
        st.metric("Estrategias activas", len(ESTRATEGIAS))

    # Mostrar señal actual si existe
    if st.session_state.senal_activa:
        s = st.session_state.senal_activa
        card_class = "signal-call" if s['direccion'] == "CALL" else "signal-put"
        st.markdown(f"""
        <div class="asset-card {card_class}">
            <div class="asset-name">{s['asset']}</div>
            <div class="asset-status">✅ SEÑAL ACTIVA</div>
            <div><strong>{s['direccion']}</strong> - Consenso de {len(s['estrategias'])} estrategias</div>
            <div>Fuerza: {s['fuerza']:.1f}%</div>
            <div class="force-bar"><div class="force-fill" style="width: {s['fuerza']}%;"></div></div>
            <div class="entry-time">⏱️ Entrada: {s['entrada']}</div>
            <div class="entry-time">⏰ Vencimiento: {s['vencimiento']}</div>
            <div><small>Estrategias: {', '.join(s['estrategias'][:3])}{'...' if len(s['estrategias'])>3 else ''}</small></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa. Esperando condiciones...")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si hay señal activa, esperar a que venza (5 min después de entrada)
        if st.session_state.senal_activa:
            entrada_dt = datetime.strptime(st.session_state.senal_activa['entrada'], "%H:%M:%S").time()
            entrada_completa = datetime.combine(now.date(), entrada_dt)
            if entrada_completa < now:
                entrada_completa += timedelta(days=1)
            if now >= entrada_completa + timedelta(minutes=5):
                st.session_state.senal_activa = None
                st.session_state.log.append("🗑️ Señal expirada. Buscando nueva...")
                st.rerun()
            else:
                # Mostrar tiempo restante
                seg_rest = (entrada_completa + timedelta(minutes=5) - now).total_seconds()
                st.info(f"⏳ Señal activa. Próximo análisis en {int(seg_rest)} segundos...")
                time.sleep(1)
                st.rerun()
        else:
            # Buscar la mejor señal
            if not st.session_state.activos_totales:
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
            if not st.session_state.activos_totales:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_entre_ciclos)
                st.rerun()

            # Analizar un lote de activos (por ejemplo, 20 cada vez)
            activos = st.session_state.activos_totales
            inicio = st.session_state.indice_ronda * 20
            fin = inicio + 20
            lote = activos[inicio:fin]
            if not lote:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"🔍 Analizando lote {st.session_state.indice_ronda + 1} ({len(lote)} activos)...")
            mejor = seleccionar_mejor_activo(st.session_state.api, lote)
            st.session_state.indice_ronda += 1

            if mejor and mejor['fuerza'] >= umbral_fuerza:
                entrada = now + timedelta(seconds=anticipacion)
                entrada_str = entrada.strftime("%H:%M:%S")
                vencimiento_str = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                st.session_state.senal_activa = {
                    'asset': mejor['asset'],
                    'direccion': mejor['direccion'],
                    'estrategias': mejor['estrategias'],
                    'fuerza': mejor['fuerza'],
                    'entrada': entrada_str,
                    'vencimiento': vencimiento_str
                }
                st.session_state.log.append(f"🚀 SEÑAL: {mejor['asset']} - {mejor['direccion']} a las {entrada_str} (Fuerza: {mejor['fuerza']:.1f}%)")
                st.session_state.log.append(f"   Estrategias: {', '.join(mejor['estrategias'])}")
            else:
                st.session_state.log.append("🔍 No se encontraron señales en este lote.")

            time.sleep(pausa_entre_ciclos)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
