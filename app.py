import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo_principal,
    seleccionar_mejor_activo,
    calcular_indicadores
)

# Configuración de página
st.set_page_config(
    page_title="NEUROTRADER PRO",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
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
    .signal-title { font-size: 1.5rem; font-weight: bold; margin-bottom: 10px; }
    .signal-detail { font-size: 1rem; color: #ccc; margin: 5px 0; }
    .signal-time { color: #888; font-size: 0.9rem; }
    hr { border-color: #2a2f3a; }
    .selected-asset-box {
        background-color: #1a2a3a;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        border-left: 4px solid #00a3ff;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar variables de sesión
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
    st.session_state.activo_actual = None  # activo que estamos siguiendo
if 'direccion_actual' not in st.session_state:
    st.session_state.direccion_actual = None  # CALL/PUT
if 'fuerza_actual' not in st.session_state:
    st.session_state.fuerza_actual = 0
if 'estado' not in st.session_state:
    st.session_state.estado = "ESPERANDO"  # ESPERANDO, LISTO, OPERACION_EN_CURSO
if 'hora_entrada' not in st.session_state:
    st.session_state.hora_entrada = None
if 'hora_vencimiento' not in st.session_state:
    st.session_state.hora_vencimiento = None
if 'señales' not in st.session_state:
    st.session_state.señales = []  # historial de señales
if 'log' not in st.session_state:
    st.session_state.log = []
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = None

# Zona horaria
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# FUNCIONES AUXILIARES
# =========================
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
            st.error(f"Error de conexión: {reason}")
            return False
    except Exception as e:
        st.error(f"Excepción: {e}")
        return False

def desconectar():
    st.session_state.api = None
    st.session_state.conectado = False
    st.session_state.monitoreando = False
    st.session_state.log.append("🔌 Desconectado")

def obtener_activos():
    if not st.session_state.api:
        return []
    try:
        open_time = st.session_state.api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    activos.append(asset)
        return activos
    except:
        return []

def crear_grafico_velas(df, activo):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df.index,
                                  open=df['open'],
                                  high=df['high'],
                                  low=df['low'],
                                  close=df['close'],
                                  name='Precio',
                                  increasing_line_color='#00ff88',
                                  decreasing_line_color='#ff4b4b'),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema9'], line=dict(color='#ffaa00', width=1), name='EMA9'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema21'], line=dict(color='#00a3ff', width=1), name='EMA21'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='#aa88ff', width=1), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ff4b4b", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00ff88", row=2, col=1)
    fig.update_layout(title=f"{activo} - Análisis en tiempo real",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=500)
    return fig

# =========================
# BARRA LATERAL
# =========================
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER PRO")
    st.markdown("---")

    st.markdown("### 🔌 Conexión IQ Option")
    email = st.text_input("Correo electrónico", placeholder="tu@email.com")
    password = st.text_input("Contraseña", type="password", placeholder="********")

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

    st.markdown("### 💳 Tipo de cuenta")
    # Corregido: agregamos un label no vacío
    tipo_cuenta = st.radio("Selecciona tipo de cuenta", ["PRACTICE", "REAL"], index=0, horizontal=True, label_visibility="collapsed")
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        saldo = st.session_state.api.get_balance()
        st.session_state.saldo = saldo if saldo is not None else 0.0
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    st.markdown("---")

    st.markdown("### ⚙️ Control")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar el mejor activo al inicio
                with st.spinner("Seleccionando el activo más confiable..."):
                    activos = obtener_activos()
                    if activos:
                        mejor_asset, direccion, fuerza = seleccionar_mejor_activo(st.session_state.api, activos)
                        if mejor_asset:
                            st.session_state.activo_actual = mejor_asset
                            st.session_state.direccion_actual = direccion
                            st.session_state.fuerza_actual = fuerza
                            st.session_state.estado = "ESPERANDO"
                            st.session_state.log.append(f"✅ Activo seleccionado: {mejor_asset} ({direccion}) con fuerza {fuerza:.1f}")
                        else:
                            st.session_state.log.append("⚠️ No se encontró ningún activo confiable.")
                    else:
                        st.session_state.log.append("⚠️ No hay activos disponibles.")
                st.rerun()
        else:
            if st.button("⏹️ DETENER MONITOREO", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.session_state.activo_actual = None
                st.session_state.estado = "ESPERANDO"
                st.session_state.log.append("🛑 Monitoreo detenido")
                st.rerun()

    if st.session_state.conectado:
        st.markdown("---")
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")

# =========================
# ÁREA PRINCIPAL
# =========================
if st.session_state.conectado:
    # Cabecera con métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activo en seguimiento", st.session_state.activo_actual or "Ninguno")
    with col3:
        st.metric("Estado", st.session_state.estado)

    # Mostrar información del activo actual
    if st.session_state.activo_actual:
        st.markdown(f"""
        <div class="selected-asset-box">
            <strong>📌 ACTIVO PRINCIPAL:</strong> {st.session_state.activo_actual} | 
            <strong>DIRECCIÓN:</strong> {st.session_state.direccion_actual} | 
            <strong>FUERZA:</strong> {st.session_state.fuerza_actual:.1f} | 
            <strong>ESTADO:</strong> {st.session_state.estado}
        </div>
        """, unsafe_allow_html=True)

    # Gráfico del activo actual
    if st.session_state.datos_grafico is not None and st.session_state.activo_actual:
        fig = crear_grafico_velas(st.session_state.datos_grafico, st.session_state.activo_actual)
        st.plotly_chart(fig, use_container_width=True)

    # TARJETA DE SEÑAL PRINCIPAL (solo cuando hay una señal activa)
    if st.session_state.estado == "LISTO" and st.session_state.hora_entrada:
        card_class = "call-card" if st.session_state.direccion_actual == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if st.session_state.direccion_actual == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {st.session_state.activo_actual}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {st.session_state.hora_entrada}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {st.session_state.hora_vencimiento} (5 minutos)</div>
            <div class="signal-detail"><strong>Estrategia:</strong> Tendencia confirmada con EMA</div>
            <div class="signal-time">✅ LISTO PARA OPERAR</div>
        </div>
        """, unsafe_allow_html=True)
    elif st.session_state.estado == "OPERACION_EN_CURSO" and st.session_state.hora_entrada:
        # Mostrar tiempo restante
        now = datetime.now(ecuador)
        vencimiento = datetime.strptime(st.session_state.hora_vencimiento, "%H:%M:%S").time()
        vencimiento_dt = datetime.combine(now.date(), vencimiento)
        if vencimiento_dt < now:
            vencimiento_dt += timedelta(days=1)
        resto = (vencimiento_dt - now).total_seconds()
        mins, segs = divmod(int(resto), 60)
        st.markdown(f"""
        <div class="signal-card waiting-card">
            <div class="signal-title">⏳ OPERACIÓN EN CURSO</div>
            <div class="signal-detail"><strong>Activo:</strong> {st.session_state.activo_actual}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {st.session_state.hora_entrada}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {st.session_state.hora_vencimiento}</div>
            <div class="signal-detail"><strong>Tiempo restante:</strong> {mins:02d}:{segs:02d}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa en este momento.")

    # Historial de señales (últimas)
    with st.expander("📋 Historial de señales", expanded=True):
        if st.session_state.señales:
            df_hist = pd.DataFrame(st.session_state.señales)
            st.dataframe(df_hist[['fecha', 'activo', 'direccion', 'entrada', 'vencimiento']],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No hay señales en el historial.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA DE MONITOREO
    # =========================
    if st.session_state.monitoreando and st.session_state.activo_actual:
        now = datetime.now(ecuador)

        # Si estamos en OPERACION_EN_CURSO, esperar a que venza
        if st.session_state.estado == "OPERACION_EN_CURSO":
            vencimiento = datetime.strptime(st.session_state.hora_vencimiento, "%H:%M:%S").time()
            vencimiento_dt = datetime.combine(now.date(), vencimiento)
            if vencimiento_dt < now:
                vencimiento_dt += timedelta(days=1)
            if now >= vencimiento_dt:
                # Operación vencida, volver a ESPERANDO y buscar nuevo activo?
                st.session_state.estado = "ESPERANDO"
                st.session_state.hora_entrada = None
                st.session_state.hora_vencimiento = None
                st.session_state.log.append("✅ Operación finalizada. Buscando nuevo activo...")
                # Buscar nuevo activo
                activos = obtener_activos()
                if activos:
                    mejor, direc, fuerza = seleccionar_mejor_activo(st.session_state.api, activos)
                    if mejor:
                        st.session_state.activo_actual = mejor
                        st.session_state.direccion_actual = direc
                        st.session_state.fuerza_actual = fuerza
                        st.session_state.log.append(f"🔄 Nuevo activo seleccionado: {mejor} ({direc})")
                    else:
                        st.session_state.activo_actual = None
                time.sleep(2)
                st.rerun()
            else:
                # Aún no vence, esperar
                time.sleep(1)
                st.rerun()
        else:
            # Estamos en ESPERANDO o LISTO (pero LISTO solo dura un ciclo)
            # Evaluar el activo actual
            direccion, fuerza, lista_para_entrar, estrategia, precio = evaluar_activo_principal(
                st.session_state.api, st.session_state.activo_actual, check_agotamiento=True
            )
            if direccion is None:
                # El activo perdió la tendencia, buscar otro
                st.session_state.log.append(f"⚠️ {st.session_state.activo_actual} perdió tendencia. Buscando reemplazo...")
                activos = obtener_activos()
                mejor, direc, fuerza = seleccionar_mejor_activo(st.session_state.api, activos)
                if mejor:
                    st.session_state.activo_actual = mejor
                    st.session_state.direccion_actual = direc
                    st.session_state.fuerza_actual = fuerza
                    st.session_state.estado = "ESPERANDO"
                    st.session_state.log.append(f"🔄 Nuevo activo seleccionado: {mejor} ({direc})")
                else:
                    st.session_state.activo_actual = None
                    st.session_state.estado = "ESPERANDO"
                time.sleep(2)
                st.rerun()
            else:
                # Actualizar fuerza y dirección
                st.session_state.direccion_actual = direccion
                st.session_state.fuerza_actual = fuerza

                if lista_para_entrar and st.session_state.estado != "LISTO":
                    # Generar señal
                    hora_entrada = now.strftime("%H:%M:%S")
                    hora_venc = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
                    st.session_state.hora_entrada = hora_entrada
                    st.session_state.hora_vencimiento = hora_venc
                    st.session_state.estado = "LISTO"
                    # Añadir al historial
                    st.session_state.señales.insert(0, {
                        'fecha': now.strftime("%Y-%m-%d %H:%M:%S"),
                        'activo': st.session_state.activo_actual,
                        'direccion': direccion,
                        'entrada': hora_entrada,
                        'vencimiento': hora_venc,
                        'estrategia': estrategia
                    })
                    st.session_state.log.append(f"📢 SEÑAL GENERADA: {st.session_state.activo_actual} - {direccion} a las {hora_entrada}")
                    time.sleep(1)
                    st.rerun()
                else:
                    # No hay señal, esperar y seguir analizando
                    time.sleep(5)
                    st.rerun()
    elif st.session_state.monitoreando and not st.session_state.activo_actual:
        # No hay activo, intentar seleccionar uno
        activos = obtener_activos()
        if activos:
            mejor, direc, fuerza = seleccionar_mejor_activo(st.session_state.api, activos)
            if mejor:
                st.session_state.activo_actual = mejor
                st.session_state.direccion_actual = direc
                st.session_state.fuerza_actual = fuerza
                st.session_state.estado = "ESPERANDO"
                st.session_state.log.append(f"✅ Activo seleccionado: {mejor} ({direc})")
            else:
                st.session_state.log.append("⚠️ No se encontró activo confiable.")
        time.sleep(5)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
