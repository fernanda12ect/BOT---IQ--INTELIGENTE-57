import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    obtener_activos_otc,
    seleccionar_mejor_senal,
    analizar_activo
)

st.set_page_config(
    page_title="NEUROTRADER OTC - AUTOMÁTICO",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (igual que antes)
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
    .status-card {
        background: linear-gradient(145deg, #1a2032, #0f1422);
        border-radius: 20px;
        padding: 20px;
        margin: 15px 0;
        box-shadow: 0 20px 35px -10px rgba(0,0,0,0.5);
        border: 1px solid rgba(0, 163, 255, 0.3);
    }
    .trade-card {
        background: linear-gradient(145deg, #1a2032, #0f1422);
        border-radius: 20px;
        padding: 20px;
        margin: 10px 0;
        border-left: 5px solid;
    }
    .trade-win {
        border-left-color: #00ff88;
    }
    .trade-loss {
        border-left-color: #ff4b4b;
    }
    .trade-pending {
        border-left-color: #ffaa00;
    }
    .asset-name {
        font-size: 1.2rem;
        font-weight: bold;
        margin-bottom: 5px;
        color: #fff;
    }
    .entry-time {
        font-family: monospace;
        font-size: 0.9rem;
        color: #ffaa00;
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
if 'trade_in_progress' not in st.session_state:
    st.session_state.trade_in_progress = False
if 'ultima_trade' not in st.session_state:
    st.session_state.ultima_trade = None
if 'historial' not in st.session_state:
    st.session_state.historial = []
if 'log' not in st.session_state:
    st.session_state.log = []

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
            st.error(f"Error de conexión: {reason}")
            return False
    except Exception as e:
        st.error(f"Excepción: {e}")
        return False

def desconectar():
    st.session_state.api = None
    st.session_state.conectado = False
    st.session_state.monitoreando = False
    st.session_state.trade_in_progress = False

def is_asset_open(api, asset):
    """Verifica si el activo está abierto para opciones binarias."""
    try:
        open_time = api.get_all_open_time()
        if 'binary' in open_time:
            for a, data in open_time['binary'].items():
                if a == asset:
                    return data.get('open', False)
        return False
    except:
        return True  # si falla, asumimos que está abierto (para no bloquear)

def ejecutar_trade(asset, direccion, monto, anticipacion=0):
    """Ejecuta una operación de compra/venta con vencimiento de 1 minuto."""
    try:
        # Verificar que el activo esté abierto
        if not is_asset_open(st.session_state.api, asset):
            st.session_state.log.append(f"⚠️ {asset} no está disponible para trading en este momento.")
            return False

        # Determinar tipo de opción
        opcion = "call" if direccion == "CALL" else "put"
        # Vencimiento: 50 segundos desde ahora (da margen de 10 segundos antes del próximo minuto)
        expiracion = int(time.time()) + 50
        # Ejecutar orden
        success, order_id = st.session_state.api.buy(monto, asset, opcion, expiracion)
        if success:
            entrada = datetime.now(ecuador) + timedelta(seconds=anticipacion)
            entrada_str = entrada.strftime("%H:%M:%S")
            vencimiento_str = (entrada + timedelta(minutes=1)).strftime("%H:%M:%S")
            st.session_state.ultima_trade = {
                'asset': asset,
                'direccion': direccion,
                'monto': monto,
                'entrada': entrada_str,
                'vencimiento': vencimiento_str,
                'estado': 'PENDIENTE',
                'order_id': order_id
            }
            st.session_state.trade_in_progress = True
            st.session_state.log.append(f"💰 Trade ejecutado: {asset} {direccion} ${monto} (ID: {order_id}, expira en 50s)")
            # Actualizar saldo (descuento inmediato)
            st.session_state.saldo -= monto
            return True
        else:
            # Manejo específico del error de tiempo
            if "Time for purchasing options is over" in str(order_id):
                st.session_state.log.append(f"⏰ {asset} no disponible en este momento (tiempo expirado).")
            else:
                st.session_state.log.append(f"❌ Error al ejecutar trade en {asset}: {order_id}")
            return False
    except Exception as e:
        st.session_state.log.append(f"⚠️ Excepción al ejecutar trade en {asset}: {e}")
        return False

def verificar_resultado_trade():
    """Verifica si la operación pendiente ha vencido y obtiene resultado."""
    if not st.session_state.trade_in_progress or not st.session_state.ultima_trade:
        return False
    trade = st.session_state.ultima_trade
    vencimiento_dt = datetime.strptime(trade['vencimiento'], "%H:%M:%S").time()
    ahora = datetime.now(ecuador).time()
    ahora_dt = datetime.combine(datetime.today(), ahora)
    vencimiento_dt_full = datetime.combine(datetime.today(), vencimiento_dt)
    if vencimiento_dt_full < ahora_dt:
        vencimiento_dt_full += timedelta(days=1)
    if ahora_dt >= vencimiento_dt_full:
        try:
            resultado = st.session_state.api.check_win_v4(trade['order_id'])
            if resultado is not None:
                if isinstance(resultado, tuple):
                    estado, ganancia = resultado
                else:
                    estado = resultado
                    ganancia = 0
                if estado == 'win':
                    st.session_state.saldo += trade['monto'] + ganancia
                    trade['estado'] = 'GANADA'
                    st.session_state.log.append(f"✅ Trade {trade['order_id']} GANADA: +{ganancia:.2f}")
                elif estado == 'loose':
                    trade['estado'] = 'PERDIDA'
                    st.session_state.log.append(f"❌ Trade {trade['order_id']} PERDIDA")
                else:
                    trade['estado'] = 'DEVUELTA'
                    st.session_state.saldo += trade['monto']
                    st.session_state.log.append(f"🔄 Trade {trade['order_id']} DEVUELTA")
            else:
                trade['estado'] = 'SIN RESULTADO'
                st.session_state.log.append(f"⚠️ No se pudo obtener resultado para {trade['order_id']}")
        except Exception as e:
            st.session_state.log.append(f"⚠️ Error al verificar resultado: {e}")
            trade['estado'] = 'ERROR'
        st.session_state.historial.append(trade)
        st.session_state.ultima_trade = None
        st.session_state.trade_in_progress = False
        return True
    return False

# Sidebar
with st.sidebar:
    st.markdown("## 🤖 NEUROTRADER OTC - AUTOMÁTICO")
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
    tipo_cuenta = st.radio("Tipo de cuenta", ["PRACTICE", "REAL"], index=0, horizontal=True)
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        saldo = st.session_state.api.get_balance()
        st.session_state.saldo = saldo if saldo is not None else 0.0
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    monto = st.number_input("💵 Monto por operación ($)", min_value=0.5, max_value=100.0, value=1.0, step=0.5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR BOT", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Bot automático iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER BOT", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("🤖 Bot Automático - 1 minuto")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Estado", "ACTIVO" if st.session_state.monitoreando else "DETENIDO")
    with col3:
        if st.session_state.trade_in_progress:
            st.metric("Operación", "En curso")
        else:
            st.metric("Operación", "Listo")

    if st.session_state.trade_in_progress and st.session_state.ultima_trade:
        t = st.session_state.ultima_trade
        st.markdown(f"""
        <div class="status-card trade-card trade-pending">
            <div class="asset-name">🔄 OPERACIÓN EN CURSO</div>
            <div><strong>{t['asset']}</strong> - {t['direccion']}</div>
            <div>Monto: ${t['monto']}</div>
            <div class="entry-time">Entrada: {t['entrada']}</div>
            <div class="entry-time">Vencimiento: {t['vencimiento']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay operación en curso. El bot analizará en el próximo minuto.")

    if st.session_state.historial:
        st.subheader("📋 Historial de operaciones")
        for trade in st.session_state.historial[-10:]:
            card_class = "trade-win" if trade['estado'] == "GANADA" else "trade-loss" if trade['estado'] == "PERDIDA" else "trade-pending"
            st.markdown(f"""
            <div class="trade-card {card_class}">
                <div class="asset-name">{trade['asset']} - {trade['direccion']}</div>
                <div>Monto: ${trade['monto']}</div>
                <div>Entrada: {trade['entrada']} | Vencimiento: {trade['vencimiento']}</div>
                <div>Resultado: {trade['estado']}</div>
            </div>
            """, unsafe_allow_html=True)

    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)
        segundo = now.second

        if st.session_state.trade_in_progress:
            if verificar_resultado_trade():
                st.rerun()
            else:
                trade = st.session_state.ultima_trade
                vencimiento_dt = datetime.strptime(trade['vencimiento'], "%H:%M:%S").time()
                ahora = datetime.now(ecuador).time()
                ahora_dt = datetime.combine(datetime.today(), ahora)
                vencimiento_dt_full = datetime.combine(datetime.today(), vencimiento_dt)
                if vencimiento_dt_full < ahora_dt:
                    vencimiento_dt_full += timedelta(days=1)
                seg_rest = (vencimiento_dt_full - ahora_dt).total_seconds()
                st.info(f"⏳ Operación en curso. Vence en {int(seg_rest)} segundos...")
                time.sleep(1)
                st.rerun()
        else:
            if segundo == 58:
                # Pequeña pausa para evitar el límite exacto
                time.sleep(0.2)
                st.session_state.log.append("🔍 Analizando activos OTC...")
                activos = obtener_activos_otc(st.session_state.api)
                mejor = seleccionar_mejor_senal(st.session_state.api, activos)
                if mejor:
                    direccion, desc = mejor['senal']
                    # Pequeña pausa antes de ejecutar para asegurar que estamos dentro del margen
                    time.sleep(0.1)
                    exito = ejecutar_trade(mejor['asset'], direccion, monto, anticipacion=0)
                    if exito:
                        st.session_state.log.append(f"🚀 OPERACIÓN EJECUTADA: {mejor['asset']} - {direccion}")
                    else:
                        st.session_state.log.append(f"❌ No se pudo ejecutar trade para {mejor['asset']}")
                else:
                    st.session_state.log.append("🔍 SIN SEÑAL – ESPERAR PROXIMO MINUTO")
                time.sleep(0.2)
                st.rerun()
            else:
                if segundo < 58:
                    seg_rest = 58 - segundo
                else:
                    seg_rest = 60 - segundo + 58
                st.info(f"⏳ Próxima señal en {seg_rest} segundos...")
                time.sleep(1)
                st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
