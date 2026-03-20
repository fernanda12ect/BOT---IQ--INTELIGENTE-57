import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejor_activo,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER PRO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (se mantienen igual, omitidos por brevedad)
# ... (mismo CSS que antes) ...

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
if 'senal_activa' not in st.session_state:
    st.session_state.senal_activa = None
if 'log' not in st.session_state:
    st.session_state.log = []
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

def get_next_candle_times(now):
    """Calcula el inicio y fin de la vela de 5 minutos actual y la próxima."""
    now_utc = now.astimezone(pytz.UTC)
    minute = now_utc.minute
    start_minute = (minute // 5) * 5
    candle_start = now_utc.replace(minute=start_minute, second=0, microsecond=0)
    candle_end = candle_start + timedelta(minutes=5)
    next_candle_start = candle_end
    return candle_start, candle_end, next_candle_start

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
    umbral_fuerza = st.slider("Fuerza mínima para señal (%)", 0, 100, 60, 5)
    anticipacion = st.slider("Anticipación de señal (segundos antes del cierre)", 5, 60, 30, 5)

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
    st.title("📊 Sistema de Trading - Tendencia + Niveles Clave")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Señales activas", "1" if st.session_state.senal_activa else "0")
    with col3:
        st.metric("Activos seguimiento", len(st.session_state.activos_totales) if st.session_state.activos_totales else 0)

    if st.session_state.senal_activa:
        s = st.session_state.senal_activa
        card_class = "signal-call" if s['direccion'] == "CALL" else "signal-put"
        st.markdown(f"""
        <div class="asset-card {card_class}">
            <div class="asset-name">{s['asset']}</div>
            <div class="asset-status">✅ SEÑAL ACTIVA</div>
            <div><strong>{s['direccion']}</strong> - Entrada en {s['nivel_desc']}</div>
            <div>Fuerza: {s['fuerza']:.1f}%</div>
            <div class="force-bar"><div class="force-fill" style="width: {s['fuerza']}%;"></div></div>
            <div class="entry-time">⏱️ Entrada: {s['entrada']}</div>
            <div class="entry-time">⏰ Vencimiento: {s['vencimiento']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa. Esperando condiciones...")

    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    if st.session_state.monitoreando:
        now = datetime.now(ecuador)
        candle_start, candle_end, next_candle_start = get_next_candle_times(now)

        if st.session_state.senal_activa:
            entrada_str = st.session_state.senal_activa['entrada']
            entrada_hora = datetime.strptime(entrada_str, "%H:%M:%S").time()
            entrada_dt = datetime.combine(now.date(), entrada_hora)
            entrada_dt = ecuador.localize(entrada_dt)
            if entrada_dt > now:
                entrada_dt -= timedelta(days=1)
            expiracion = entrada_dt + timedelta(minutes=5)
            if now >= expiracion:
                st.session_state.senal_activa = None
                st.session_state.log.append("🗑️ Señal expirada. Buscando nueva...")
                st.rerun()
            else:
                seg_rest = (expiracion - now).total_seconds()
                mins = int(seg_rest // 60)
                segs = int(seg_rest % 60)
                st.info(f"⏳ Señal activa. Vence en {mins} min {segs} seg...")
                time.sleep(1)
                st.rerun()
        else:
            seg_hasta_cierre = (candle_end - now).total_seconds()
            if 0 <= seg_hasta_cierre <= anticipacion:
                if not st.session_state.activos_totales:
                    st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                if not st.session_state.activos_totales:
                    st.warning("No hay activos disponibles")
                    time.sleep(2)
                    st.rerun()

                mejor = seleccionar_mejor_activo(st.session_state.api, st.session_state.activos_totales)
                if mejor and mejor['fuerza'] >= umbral_fuerza:
                    entrada_dt = next_candle_start.astimezone(ecuador)
                    entrada_str = entrada_dt.strftime("%H:%M:%S")
                    vencimiento_dt = entrada_dt + timedelta(minutes=5)
                    vencimiento_str = vencimiento_dt.strftime("%H:%M:%S")
                    st.session_state.senal_activa = {
                        'asset': mejor['asset'],
                        'direccion': mejor['direccion'],
                        'fuerza': mejor['fuerza'],
                        'nivel_desc': mejor['descripcion'],
                        'entrada': entrada_str,
                        'vencimiento': vencimiento_str
                    }
                    st.session_state.log.append(f"🚀 SEÑAL: {mejor['asset']} - {mejor['direccion']} a las {entrada_str} (Nivel: {mejor['descripcion']}, Fuerza: {mejor['fuerza']:.1f}%)")
                else:
                    st.session_state.log.append("🔍 No se encontraron señales en esta vela.")
                time.sleep(1)
                st.rerun()
            else:
                seg_rest = seg_hasta_cierre - anticipacion if seg_hasta_cierre > anticipacion else (candle_start + timedelta(minutes=5) - now).total_seconds()
                st.info(f"⏳ Próximo análisis en {int(seg_rest)} segundos...")
                time.sleep(1)
                st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
