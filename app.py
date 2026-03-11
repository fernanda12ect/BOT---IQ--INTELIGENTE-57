import streamlit as st
import pandas as pd
import numpy as np
import time
import threading
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import evaluar_activo, ESTRATEGIAS, calcular_indicadores

# Configuración de página
st.set_page_config(
    page_title="IQ Option Bot Profesional",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .sidebar .sidebar-content {
        background: #1e1e1e;
    }
    .Widget>label {
        color: white;
    }
    .stButton>button {
        background-color: #00a3ff;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 10px 20px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #0082cc;
    }
    .success-box {
        background-color: #1e3a3a;
        border-left: 4px solid #00ff88;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .warning-box {
        background-color: #3a2e1e;
        border-left: 4px solid #ffaa00;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .info-box {
        background-color: #1e2a3a;
        border-left: 4px solid #00a3ff;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .call-box {
        background-color: #1e3a2e;
        border: 2px solid #00ff88;
        padding: 15px;
        border-radius: 10px;
    }
    .put-box {
        background-color: #3a1e1e;
        border: 2px solid #ff4b4b;
        padding: 15px;
        border-radius: 10px;
    }
    .logo-placeholder {
        font-size: 2rem;
        font-weight: bold;
        color: #00a3ff;
        text-align: center;
        padding: 20px;
        border: 2px dashed #00a3ff;
        border-radius: 10px;
        margin: 10px 0;
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
if 'operando' not in st.session_state:
    st.session_state.operando = False
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None
if 'ultima_operacion' not in st.session_state:
    st.session_state.ultima_operacion = None
if 'cooldown_hasta' not in st.session_state:
    st.session_state.cooldown_hasta = None
if 'historial_ops' not in st.session_state:
    st.session_state.historial_ops = []
if 'log' not in st.session_state:
    st.session_state.log = []
if 'estrategias_activas' not in st.session_state:
    st.session_state.estrategias_activas = [nombre for nombre, _ in ESTRATEGIAS[:5]]  # primeras 5 por defecto
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = None  # para almacenar último DataFrame del activo analizado

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
            perfil = api.get_profile()
            st.session_state.saldo = perfil.get('balance', 0)
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
    st.session_state.operando = False
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

def ejecutar_operacion(activo, direccion, monto):
    if not st.session_state.api:
        return False
    try:
        # Validar saldo suficiente
        if monto > st.session_state.saldo:
            st.session_state.log.append(f"❌ Saldo insuficiente: ${st.session_state.saldo} < ${monto}")
            return False

        accion = "call" if direccion == "CALL" else "put"
        expiracion = int(time.time()) + 300  # 5 minutos
        resultado = st.session_state.api.buy(monto, activo, accion, expiracion)
        if resultado:
            # Actualizar saldo (aproximado, la API no devuelve el nuevo saldo inmediatamente)
            st.session_state.saldo -= monto
            st.session_state.log.append(f"💰 Operación ejecutada: {activo} {direccion} ${monto}")
            return True
        else:
            st.session_state.log.append(f"❌ Error al ejecutar operación")
            return False
    except Exception as e:
        st.session_state.log.append(f"⚠️ Excepción en operación: {e}")
        return False

def crear_grafico_velas(df, activo):
    """Crea gráfico de velas con EMAs y Bandas de Bollinger usando Plotly"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03,
                        row_heights=[0.7, 0.3])

    # Gráfico de velas
    fig.add_trace(go.Candlestick(x=df.index,
                                  open=df['open'],
                                  high=df['high'],
                                  low=df['low'],
                                  close=df['close'],
                                  name='Velas'),
                  row=1, col=1)

    # EMAs
    fig.add_trace(go.Scatter(x=df.index, y=df['ema9'], line=dict(color='orange', width=1), name='EMA9'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema21'], line=dict(color='blue', width=1), name='EMA21'), row=1, col=1)

    # Bandas de Bollinger
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], line=dict(color='gray', width=1, dash='dash'), name='BB Superior'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], line=dict(color='gray', width=1, dash='dash'), name='BB Inferior'), row=1, col=1)

    # RSI en subplot inferior
    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='purple', width=1), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(title=f"Análisis de {activo} - Últimas 50 velas M5",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=600)
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="RSI", row=2, col=1)

    return fig

# =========================
# INTERFAZ DE USUARIO
# =========================
st.title("🤖 IQ Option Bot Profesional - 10 Estrategias")

# Logo placeholder
st.markdown('<div class="logo-placeholder">LOGO AQUÍ</div>', unsafe_allow_html=True)

# Barra lateral
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email", placeholder="tu@email.com")
    password = st.text_input("🔑 Password", type="password", placeholder="********")

    st.divider()

    # Selector de cuenta
    tipo_cuenta = st.radio("💰 Tipo de cuenta", ["PRACTICE", "REAL"], index=0)
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        # Actualizar saldo
        perfil = st.session_state.api.get_profile()
        st.session_state.saldo = perfil.get('balance', 0)
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    # Monto por operación
    monto_operacion = st.number_input("💵 Monto por operación ($)", min_value=1.0, max_value=1000.0, value=10.0, step=1.0)

    st.divider()

    # Botones de conexión
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 CONECTAR", use_container_width=True):
            if email and password:
                conectar(email, password)
            else:
                st.warning("Ingresa email y password")
    with col2:
        if st.button("⛔ DESCONECTAR", use_container_width=True):
            desconectar()

    st.divider()

    # Estrategias activas
    st.subheader("🎯 Estrategias activas")
    nuevas_estrategias = []
    for nombre, _ in ESTRATEGIAS:
        activa = st.checkbox(nombre, value=(nombre in st.session_state.estrategias_activas))
        if activa:
            nuevas_estrategias.append(nombre)
    st.session_state.estrategias_activas = nuevas_estrategias

    st.divider()

    # Botón de inicio/parada
    if st.session_state.conectado:
        if not st.session_state.operando:
            if st.button("▶️ INICIAR BOT", use_container_width=True, type="primary"):
                st.session_state.operando = True
                st.session_state.cooldown_hasta = None
                st.session_state.log.append("🚀 Bot iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER BOT", use_container_width=True, type="secondary"):
                st.session_state.operando = False
                st.session_state.log.append("🛑 Bot detenido")
                st.rerun()

    # Información de estado
    if st.session_state.conectado:
        st.divider()
        st.metric("Saldo actual", f"${st.session_state.saldo:.2f}")
        st.metric("Estrategias activas", len(st.session_state.estrategias_activas))

# Área principal
if st.session_state.conectado:
    # Panel superior: información en vivo
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info(f"📊 Cuenta: **{st.session_state.tipo_cuenta}**")
    with col2:
        st.info(f"🤖 Estado: **{'ACTIVO' if st.session_state.operando else 'DETENIDO'}**")
    with col3:
        if st.session_state.activo_actual:
            st.info(f"🔍 Analizando: **{st.session_state.activo_actual}**")
        else:
            st.info("🔍 Analizando: **Ninguno**")
    with col4:
        if st.session_state.cooldown_hasta:
            seg_rest = max(0, (st.session_state.cooldown_hasta - datetime.now(ecuador)).total_seconds())
            st.info(f"⏳ Cooldown: **{int(seg_rest)}s**")
        else:
            st.info("⏳ Cooldown: **Listo**")

    st.divider()

    # Sección de señal actual
    st.subheader("🚀 Señal actual")
    if st.session_state.ultima_operacion:
        op = st.session_state.ultima_operacion
        if op['direccion'] == 'CALL':
            with st.container():
                st.markdown(f"""
                <div class="call-box">
                    <h3 style="color:#00ff88;">🔵 COMPRA (CALL)</h3>
                    <p style="font-size:1.2rem;">Activo: {op['activo']}</p>
                    <p>Estrategia: {op['estrategia']}</p>
                    <p>Hora: {op['hora']}</p>
                    <p>Monto: ${op['monto']}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            with st.container():
                st.markdown(f"""
                <div class="put-box">
                    <h3 style="color:#ff4b4b;">🔴 VENTA (PUT)</h3>
                    <p style="font-size:1.2rem;">Activo: {op['activo']}</p>
                    <p>Estrategia: {op['estrategia']}</p>
                    <p>Hora: {op['hora']}</p>
                    <p>Monto: ${op['monto']}</p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa en este momento.")

    st.divider()

    # Gráfico en tiempo real (si hay datos)
    if st.session_state.datos_grafico is not None:
        fig = crear_grafico_velas(st.session_state.datos_grafico, st.session_state.activo_actual or "Activo")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Esperando datos para mostrar el gráfico...")

    # Historial de operaciones
    with st.expander("📋 Historial de operaciones", expanded=True):
        if st.session_state.historial_ops:
            df_hist = pd.DataFrame(st.session_state.historial_ops)
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Sin operaciones aún.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA PRINCIPAL DEL BOT
    # =========================
    if st.session_state.operando:
        # Verificar cooldown
        now = datetime.now(ecuador)
        if st.session_state.cooldown_hasta and now < st.session_state.cooldown_hasta:
            # Esperar y recargar
            time.sleep(1)
            st.rerun()
        else:
            # Obtener lista de activos
            activos = obtener_activos()
            if not activos:
                st.warning("No se pudieron obtener activos. Reintentando...")
                time.sleep(5)
                st.rerun()

            # Analizar activos secuencialmente
            señal_encontrada = None
            for asset in activos:
                if not st.session_state.operando:
                    break
                st.session_state.activo_actual = asset
                # Evaluar con estrategias activas
                resultado = evaluar_activo(st.session_state.api, asset, st.session_state.estrategias_activas)
                if resultado:
                    direccion, nombre_estr = resultado
                    señal_encontrada = (asset, direccion, nombre_estr)
                    st.session_state.log.append(f"🔔 Señal detectada: {asset} - {direccion} ({nombre_estr})")
                    break
                # Pequeña pausa entre activos
                time.sleep(0.5)

            if señal_encontrada:
                asset, direccion, nombre_estr = señal_encontrada
                # Obtener datos para el gráfico (últimas 50 velas)
                try:
                    candles = st.session_state.api.get_candles(asset, 300, 50, time.time())
                    if candles:
                        df = pd.DataFrame(candles)
                        for col in ['open', 'max', 'min', 'close', 'volume']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                        df.dropna(inplace=True)
                        df = calcular_indicadores(df)
                        st.session_state.datos_grafico = df
                except:
                    pass

                # Ejecutar operación
                exito = ejecutar_operacion(asset, direccion, monto_operacion)
                if exito:
                    # Registrar en historial
                    ahora = now.strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.historial_ops.append({
                        'Fecha': ahora,
                        'Activo': asset,
                        'Dirección': direccion,
                        'Estrategia': nombre_estr,
                        'Monto': monto_operacion,
                        'Resultado': 'Pendiente',
                        'Balance después': st.session_state.saldo
                    })
                    st.session_state.ultima_operacion = {
                        'activo': asset,
                        'direccion': direccion,
                        'estrategia': nombre_estr,
                        'hora': ahora,
                        'monto': monto_operacion
                    }
                    # Activar cooldown de 2 minutos
                    st.session_state.cooldown_hasta = now + timedelta(minutes=2)
                    st.session_state.log.append(f"⏸️ Cooldown activado por 2 minutos")
                else:
                    st.session_state.log.append(f"❌ Falló la ejecución de la operación")
                # Pequeña pausa antes de recargar
                time.sleep(2)
                st.rerun()
            else:
                # No se encontró señal, esperar y continuar
                st.session_state.activo_actual = None
                time.sleep(5)
                st.rerun()

else:
    st.warning("🔒 Por favor, conéctate desde el panel izquierdo.")
