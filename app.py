import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo_seleccion,
    evaluar_activo_seguimiento,
    seleccionar_mejor_activo,
    obtener_activos_abiertos,
    ESTRATEGIAS
)

st.set_page_config(
    page_title="NEUROTRADER PRO - 10 ESTRATEGIAS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS profesionales
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
    .countdown {
        font-size: 1.5rem;
        color: #ffaa00;
        font-weight: bold;
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
if 'alerta' not in st.session_state:
    st.session_state.alerta = None
if 'señal' not in st.session_state:
    st.session_state.señal = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []
if 'tiempo_inicio_monitoreo' not in st.session_state:
    st.session_state.tiempo_inicio_monitoreo = None

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
    st.session_state.alerta = None
    st.session_state.señal = None

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER PRO")
    st.markdown("### 10 ESTRATEGIAS INTELIGENTES")
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
    st.markdown("### ⚙️ Configuración de mercado")

    tipo_mercado = st.selectbox("Mercado", ["OTC", "REAL", "AMBOS"], index=2)
    min_estrategias = st.slider("Mínimo de estrategias para seleccionar", 1, 5, 2, 1,
                                help="El activo debe tener al menos este número de estrategias en la misma dirección")

    st.markdown("---")
    st.markdown("### ⚙️ Parámetros de entrada")

    umbral_pullback = st.slider("Umbral pullback (ATR)", 0.1, 0.5, 0.2, 0.05,
                                help="Movimiento mínimo en contra de la tendencia para considerar pullback")
    ventana_cruce = st.slider("Ventana para cruce de EMA (velas)", 1, 5, 3, 1,
                              help="Número de velas hacia atrás para buscar el cruce")
    anticipacion = st.slider("Anticipación de señal (segundos)", 0, 60, 20, 5,
                             help="Tiempo antes de la entrada para mostrar alerta")
    timeout_monitoreo = st.slider("Timeout de monitoreo (minutos)", 5, 30, 10, 1,
                                   help="Si el activo no da señal en este tiempo, se descarta")

    st.markdown("---")
    st.markdown("### ⚙️ Rendimiento")

    tamaño_ronda = st.slider("Activos por ronda", 10, 50, 20, 5)
    pausa_entre_rondas = st.slider("Pausa entre rondas (seg)", 5, 60, 15, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.indice_ronda = 0
                st.session_state.activo_seleccionado = None
                st.session_state.alerta = None
                st.session_state.señal = None
                st.session_state.tiempo_inicio_monitoreo = None
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                st.session_state.log.append(f"📊 Activos para análisis: {len(st.session_state.activos_totales)}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER MONITOREO", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        if st.session_state.activo_seleccionado:
            st.metric("📈 Activo en seguimiento", st.session_state.activo_seleccionado['asset'])
        else:
            st.metric("📈 Activo en seguimiento", "Ninguno")
    with col3:
        st.metric("🎯 Estrategias activas", len(ESTRATEGIAS))
    with col4:
        st.metric("🚦 Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))

    # Mostrar activo seleccionado si existe
    if st.session_state.activo_seleccionado:
        a = st.session_state.activo_seleccionado
        st.markdown(f"""
        <div class="asset-box">
            <strong>🎯 ACTIVO SELECCIONADO:</strong> {a['asset']}<br>
            <strong>Dirección:</strong> {'🔵 COMPRA' if a['direccion'] == 'CALL' else '🔴 VENTA'}<br>
            <strong>Votos CALL/PUT:</strong> {a['votos_call']} / {a['votos_put']}<br>
            <strong>Estrategias:</strong> {', '.join(a['estrategias'][:3])}...<br>
            <strong>Puntuación:</strong> {a['puntuacion']:.0f}
        </div>
        """, unsafe_allow_html=True)

    # Alerta previa
    if st.session_state.alerta:
        st.markdown(f'<div class="alert-card">{st.session_state.alerta}</div>', unsafe_allow_html=True)

    # Señal definitiva
    if st.session_state.señal:
        card_class = "call-card" if st.session_state.señal['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if st.session_state.señal['direccion'] == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {st.session_state.señal['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {st.session_state.señal['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {st.session_state.señal['vencimiento']} (5 min)</div>
            <div class="signal-detail"><strong>Estrategia:</strong> {st.session_state.señal['estrategia']}</div>
        </div>
        """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si ya tenemos un activo seleccionado
        if st.session_state.activo_seleccionado and isinstance(st.session_state.activo_seleccionado, dict):
            # Verificar si ya pasó el tiempo de la señal (para reiniciar después de 5 min)
            if st.session_state.señal:
                tiempo_transcurrido = (now - st.session_state.señal['timestamp']).total_seconds()
                if tiempo_transcurrido > 300:  # 5 minutos
                    st.session_state.activo_seleccionado = None
                    st.session_state.alerta = None
                    st.session_state.señal = None
                    st.session_state.tiempo_inicio_monitoreo = None
                    st.session_state.log.append("🔄 Reiniciando búsqueda...")
                    time.sleep(2)
                    st.rerun()
                else:
                    time.sleep(5)
                    st.rerun()
            else:
                # Verificar timeout de monitoreo
                if st.session_state.tiempo_inicio_monitoreo is None:
                    st.session_state.tiempo_inicio_monitoreo = now
                else:
                    tiempo_espera = (now - st.session_state.tiempo_inicio_monitoreo).total_seconds() / 60
                    if tiempo_espera > timeout_monitoreo:
                        st.session_state.log.append(f"⏰ Timeout alcanzado para {st.session_state.activo_seleccionado['asset']}. Buscando otro...")
                        st.session_state.activo_seleccionado = None
                        st.session_state.alerta = None
                        st.session_state.tiempo_inicio_monitoreo = None
                        time.sleep(2)
                        st.rerun()

                # Monitorear el activo seleccionado
                lista_para_entrar, direccion, fuerza, estrategia = evaluar_activo_seguimiento(
                    st.session_state.api,
                    st.session_state.activo_seleccionado['asset'],
                    st.session_state.activo_seleccionado['direccion'],
                    umbral_pullback=umbral_pullback,
                    ventana_cruce=ventana_cruce
                )
                if lista_para_entrar and direccion:
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    vencimiento = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                    st.session_state.señal = {
                        'asset': st.session_state.activo_seleccionado['asset'],
                        'direccion': direccion,
                        'entrada': entrada_str,
                        'vencimiento': vencimiento,
                        'estrategia': estrategia,
                        'timestamp': now
                    }
                    st.session_state.log.append(f"🚀 SEÑAL GENERADA: {st.session_state.activo_seleccionado['asset']} - {direccion} a las {entrada_str}")
                    st.rerun()
                else:
                    st.session_state.alerta = f"⏳ Esperando pullback y cruce para {st.session_state.activo_seleccionado['asset']}..."
                    time.sleep(2)
                    st.rerun()
        else:
            # No hay activo, buscar uno nuevo
            activos_totales = st.session_state.activos_totales
            if not activos_totales:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_entre_rondas)
                st.rerun()

            # Dividir en rondas
            inicio = st.session_state.indice_ronda * tamaño_ronda
            fin = inicio + tamaño_ronda
            ronda_actual = activos_totales[inicio:fin]

            if not ronda_actual:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"Analizando ronda {st.session_state.indice_ronda + 1} ({len(ronda_actual)} activos)...")
            mejor = seleccionar_mejor_activo(
                st.session_state.api,
                ronda_actual,
                min_estrategias=min_estrategias
            )

            if mejor:
                st.session_state.activo_seleccionado = mejor
                st.session_state.alerta = f"🔔 {mejor['asset']} - {mejor['direccion']} con {mejor['votos_call']+mejor['votos_put']} estrategias. Esperando pullback y cruce."
                st.session_state.tiempo_inicio_monitoreo = datetime.now(ecuador)
                st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']} ({mejor['direccion']}, fuerza {mejor['fuerza']:.1f})")
            else:
                st.session_state.log.append("⚠️ No se encontraron activos con suficientes estrategias.")

            st.session_state.indice_ronda += 1
            time.sleep(pausa_entre_rondas)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
