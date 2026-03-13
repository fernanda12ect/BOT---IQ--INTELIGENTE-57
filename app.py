import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    buscar_mejor_senal,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER PRO - OFERTA/DEMANDA",
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
if 'operacion_en_curso' not in st.session_state:
    st.session_state.operacion_en_curso = False
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'proxima_entrada' not in st.session_state:
    st.session_state.proxima_entrada = None
if 'alertas' not in st.session_state:
    st.session_state.alertas = []
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
            # Obtener activos una vez conectado
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
    st.session_state.operacion_en_curso = False

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER PRO")
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
    tamanio_ronda = st.slider("Activos por ronda", 10, 50, 20, 5)
    pausa_rondas = st.slider("Pausa entre rondas (seg)", 5, 30, 10, 5)
    anticipacion = st.slider("Anticipación de señal (seg)", 5, 30, 20, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.operacion_en_curso = False
                st.session_state.senal_actual = None
                st.session_state.alertas = []
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
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        if st.session_state.operacion_en_curso:
            st.metric("Operación en curso", "SÍ")
        else:
            st.metric("Operación en curso", "NO")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))
    with col4:
        st.metric("Alertas activas", len(st.session_state.alertas))

    # Mostrar alertas anticipadas
    if st.session_state.alertas:
        with st.expander("🔔 Alertas anticipadas", expanded=True):
            for alerta in st.session_state.alertas[-5:]:
                st.markdown(f'<div class="alert-card">{alerta}</div>', unsafe_allow_html=True)

    # Mostrar señal actual si existe
    if st.session_state.senal_actual:
        s = st.session_state.senal_actual
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        zona = s['zona']
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if s['direccion'] == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {s['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {s['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {s['vencimiento']} min</div>
            <div class="signal-detail"><strong>Zona {zona['tipo'].upper()}:</strong> {zona['precio_min']:.5f} - {zona['precio_max']:.5f}</div>
            <div class="signal-detail"><strong>Confirmación:</strong> {s['tipo_vela'] if s['confirmacion'] else 'Zona fuerte'}</div>
            <div class="signal-detail"><strong>Fuerza consenso:</strong> {s['fuerza']:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.proxima_entrada:
            now = datetime.now(ecuador)
            segundos_restantes = (st.session_state.proxima_entrada - now).total_seconds()
            if segundos_restantes > 0:
                st.info(f"⏳ Próxima entrada en {int(segundos_restantes)} segundos...")
            else:
                st.success("✅ Momento de entrada alcanzado")
    else:
        st.info("No hay señal activa en este momento.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # =========================
    # LÓGICA PRINCIPAL
    # =========================
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si hay una operación en curso, esperar a que termine
        if st.session_state.operacion_en_curso:
            if st.session_state.proxima_entrada:
                # La operación debería haberse ejecutado en el momento de entrada
                # Calculamos el vencimiento real (entrada + minutos de vencimiento)
                vencimiento_real = st.session_state.proxima_entrada + timedelta(minutes=st.session_state.senal_actual['vencimiento'])
                if now >= vencimiento_real:
                    # Operación finalizada
                    st.session_state.operacion_en_curso = False
                    st.session_state.senal_actual = None
                    st.session_state.proxima_entrada = None
                    st.session_state.log.append("✅ Operación finalizada. Buscando nueva señal...")
                    time.sleep(2)
                    st.rerun()
                else:
                    # Aún en curso, mostrar tiempo restante
                    segundos_restantes = (vencimiento_real - now).total_seconds()
                    st.info(f"⏳ Operación en curso. Vence en {int(segundos_restantes)} segundos.")
                    time.sleep(5)
                    st.rerun()
            else:
                # Error, reiniciamos
                st.session_state.operacion_en_curso = False
                st.rerun()
        else:
            # No hay operación, buscamos señales
            # Actualizar lista de activos según mercado
            activos_totales = st.session_state.activos_totales
            if not activos_totales:
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                activos_totales = st.session_state.activos_totales
                if not activos_totales:
                    st.warning("No hay activos disponibles")
                    time.sleep(pausa_rondas)
                    st.rerun()

            # Dividir en rondas
            inicio = st.session_state.indice_ronda * tamanio_ronda
            fin = inicio + tamanio_ronda
            ronda_actual = activos_totales[inicio:fin]

            if not ronda_actual:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"Analizando ronda {st.session_state.indice_ronda + 1} ({len(ronda_actual)} activos)...")
            mejor = buscar_mejor_senal(st.session_state.api, ronda_actual)

            if mejor:
                # Verificar si está cerca de la zona para alerta anticipada
                if mejor['distancia'] > 1.5:
                    # Lejos, solo registrar
                    st.session_state.log.append(f"🔍 {mejor['asset']} - {mejor['direccion']} (zona a {mejor['distancia']:.1f} ATR)")
                elif mejor['distancia'] <= 1.5 and not mejor['confirmacion']:
                    # Cerca pero sin confirmación, generar alerta
                    alerta = f"🔔 {mejor['asset']} se acerca a zona de {mejor['zona']['tipo']}. Esperando vela de confirmación."
                    if alerta not in st.session_state.alertas:
                        st.session_state.alertas.append(alerta)
                        st.session_state.log.append(alerta)
                elif mejor['confirmacion']:
                    # Señal lista, generar entrada
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    mejor['entrada'] = entrada_str
                    st.session_state.senal_actual = mejor
                    st.session_state.proxima_entrada = entrada
                    st.session_state.operacion_en_curso = True
                    st.session_state.log.append(f"🚀 SEÑAL GENERADA: {mejor['asset']} - {mejor['direccion']} a las {entrada_str} (vencimiento {mejor['vencimiento']} min)")
                    # Limpiar alertas de este activo
                    st.session_state.alertas = [a for a in st.session_state.alertas if mejor['asset'] not in a]
                    st.rerun()
                else:
                    st.session_state.log.append(f"⏭️ {mejor['asset']} - cerca pero sin confirmación")
            else:
                st.session_state.log.append("⚠️ No se encontraron señales en esta ronda.")

            # Avanzar a la siguiente ronda
            st.session_state.indice_ronda += 1
            time.sleep(pausa_rondas)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
