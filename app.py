import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    buscar_senales,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER - 3 ESTRATEGIAS",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (mantenemos los mismos)
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
    .alert-card {
        background-color: #2a2a1e;
        border-left: 4px solid #ffaa00;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
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
if 'señales_emitidas' not in st.session_state:
    st.session_state.señales_emitidas = []  # historial de señales emitidas
if 'ultima_entrada' not in st.session_state:
    st.session_state.ultima_entrada = None  # momento de la última entrada
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

# Sidebar
with st.sidebar:
    st.markdown("## 🎯 NEUROTRADER")
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
    activos_por_ciclo = st.slider("Activos por ciclo", 10, 30, 20, 5)
    pausa_ciclo = st.slider("Pausa entre ciclos (seg)", 60, 180, 90, 10, help="1.5 - 3 minutos")
    anticipacion = st.slider("Anticipación de señal (seg)", 5, 30, 15, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.indice_ronda = 0
                st.session_state.señales_emitidas = []
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
    st.title("🎯 Señales de Trading - 3 Estrategias")

    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Señales emitidas", len(st.session_state.señales_emitidas))
    with col3:
        if st.session_state.ultima_entrada:
            tiempo_restante = max(0, (st.session_state.ultima_entrada + timedelta(minutes=5) - datetime.now(ecuador)).total_seconds())
            st.metric("Próximo análisis", f"{int(tiempo_restante)}s" if tiempo_restante > 0 else "Ahora")
        else:
            st.metric("Próximo análisis", "Inmediato")

    # Mostrar últimas señales emitidas
    if st.session_state.señales_emitidas:
        st.subheader("📊 Señales activas (más recientes primero)")
        for señal in st.session_state.señales_emitidas[-5:][::-1]:
            card_class = "call-card" if señal['direccion'] == "CALL" else "put-card"
            st.markdown(f"""
            <div class="signal-card {card_class}">
                <div class="asset-title">[{señal['hora']}] {señal['asset']}</div>
                <div><strong>{señal['direccion']}</strong> - {señal['estrategias']}</div>
                <div class="signal-detail">Entrada: {señal['entrada']} | Vencimiento: 5 min</div>
                <div class="signal-detail">Fuerza: {señal['fuerza']}%</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No hay señales emitidas aún.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Verificar si podemos analizar (si no hay operación reciente o ya pasaron 5 min)
        if st.session_state.ultima_entrada is None or now >= st.session_state.ultima_entrada + timedelta(minutes=5):
            # Podemos analizar
            activos = st.session_state.activos_totales
            if not activos:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_ciclo)
                st.rerun()

            # Dividir en ciclos
            inicio = st.session_state.indice_ronda * activos_por_ciclo
            fin = inicio + activos_por_ciclo
            lote = activos[inicio:fin]

            if not lote:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"🔄 Analizando lote {st.session_state.indice_ronda + 1} ({len(lote)} activos)...")
            señales = buscar_senales(st.session_state.api, lote, max_activos=activos_por_ciclo)

            if señales:
                # Tomamos la mejor señal (la primera, ya ordenada por fuerza)
                mejor = señales[0]
                entrada = now + timedelta(seconds=anticipacion)
                entrada_str = entrada.strftime("%H:%M:%S")
                hora_actual = now.strftime("%H:%M:%S")
                st.session_state.señales_emitidas.append({
                    'hora': hora_actual,
                    'asset': mejor['asset'],
                    'direccion': mejor['direccion'],
                    'estrategias': ', '.join(mejor['estrategias']),
                    'entrada': entrada_str,
                    'fuerza': mejor['fuerza']
                })
                st.session_state.ultima_entrada = entrada
                st.session_state.log.append(f"🚀 SEÑAL: {mejor['asset']} - {mejor['direccion']} a las {entrada_str} (Estrategias: {', '.join(mejor['estrategias'])})")
            else:
                st.session_state.log.append("🔍 No se encontraron señales en este lote.")

            # Pasar al siguiente lote
            st.session_state.indice_ronda += 1
            time.sleep(pausa_ciclo)
            st.rerun()
        else:
            # Esperar a que termine la operación actual
            tiempo_restante = (st.session_state.ultima_entrada + timedelta(minutes=5) - now).total_seconds()
            if tiempo_restante > 0:
                st.info(f"⏳ Esperando {int(tiempo_restante)} segundos para el próximo análisis...")
                time.sleep(1)
                st.rerun()
            else:
                # Ya pasó el tiempo, reiniciamos el ciclo
                st.session_state.ultima_entrada = None
                st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
