import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejores_activos,
    obtener_activos_abiertos,
    calcular_indicadores
)

# Configuración de página
st.set_page_config(
    page_title="NEUROTRADER MULTI",
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
    .signal-title { font-size: 1.5rem; font-weight: bold; margin-bottom: 10px; }
    .signal-detail { font-size: 1rem; color: #ccc; margin: 5px 0; }
    .signal-time { color: #888; font-size: 0.9rem; }
    hr { border-color: #2a2f3a; }
    .asset-box {
        background-color: #1a2a3a;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
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
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []  # lista de activos en seguimiento
if 'estados' not in st.session_state:
    st.session_state.estados = {}  # dict {asset: {estado, direccion, fuerza, hora_entrada, hora_vencimiento, ultima_actualizacion}}
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
    fig.update_layout(title=f"{activo} - Análisis",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=500)
    return fig

# =========================
# BARRA LATERAL
# =========================
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER MULTI")
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
    tipo_cuenta = st.radio("Tipo de cuenta", ["PRACTICE", "REAL"], index=0, horizontal=True, label_visibility="collapsed")
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        saldo = st.session_state.api.get_balance()
        st.session_state.saldo = saldo if saldo is not None else 0.0
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    st.markdown("---")

    st.markdown("### ⚙️ Configuración")
    mercado = st.selectbox("Mercado a analizar", ["OTC", "REAL", "AMBOS"], index=0)
    num_activos = st.slider("Número de activos a monitorear", 1, 5, 3, 1,
                             help="Cantidad de activos que el bot seguirá simultáneamente")
    tiempo_max_espera = st.slider("Tiempo máximo de espera (minutos)", 5, 30, 15, 5,
                                   help="Si un activo no da señal en este tiempo, se buscará otro.")

    st.markdown("---")

    st.markdown("### ⚙️ Control")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar los mejores activos dinámicamente
                with st.spinner(f"Analizando activos {mercado} en tiempo real..."):
                    seleccionados = seleccionar_mejores_activos(
                        st.session_state.api, mercado, num_activos
                    )
                    if seleccionados:
                        st.session_state.activos_seleccionados = [asset for asset, _, _ in seleccionados]
                        for asset, direc, fuerza in seleccionados:
                            st.session_state.estados[asset] = {
                                'direccion': direc,
                                'fuerza': fuerza,
                                'estado': 'ESPERANDO',
                                'hora_entrada': None,
                                'hora_vencimiento': None,
                                'ultima_actualizacion': datetime.now(ecuador)
                            }
                        st.session_state.log.append(f"✅ Activos seleccionados: {', '.join(st.session_state.activos_seleccionados)}")
                    else:
                        st.session_state.log.append("⚠️ No se encontraron activos confiables en este momento.")
                        st.session_state.activos_seleccionados = []
                st.rerun()
        else:
            if st.button("⏹️ DETENER MONITOREO", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.session_state.activos_seleccionados = []
                st.session_state.estados = {}
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
        st.metric("Activos en seguimiento", len(st.session_state.activos_seleccionados))
    with col3:
        st.metric("Señales generadas", len(st.session_state.señales))

    # Mostrar activos en seguimiento y sus tarjetas de señal
    if st.session_state.activos_seleccionados:
        st.subheader("📊 ACTIVOS EN SEGUIMIENTO")
        for asset in st.session_state.activos_seleccionados:
            estado = st.session_state.estados.get(asset, {})
            direccion = estado.get('direccion', '?')
            fuerza = estado.get('fuerza', 0)
            estado_actual = estado.get('estado', 'ESPERANDO')
            hora_entrada = estado.get('hora_entrada')
            hora_vencimiento = estado.get('hora_vencimiento')

            if estado_actual == "LISTO" and hora_entrada:
                card_class = "call-card" if direccion == "CALL" else "put-card"
                st.markdown(f"""
                <div class="signal-card {card_class}">
                    <div class="signal-title">{'🔵 COMPRA (CALL)' if direccion == 'CALL' else '🔴 VENTA (PUT)'}</div>
                    <div class="signal-detail"><strong>Activo:</strong> {asset}</div>
                    <div class="signal-detail"><strong>Entrada:</strong> {hora_entrada}</div>
                    <div class="signal-detail"><strong>Vencimiento:</strong> {hora_vencimiento} (5 minutos)</div>
                    <div class="signal-detail"><strong>Fuerza:</strong> {fuerza:.1f}</div>
                    <div class="signal-time">✅ LISTO PARA OPERAR</div>
                </div>
                """, unsafe_allow_html=True)
            elif estado_actual == "OPERACION_EN_CURSO" and hora_entrada:
                now = datetime.now(ecuador)
                vencimiento = datetime.strptime(hora_vencimiento, "%H:%M:%S").time()
                vencimiento_dt = datetime.combine(now.date(), vencimiento)
                if vencimiento_dt < now:
                    vencimiento_dt += timedelta(days=1)
                resto = (vencimiento_dt - now).total_seconds()
                mins, segs = divmod(int(resto), 60)
                st.markdown(f"""
                <div class="signal-card waiting-card">
                    <div class="signal-title">⏳ OPERACIÓN EN CURSO</div>
                    <div class="signal-detail"><strong>Activo:</strong> {asset}</div>
                    <div class="signal-detail"><strong>Entrada:</strong> {hora_entrada}</div>
                    <div class="signal-detail"><strong>Vencimiento:</strong> {hora_vencimiento}</div>
                    <div class="signal-detail"><strong>Tiempo restante:</strong> {mins:02d}:{segs:02d}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="asset-box">
                    <strong>{asset}</strong> | Dirección: {direccion} | Fuerza: {fuerza:.1f} | Estado: {estado_actual}
                </div>
                """, unsafe_allow_html=True)

    # Historial de señales
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
    if st.session_state.monitoreando and st.session_state.activos_seleccionados:
        now = datetime.now(ecuador)

        # Revisar cada activo en seguimiento
        for asset in st.session_state.activos_seleccionados:
            estado = st.session_state.estados.get(asset, {})
            if estado.get('estado') == 'OPERACION_EN_CURSO':
                # Verificar si ya venció
                vencimiento = datetime.strptime(estado['hora_vencimiento'], "%H:%M:%S").time()
                vencimiento_dt = datetime.combine(now.date(), vencimiento)
                if vencimiento_dt < now:
                    vencimiento_dt += timedelta(days=1)
                if now >= vencimiento_dt:
                    # Operación vencida, volver a ESPERANDO
                    estado['estado'] = 'ESPERANDO'
                    estado['hora_entrada'] = None
                    estado['hora_vencimiento'] = None
                    st.session_state.log.append(f"✅ Operación finalizada para {asset}")
            else:
                # Evaluar el activo
                direccion, fuerza, lista_para_entrar, estrategia, precio = evaluar_activo(
                    st.session_state.api, asset, check_agotamiento=True
                )
                if direccion is None:
                    # El activo perdió tendencia, lo marcaremos para reemplazo después
                    st.session_state.log.append(f"⚠️ {asset} perdió tendencia. Será reemplazado.")
                    continue
                else:
                    # Actualizar datos
                    estado['direccion'] = direccion
                    estado['fuerza'] = fuerza
                    estado['ultima_actualizacion'] = now

                    if lista_para_entrar and estado['estado'] == 'ESPERANDO':
                        # Generar señal
                        hora_entrada = now.strftime("%H:%M:%S")
                        hora_venc = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
                        estado['estado'] = 'LISTO'
                        estado['hora_entrada'] = hora_entrada
                        estado['hora_vencimiento'] = hora_venc
                        st.session_state.señales.insert(0, {
                            'fecha': now.strftime("%Y-%m-%d %H:%M:%S"),
                            'activo': asset,
                            'direccion': direccion,
                            'entrada': hora_entrada,
                            'vencimiento': hora_venc,
                            'estrategia': estrategia
                        })
                        st.session_state.log.append(f"📢 SEÑAL GENERADA: {asset} - {direccion} a las {hora_entrada}")

        # Después de evaluar, podemos verificar si hay que reemplazar algún activo
        nuevos_activos = []
        for asset in st.session_state.activos_seleccionados:
            estado = st.session_state.estados.get(asset)
            if estado and estado.get('direccion') is not None:
                nuevos_activos.append(asset)
            else:
                # Este activo debe ser reemplazado
                st.session_state.log.append(f"🔄 Buscando reemplazo para {asset}...")
                # Buscamos un nuevo activo del mismo mercado
                seleccionados = seleccionar_mejores_activos(
                    st.session_state.api, mercado, 1  # solo uno de reemplazo
                )
                if seleccionados:
                    nuevo_asset, nueva_dir, nueva_fuerza = seleccionados[0]
                    if nuevo_asset not in st.session_state.activos_seleccionados:
                        nuevos_activos.append(nuevo_asset)
                        st.session_state.estados[nuevo_asset] = {
                            'direccion': nueva_dir,
                            'fuerza': nueva_fuerza,
                            'estado': 'ESPERANDO',
                            'hora_entrada': None,
                            'hora_vencimiento': None,
                            'ultima_actualizacion': now
                        }
                        st.session_state.log.append(f"✅ Nuevo activo añadido: {nuevo_asset}")
                # Eliminar el viejo del dict de estados
                if asset in st.session_state.estados:
                    del st.session_state.estados[asset]

        st.session_state.activos_seleccionados = nuevos_activos
        time.sleep(5)  # pausa entre ciclos
        st.rerun()

    elif st.session_state.monitoreando and not st.session_state.activos_seleccionados:
        # No hay activos, intentar seleccionar de nuevo
        st.session_state.log.append("🔄 No hay activos, buscando nuevamente...")
        seleccionados = seleccionar_mejores_activos(st.session_state.api, mercado, num_activos)
        if seleccionados:
            st.session_state.activos_seleccionados = [asset for asset, _, _ in seleccionados]
            for asset, direc, fuerza in seleccionados:
                st.session_state.estados[asset] = {
                    'direccion': direc,
                    'fuerza': fuerza,
                    'estado': 'ESPERANDO',
                    'hora_entrada': None,
                    'hora_vencimiento': None,
                    'ultima_actualizacion': datetime.now(ecuador)
                }
            st.session_state.log.append(f"✅ Nuevos activos seleccionados: {', '.join(st.session_state.activos_seleccionados)}")
        time.sleep(5)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
