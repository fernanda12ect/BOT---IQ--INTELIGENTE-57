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
    page_title="NEUROTRADER - SEGUIMIENTO CONTINUO",
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
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None  # dict con info del activo
if 'ultima_senal' not in st.session_state:
    st.session_state.ultima_senal = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'proxima_evaluacion' not in st.session_state:
    st.session_state.proxima_evaluacion = None

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
    st.session_state.activo_actual = None

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
    min_votos = st.slider("Mínimo de estrategias para seleccionar", 1, 5, 2, 1,
                          help="El activo debe tener al menos este número de estrategias en la misma dirección")
    umbral_fuerza = st.slider("Umbral de fuerza para mantener activo", 0, 100, 50, 5,
                              help="Si la fuerza (promedio de pesos) baja de este valor, se busca otro activo")
    anticipacion = st.slider("Anticipación de señal (segundos)", 0, 30, 20, 5,
                             help="Tiempo antes del cierre de la vela para mostrar la señal")

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar el primer activo
                with st.spinner("Buscando el mejor activo..."):
                    activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                    mejor = seleccionar_mejor_activo(st.session_state.api, activos, min_votos)
                    if mejor:
                        st.session_state.activo_actual = mejor
                        st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']} (votos CALL/PUT: {mejor['votos_call']}/{mejor['votos_put']}, fuerza {mejor['fuerza']:.1f})")
                        # Calcular próxima evaluación (cada 5 minutos, sincronizado con el cierre de vela)
                        now = datetime.now(ecuador)
                        # Próximo cierre de vela de 5 minutos (redondear hacia arriba)
                        minutos = now.minute
                        resto = minutos % 5
                        if resto == 0:
                            # Estamos justo en el cierre, esperar 5 minutos
                            prox = now + timedelta(minutes=5)
                        else:
                            prox = now + timedelta(minutes=(5 - resto))
                        prox = prox.replace(second=0, microsecond=0)
                        st.session_state.proxima_evaluacion = prox
                        st.session_state.log.append(f"⏳ Próxima evaluación en {prox.strftime('%H:%M:%S')}")
                    else:
                        st.session_state.log.append("⚠️ No se encontró ningún activo con suficientes estrategias.")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        if st.session_state.activo_actual:
            st.metric("Activo actual", st.session_state.activo_actual['asset'])
        else:
            st.metric("Activo actual", "Ninguno")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))

    # Información del activo actual
    if st.session_state.activo_actual:
        a = st.session_state.activo_actual
        st.markdown(f"""
        <div class="asset-box">
            <strong>🎯 ACTIVO EN SEGUIMIENTO:</strong> {a['asset']}<br>
            <strong>Dirección:</strong> {'🔵 COMPRA' if a['direccion'] == 'CALL' else '🔴 VENTA'}<br>
            <strong>Votos CALL/PUT:</strong> {a['votos_call']} / {a['votos_put']}<br>
            <strong>Fuerza:</strong> {a['fuerza']:.1f}<br>
            <strong>Estrategias:</strong> {', '.join(a['estrategias'][:5])}{'...' if len(a['estrategias'])>5 else ''}
        </div>
        """, unsafe_allow_html=True)

    # Señal generada
    if st.session_state.ultima_senal:
        s = st.session_state.ultima_senal
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA' if s['direccion'] == 'CALL' else '🔴 VENTA'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {s['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {s['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {s['vencimiento']} (5 min)</div>
            <div class="signal-detail"><strong>Votos:</strong> CALL {s['votos_call']} / PUT {s['votos_put']}</div>
            <div class="signal-detail"><strong>Fuerza:</strong> {s['fuerza']:.1f}</div>
        </div>
        """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando and st.session_state.activo_actual:
        now = datetime.now(ecuador)

        # Si hay próxima evaluación y ya es hora
        if st.session_state.proxima_evaluacion and now >= st.session_state.proxima_evaluacion:
            # Evaluar el activo actual
            res = evaluar_activo(st.session_state.api, st.session_state.activo_actual['asset'])
            if res:
                # Actualizar datos
                st.session_state.activo_actual = res
                # Verificar si sigue siendo rentable
                if res['fuerza'] >= umbral_fuerza and (res['votos_call'] + res['votos_put']) >= min_votos:
                    # Generar señal para la próxima vela
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    vencimiento = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                    st.session_state.ultima_senal = {
                        'asset': res['asset'],
                        'direccion': res['direccion'],
                        'entrada': entrada_str,
                        'vencimiento': vencimiento,
                        'votos_call': res['votos_call'],
                        'votos_put': res['votos_put'],
                        'fuerza': res['fuerza']
                    }
                    st.session_state.log.append(f"🚀 SEÑAL GENERADA: {res['asset']} - {res['direccion']} a las {entrada_str}")
                else:
                    # El activo perdió fuerza, buscar otro
                    st.session_state.log.append(f"⚠️ {res['asset']} perdió fuerza (fuerza {res['fuerza']:.1f}). Buscando otro...")
                    activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                    mejor = seleccionar_mejor_activo(st.session_state.api, activos, min_votos)
                    if mejor:
                        st.session_state.activo_actual = mejor
                        st.session_state.log.append(f"✅ Nuevo activo seleccionado: {mejor['asset']}")
                    else:
                        st.session_state.activo_actual = None
                        st.session_state.log.append("⚠️ No se encontró ningún activo.")
            else:
                # Error al evaluar, descartar activo
                st.session_state.log.append(f"❌ Error evaluando {st.session_state.activo_actual['asset']}. Buscando otro...")
                activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                mejor = seleccionar_mejor_activo(st.session_state.api, activos, min_votos)
                if mejor:
                    st.session_state.activo_actual = mejor
                    st.session_state.log.append(f"✅ Nuevo activo seleccionado: {mejor['asset']}")
                else:
                    st.session_state.activo_actual = None

            # Calcular próxima evaluación (siguiente vela de 5 minutos)
            prox = now + timedelta(minutes=5)
            prox = prox.replace(second=0, microsecond=0)
            st.session_state.proxima_evaluacion = prox
            st.session_state.log.append(f"⏳ Próxima evaluación en {prox.strftime('%H:%M:%S')}")
            time.sleep(1)
            st.rerun()
        else:
            # Esperar hasta la próxima evaluación
            if st.session_state.proxima_evaluacion:
                segundos_restantes = (st.session_state.proxima_evaluacion - now).total_seconds()
                if segundos_restantes > 0:
                    st.info(f"⏳ Próxima evaluación en {int(segundos_restantes)} segundos...")
                    time.sleep(1)
                    st.rerun()
                else:
                    # Ya pasó la hora, forzar reevaluación
                    st.rerun()
            else:
                # Si no hay próxima evaluación, calcularla
                prox = now + timedelta(minutes=5)
                prox = prox.replace(second=0, microsecond=0)
                st.session_state.proxima_evaluacion = prox
                st.rerun()
    elif st.session_state.monitoreando and not st.session_state.activo_actual:
        # No hay activo, intentar seleccionar uno
        with st.spinner("Buscando el mejor activo..."):
            activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
            mejor = seleccionar_mejor_activo(st.session_state.api, activos, min_votos)
            if mejor:
                st.session_state.activo_actual = mejor
                st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']}")
                now = datetime.now(ecuador)
                prox = now + timedelta(minutes=5)
                prox = prox.replace(second=0, microsecond=0)
                st.session_state.proxima_evaluacion = prox
            else:
                st.session_state.log.append("⚠️ No se encontró ningún activo con suficientes estrategias.")
        time.sleep(5)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
