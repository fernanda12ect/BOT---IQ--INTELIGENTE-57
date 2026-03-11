import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import evaluar_activo, ESTRATEGIAS, calcular_indicadores

# Configuración de página
st.set_page_config(
    page_title="NEUROTRADER",
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
    .call-box { background-color: #1a2a1a; border-left: 4px solid #00ff88; padding: 10px; margin: 5px 0; border-radius: 5px; }
    .put-box { background-color: #2a1a1a; border-left: 4px solid #ff4b4b; padding: 10px; margin: 5px 0; border-radius: 5px; }
    h1 { color: #00a3ff; font-size: 2.5rem; font-weight: 700; margin-bottom: 0; }
    hr { border-color: #2a2f3a; }
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
if 'operaciones_pendientes' not in st.session_state:
    st.session_state.operaciones_pendientes = []  # lista de dicts con order_id, activo, direccion, monto, timestamp
if 'historial_ops' not in st.session_state:
    st.session_state.historial_ops = []
if 'log' not in st.session_state:
    st.session_state.log = []
if 'estrategias_activas' not in st.session_state:
    st.session_state.estrategias_activas = [nombre for nombre, _ in ESTRATEGIAS[:5]]
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = None
if 'stop_loss' not in st.session_state:
    st.session_state.stop_loss = 100.0
if 'take_profit' not in st.session_state:
    st.session_state.take_profit = 50.0
if 'martingala' not in st.session_state:
    st.session_state.martingala = False
if 'perdidas_consecutivas' not in st.session_state:
    st.session_state.perdidas_consecutivas = 0
if 'ganancias_totales' not in st.session_state:
    st.session_state.ganancias_totales = 0.0
if 'perdidas_totales' not in st.session_state:
    st.session_state.perdidas_totales = 0.0
if 'total_operaciones' not in st.session_state:
    st.session_state.total_operaciones = 0

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

def verificar_operaciones_pendientes():
    """Revisa si hay operaciones pendientes que ya vencieron y actualiza resultados"""
    ahora = datetime.now(ecuador)
    nuevas_pendientes = []
    for op in st.session_state.operaciones_pendientes:
        tiempo_vencimiento = op['timestamp'] + timedelta(minutes=5)
        if ahora >= tiempo_vencimiento:
            # La operación ya venció, verificar resultado
            try:
                resultado = st.session_state.api.check_win_v4(op['order_id'])
                if resultado is not None:
                    # resultado es una tupla: (estado, ganancia)
                    estado, ganancia = resultado if isinstance(resultado, tuple) else (resultado, 0)
                    
                    if estado == 'win':
                        st.session_state.saldo += op['monto'] + ganancia
                        st.session_state.ganancias_totales += ganancia
                        resultado_texto = f"GANADA (+${ganancia:.2f})"
                        resultado_num = ganancia
                    elif estado == 'loose':
                        st.session_state.perdidas_totales += op['monto']
                        resultado_texto = f"PERDIDA (-${op['monto']:.2f})"
                        resultado_num = -op['monto']
                    else:  # equal
                        st.session_state.saldo += op['monto']
                        resultado_texto = "DEVUELTA"
                        resultado_num = 0
                    
                    st.session_state.historial_ops.append({
                        'Fecha': op['timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
                        'Activo': op['activo'],
                        'Dirección': op['direccion'],
                        'Estrategia': op['estrategia'],
                        'Monto': op['monto'],
                        'Resultado': resultado_texto,
                        'Balance después': st.session_state.saldo
                    })
                    
                    st.session_state.total_operaciones += 1
                    st.session_state.log.append(f"📊 Operación {op['order_id']}: {resultado_texto}")
                else:
                    # Si no se pudo verificar, reintentar después
                    nuevas_pendientes.append(op)
            except Exception as e:
                st.session_state.log.append(f"⚠️ Error verificando operación {op['order_id']}: {e}")
                nuevas_pendientes.append(op)
        else:
            nuevas_pendientes.append(op)
    
    st.session_state.operaciones_pendientes = nuevas_pendientes

def ejecutar_operacion(activo, direccion, monto, estrategia):
    if not st.session_state.api:
        return False, "No conectado"
    try:
        # Validar stop loss/take profit
        perdidas_totales = abs(st.session_state.perdidas_totales)
        if st.session_state.stop_loss > 0 and perdidas_totales >= st.session_state.stop_loss:
            st.session_state.operando = False
            return False, f"Stop loss alcanzado (${perdidas_totales:.2f})"
        
        if st.session_state.take_profit > 0 and st.session_state.ganancias_totales >= st.session_state.take_profit:
            st.session_state.operando = False
            return False, f"Take profit alcanzado (${st.session_state.ganancias_totales:.2f})"

        # Ejecutar operación
        accion = "call" if direccion == "CALL" else "put"
        expiracion = int(time.time()) + 300  # 5 minutos
        success, data = st.session_state.api.buy(monto, activo, accion, expiracion)
        
        if success:
            # data es el order_id
            order_id = data
            # Registrar operación pendiente
            st.session_state.operaciones_pendientes.append({
                'order_id': order_id,
                'activo': activo,
                'direccion': direccion,
                'estrategia': estrategia,
                'monto': monto,
                'timestamp': datetime.now(ecuador)
            })
            
            # Actualizar saldo (descuento inmediato)
            st.session_state.saldo -= monto
            
            # Resetear contador de pérdidas consecutivas (se actualizará al vencer)
            if st.session_state.martingala and direccion == "CALL":
                pass
            
            st.session_state.log.append(f"💰 Operación ejecutada: {activo} {direccion} ${monto} (ID: {order_id})")
            return True, f"Operación ejecutada (ID: {order_id})"
        else:
            # data es el mensaje de error
            st.session_state.log.append(f"❌ Error al ejecutar operación: {data}")
            return False, f"Error: {data}"
    except Exception as e:
        st.session_state.log.append(f"⚠️ Excepción en operación: {e}")
        return False, f"Excepción: {e}"

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

    fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], line=dict(color='#888', width=1, dash='dash'), name='BB Sup'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], line=dict(color='#888', width=1, dash='dash'), name='BB Inf'), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='#aa88ff', width=1), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ff4b4b", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00ff88", row=2, col=1)

    fig.update_layout(title=f"{activo} - Análisis en tiempo real",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=600,
                      margin=dict(l=50, r=50, t=50, b=50))
    fig.update_xaxes(title_text="Tiempo", row=2, col=1)
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="RSI", row=2, col=1)

    return fig

# =========================
# BARRA LATERAL
# =========================
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER")
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
    tipo_cuenta = st.radio("", ["PRACTICE", "REAL"], index=0, horizontal=True)
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        saldo = st.session_state.api.get_balance()
        st.session_state.saldo = saldo if saldo is not None else 0.0
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    st.markdown("### 💵 Monto por operación")
    monto_operacion = st.number_input("", min_value=1.0, max_value=1000.0, value=10.0, step=1.0, label_visibility="collapsed")

    st.markdown("---")

    st.markdown("### ⚖️ Gestión de riesgo")
    stop_loss = st.number_input("Stop Loss ($)", min_value=0.0, value=100.0, step=10.0)
    take_profit = st.number_input("Take Profit ($)", min_value=0.0, value=50.0, step=10.0)
    martingala = st.checkbox("Estrategia Martingala (duplicar tras pérdida)")

    st.session_state.stop_loss = stop_loss
    st.session_state.take_profit = take_profit
    st.session_state.martingala = martingala

    st.markdown("---")

    st.markdown("### 🎯 Estrategias activas")
    nuevas_estrategias = []
    for nombre, _ in ESTRATEGIAS:
        activa = st.checkbox(nombre, value=(nombre in st.session_state.estrategias_activas))
        if activa:
            nuevas_estrategias.append(nombre)
    st.session_state.estrategias_activas = nuevas_estrategias

    st.markdown("---")

    if st.session_state.conectado:
        if not st.session_state.operando:
            if st.button("▶️ INICIAR BOT", use_container_width=True, type="primary"):
                st.session_state.operando = True
                st.session_state.log.append("🚀 Bot iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER BOT", use_container_width=True, type="secondary"):
                st.session_state.operando = False
                st.session_state.log.append("🛑 Bot detenido")
                st.rerun()

    if st.session_state.conectado:
        st.markdown("---")
        st.metric("Saldo actual", f"${st.session_state.saldo:.2f}")

# =========================
# ÁREA PRINCIPAL
# =========================
if st.session_state.conectado:
    # Verificar operaciones pendientes
    verificar_operaciones_pendientes()
    
    # Calcular estadísticas
    ganadas = sum(1 for op in st.session_state.historial_ops if 'GANADA' in op['Resultado'])
    perdidas = sum(1 for op in st.session_state.historial_ops if 'PERDIDA' in op['Resultado'])
    total = ganadas + perdidas
    win_rate = (ganadas / total * 100) if total > 0 else 0
    profit_total = st.session_state.ganancias_totales - st.session_state.perdidas_totales

    # Cabecera con métricas
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with col3:
        st.metric("Profit Total", f"${profit_total:.2f}")
    with col4:
        st.metric("Operaciones", total)
    with col5:
        st.metric("Estrategias Activas", len(st.session_state.estrategias_activas))

    # Activo actual y gráfico
    if st.session_state.activo_actual:
        st.subheader(f"🔍 Analizando: {st.session_state.activo_actual}")
    else:
        st.subheader("🔍 Esperando análisis...")

    if st.session_state.datos_grafico is not None:
        fig = crear_grafico_velas(st.session_state.datos_grafico, st.session_state.activo_actual or "Activo")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("El gráfico se mostrará cuando se analice un activo.")

    # Señales activas (última operación lanzada)
    st.subheader("📊 Última señal ejecutada")
    if st.session_state.ultima_operacion:
        op = st.session_state.ultima_operacion
        if op['direccion'] == 'CALL':
            st.markdown(f"""
            <div class="call-box">
                <strong>{op['hora']} - {op['activo']}</strong> 🔵 CALL<br>
                Estrategia: {op['estrategia']} | Monto: ${op['monto']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="put-box">
                <strong>{op['hora']} - {op['activo']}</strong> 🔴 PUT<br>
                Estrategia: {op['estrategia']} | Monto: ${op['monto']}
            </div>
            """, unsafe_allow_html=True)

    # Operaciones pendientes con contador
    if st.session_state.operaciones_pendientes:
        with st.expander("⏳ Operaciones en curso", expanded=True):
            for op in st.session_state.operaciones_pendientes:
                tiempo_restante = (op['timestamp'] + timedelta(minutes=5) - datetime.now(ecuador)).total_seconds()
                if tiempo_restante > 0:
                    mins, segs = divmod(int(tiempo_restante), 60)
                    st.text(f"{op['activo']} - {op['direccion']} - ${op['monto']} - Tiempo restante: {mins:02d}:{segs:02d}")
                else:
                    st.text(f"{op['activo']} - {op['direccion']} - ${op['monto']} - VENCIDA (verificando resultado)")

    # Historial de operaciones
    with st.expander("📋 Historial de operaciones", expanded=True):
        if st.session_state.historial_ops:
            df_hist = pd.DataFrame(st.session_state.historial_ops)
            st.dataframe(df_hist[['Fecha', 'Activo', 'Dirección', 'Monto', 'Estrategia', 'Resultado', 'Balance después']],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No hay operaciones en el historial aún.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA PRINCIPAL DEL BOT
    # =========================
    if st.session_state.operando:
        now = datetime.now(ecuador)
        
        # Si hay operaciones pendientes, esperar a que venzan (no buscar nuevas señales)
        if len(st.session_state.operaciones_pendientes) > 0:
            # Mostrar tiempo restante y esperar 1 segundo para actualizar contador
            time.sleep(1)
            st.rerun()
        else:
            # No hay operaciones pendientes, podemos buscar una nueva señal
            activos = obtener_activos()
            if not activos:
                time.sleep(5)
                st.rerun()

            señal_encontrada = None
            for asset in activos:
                if not st.session_state.operando:
                    break
                st.session_state.activo_actual = asset
                resultado = evaluar_activo(st.session_state.api, asset, st.session_state.estrategias_activas)
                if resultado:
                    direccion, nombre_estr = resultado
                    señal_encontrada = (asset, direccion, nombre_estr)
                    st.session_state.log.append(f"🔔 Señal detectada: {asset} - {direccion} ({nombre_estr})")
                    break
                time.sleep(0.5)

            if señal_encontrada:
                asset, direccion, nombre_estr = señal_encontrada
                
                # Obtener datos para gráfico
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

                # Aplicar martingala
                monto_actual = monto_operacion
                if st.session_state.martingala and st.session_state.perdidas_consecutivas > 0:
                    monto_actual = monto_operacion * (2 ** st.session_state.perdidas_consecutivas)
                    if monto_actual > st.session_state.saldo:
                        monto_actual = st.session_state.saldo

                exito, msg = ejecutar_operacion(asset, direccion, monto_actual, nombre_estr)
                if exito:
                    ahora = now.strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.ultima_operacion = {
                        'activo': asset,
                        'direccion': direccion,
                        'estrategia': nombre_estr,
                        'hora': ahora,
                        'monto': monto_actual
                    }
                    # No hay cooldown, se esperará a que venza la operación
                else:
                    st.session_state.log.append(f"❌ Falló operación: {msg}")
                
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.activo_actual = None
                time.sleep(5)
                st.rerun()
else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
