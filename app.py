import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    seleccionar_mejores_activos,
    evaluar_activo
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("📈 GENERADOR DE SEÑALES M5 - SELECCIÓN AUTOMÁTICA DE ACTIVOS")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []  # los que el bot elige
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'señales' not in st.session_state:
    st.session_state.señales = []  # lista de dicts con señal, timestamp
if 'historial_señales' not in st.session_state:
    st.session_state.historial_señales = []
if 'indice_activo' not in st.session_state:
    st.session_state.indice_activo = 0
if 'ultima_ejecucion' not in st.session_state:
    st.session_state.ultima_ejecucion = None
if 'log' not in st.session_state:
    st.session_state.log = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Función para añadir señal
def añadir_señal(asset, direccion, estrategia):
    now = datetime.now(ecuador)
    # La entrada se estima al inicio de la siguiente vela M1 (aproximadamente 30-50 segundos)
    entrada_estimada = now + timedelta(minutes=1)
    entrada_estimada = entrada_estimada.replace(second=0, microsecond=0)
    tiempo_restante = (entrada_estimada - now).total_seconds()
    señal = {
        'activo': asset,
        'direccion': direccion,
        'estrategia': estrategia,
        'entrada': entrada_estimada.strftime("%H:%M:%S"),
        'tiempo_restante': f"{int(tiempo_restante)}s",
        'timestamp': now
    }
    st.session_state.señales.insert(0, señal)  # la más reciente al principio
    st.session_state.señales = st.session_state.señales[:20]  # mantener solo últimas 20
    st.session_state.historial_señales.append(señal)
    st.session_state.log.append(f"📊 SEÑAL: {asset} - {direccion} ({estrategia}) a las {entrada_estimada.strftime('%H:%M:%S')}")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    st.divider()
    max_activos = st.slider("🎯 Número máximo de activos a seguir", 5, 30, 10, 5)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    st.divider()
    if st.session_state.api is not None:
        if not st.session_state.escaneando:
            iniciar = st.button("▶️ INICIAR MONITOREO")
            if iniciar:
                # Seleccionar automáticamente los mejores activos
                with st.spinner("Seleccionando los mejores activos..."):
                    todos_activos = st.session_state.activos_reales + st.session_state.activos_otc
                    seleccionados = seleccionar_mejores_activos(st.session_state.api, todos_activos, max_activos)
                    st.session_state.activos_seleccionados = seleccionados
                    st.session_state.log.append(f"✅ Seleccionados {len(seleccionados)} activos: {', '.join(seleccionados[:5])}...")
                st.session_state.escaneando = True
                st.session_state.indice_activo = 0
                st.rerun()
        else:
            detener = st.button("⏹️ DETENER MONITOREO")
            if detener:
                st.session_state.escaneando = False
                st.rerun()

# Lógica de conexión
if conectar:
    if not email or not password:
        st.error("❌ Ingresa email y password")
    else:
        try:
            API = IQ_Option(email, password)
            check, reason = API.connect()
            if check:
                st.session_state.api = API
                real, otc = obtener_activos_abiertos(API)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.activos_seleccionados = []
                st.session_state.escaneando = False
                st.session_state.log.append("✅ Conectado")
                st.success("Conectado")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.activos_seleccionados = []
    st.session_state.escaneando = False
    st.session_state.log.append("🔌 Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    st.info(f"📊 Modo: Generador de señales | Activos en seguimiento: {len(st.session_state.activos_seleccionados)}")

    # Mostrar los activos seleccionados (para que el usuario pueda abrir sus gráficos)
    if st.session_state.activos_seleccionados:
        with st.expander("📌 Activos seleccionados automáticamente"):
            st.write("Los siguientes activos son los más prometedores según el análisis del bot:")
            cols = st.columns(3)
            for i, asset in enumerate(st.session_state.activos_seleccionados):
                cols[i % 3].write(f"- {asset}")

    # Mostrar señales activas (la más reciente primero)
    st.subheader("🚀 SEÑALES ACTIVAS (próxima vela)")
    if st.session_state.señales:
        cols = st.columns(2)
        for idx, señal in enumerate(st.session_state.señales[:6]):  # mostrar hasta 6
            with cols[idx % 2]:
                color = "#006400" if señal['direccion'] == "CALL" else "#8B0000"
                html_code = f"""
                <div style="background:#111; padding:15px; border-radius:10px; border:3px solid {color}; margin-bottom:10px;">
                    <h4>{señal['activo']} 📱</h4>
                    <p style="color:{color}; font-size:1.8rem;">{señal['direccion']}</p>
                    <p><strong>Estrategia:</strong> {señal['estrategia']}</p>
                    <p><strong>Entrada:</strong> {señal['entrada']}</p>
                    <p><strong>⏳ {señal['tiempo_restante']}</strong></p>
                </div>
                """
                st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.info("No hay señales activas.")

    # Historial de señales
    with st.expander("📋 Historial de señales"):
        if st.session_state.historial_señales:
            df_hist = pd.DataFrame(st.session_state.historial_señales[-50:])
            st.dataframe(df_hist[['activo', 'direccion', 'estrategia', 'entrada', 'timestamp']], width='stretch')
        else:
            st.info("Sin historial.")

    # Log de eventos
    with st.expander("📋 Log"):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Monitoreo continuo
    if st.session_state.escaneando and st.session_state.activos_seleccionados:
        activos = st.session_state.activos_seleccionados
        total = len(activos)

        # Rotación secuencial
        idx = st.session_state.indice_activo
        asset = activos[idx % total]
        st.info(f"🔄 Analizando {asset} ({idx+1}/{total})...")

        try:
            resultado = evaluar_activo(st.session_state.api, asset)
            if resultado:
                direccion, estrategia = resultado
                añadir_señal(asset, direccion, estrategia)
                # Después de una señal, esperamos un poco para no saturar (simula pausa humana)
                time.sleep(5)
        except Exception as e:
            st.session_state.log.append(f"⚠️ Error con {asset}: {str(e)[:50]}")

        # Avanzar al siguiente activo
        st.session_state.indice_activo = (idx + 1) % total
        # Pequeña pausa entre activos para no sobrecargar API
        time.sleep(2)
        st.rerun()

    elif not st.session_state.activos_seleccionados and st.session_state.escaneando:
        st.warning("No se pudo seleccionar ningún activo. Reintentando...")
        st.session_state.escaneando = False

else:
    st.warning("🔒 Conéctate primero.")
