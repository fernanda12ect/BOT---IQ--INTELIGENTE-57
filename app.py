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
    page_title="NEUROTRADER PRO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (igual que antes, se omite por brevedad)
# ... (el mismo CSS que en la respuesta anterior) ...

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
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0

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

# Sidebar (mismo código que antes)
# ...

# Área principal
if st.session_state.conectado:
    st.title("📊 Sistema de Trading con 8 Estrategias")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Señales activas", "1" if st.session_state.senal_activa else "0")
    with col3:
        st.metric("Estrategias activas", len(ESTRATEGIAS))

    # Mostrar señal actual si existe
    if st.session_state.senal_activa:
        s = st.session_state.senal_activa
        card_class = "signal-call" if s['direccion'] == "CALL" else "signal-put"
        st.markdown(f"""
        <div class="asset-card {card_class}">
            <div class="asset-name">{s['asset']}</div>
            <div class="asset-status">✅ SEÑAL ACTIVA</div>
            <div><strong>{s['direccion']}</strong> - Consenso de {len(s['estrategias'])} estrategias</div>
            <div>Fuerza: {s['fuerza']:.1f}%</div>
            <div class="force-bar"><div class="force-fill" style="width: {s['fuerza']}%;"></div></div>
            <div class="entry-time">⏱️ Entrada: {s['entrada']}</div>
            <div class="entry-time">⏰ Vencimiento: {s['vencimiento']}</div>
            <div><small>Estrategias: {', '.join(s['estrategias'][:3])}{'...' if len(s['estrategias'])>3 else ''}</small></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa. Esperando condiciones...")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si hay señal activa, esperar a que venza (5 minutos después de entrada)
        if st.session_state.senal_activa:
            entrada_str = st.session_state.senal_activa['entrada']
            # Convertir entrada_str a datetime del día actual (asumiendo que la entrada ocurre hoy)
            entrada_hora = datetime.strptime(entrada_str, "%H:%M:%S").time()
            entrada_dt = datetime.combine(now.date(), entrada_hora)
            entrada_dt = ecuador.localize(entrada_dt)
            # Si la entrada ya pasó hoy, consideramos que fue ayer (para no obtener tiempo negativo)
            if entrada_dt > now:
                entrada_dt -= timedelta(days=1)
            # Calcular tiempo de expiración (5 minutos después)
            expiracion = entrada_dt + timedelta(minutes=5)
            if now >= expiracion:
                # Señal expirada, eliminarla y volver a analizar
                st.session_state.senal_activa = None
                st.session_state.log.append("🗑️ Señal expirada. Buscando nueva...")
                st.rerun()
            else:
                seg_rest = (expiracion - now).total_seconds()
                mins = int(seg_rest // 60)
                segs = int(seg_rest % 60)
                st.info(f"⏳ Señal activa. Próximo análisis en {mins} min {segs} seg...")
                time.sleep(1)
                st.rerun()
        else:
            # No hay señal, buscar la mejor oportunidad
            if not st.session_state.activos_totales:
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
            if not st.session_state.activos_totales:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_entre_ciclos)
                st.rerun()

            # Analizar un lote de activos (por ejemplo, 20 cada vez)
            activos = st.session_state.activos_totales
            inicio = st.session_state.indice_ronda * 20
            fin = inicio + 20
            lote = activos[inicio:fin]
            if not lote:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"🔍 Analizando lote {st.session_state.indice_ronda + 1} ({len(lote)} activos)...")
            mejor = seleccionar_mejor_activo(st.session_state.api, lote)
            st.session_state.indice_ronda += 1

            if mejor and mejor['fuerza'] >= umbral_fuerza:
                entrada = now + timedelta(seconds=anticipacion)
                entrada_str = entrada.strftime("%H:%M:%S")
                vencimiento_str = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                st.session_state.senal_activa = {
                    'asset': mejor['asset'],
                    'direccion': mejor['direccion'],
                    'estrategias': mejor['estrategias'],
                    'fuerza': mejor['fuerza'],
                    'entrada': entrada_str,
                    'vencimiento': vencimiento_str
                }
                st.session_state.log.append(f"🚀 SEÑAL: {mejor['asset']} - {mejor['direccion']} a las {entrada_str} (Fuerza: {mejor['fuerza']:.1f}%)")
                st.session_state.log.append(f"   Estrategias: {', '.join(mejor['estrategias'])}")
            else:
                st.session_state.log.append("🔍 No se encontraron señales en este lote.")

            time.sleep(pausa_entre_ciclos)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")
