import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_estrategias,
    REAL_ASSETS,
    OTC_ASSETS
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - 4 ESTRATEGIAS DE 5 MINUTOS")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []  # Lista de dicts con señal + timestamp
if 'cooldown_until' not in st.session_state:
    st.session_state.cooldown_until = None
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'indice_activo' not in st.session_state:
    st.session_state.indice_activo = 0
if 'activos_a_escanear' not in st.session_state:
    st.session_state.activos_a_escanear = []
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    # Umbral de fuerza mínima para mostrar señal (ajustable)
    umbral_fuerza = st.slider("🎯 Fuerza mínima de señal (%)", 0, 100, 50, 5)

    # Tiempo de espera entre rondas completas (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", min_value=5, max_value=120, value=20)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    if st.session_state.api is not None and not st.session_state.escaneando:
        if st.button("▶️ Reiniciar escaneo"):
            real, otc = obtener_activos_abiertos(st.session_state.api)
            st.session_state.activos_reales = real
            st.session_state.activos_otc = otc
            st.session_state.activos_a_escanear = real + otc
            st.session_state.indice_activo = 0
            st.session_state.historial = []
            st.session_state.señales_activas = []
            st.session_state.escaneando = True
            st.rerun()

# Lógica de conexión
if conectar:
    if not email or not password:
        st.error("❌ Por favor ingresa email y password")
    else:
        try:
            API = IQ_Option(email, password)
            check, reason = API.connect()
            if check:
                st.session_state.api = API
                # Obtener activos
                real, otc = obtener_activos_abiertos(API)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.activos_a_escanear = real + otc
                st.session_state.indice_activo = 0
                st.session_state.historial = []
                st.session_state.señales_activas = []
                st.session_state.escaneando = True
                st.success("✅ Conectado - Escaneo iniciado")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.activos_reales = []
    st.session_state.activos_otc = []
    st.session_state.activos_a_escanear = []
    st.session_state.indice_activo = 0
    st.session_state.historial = []
    st.session_state.señales_activas = []
    st.session_state.escaneando = False
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    st.info("🔌 Conectado.")

    # Mostrar estado del mercado
    real_count = len(st.session_state.activos_reales)
    otc_count = len(st.session_state.activos_otc)
    if real_count > 0:
        st.success(f"🌍 REAL: {real_count} | 📱 OTC: {otc_count}")
    else:
        st.warning(f"⚠️ Mercado REAL cerrado - Solo OTC ({otc_count} disponibles)")

    # --- SECCIÓN DE SEÑALES ACTIVAS (hasta 3 tarjetas) ---
    st.subheader("📊 Señales activas (máx 3)")

    # Eliminar señales que ya expiraron (hora actual > hora de entrada)
    now = datetime.now(ecuador)
    señales_vigentes = []
    for senal in st.session_state.señales_activas:
        # Asegurar que 'entry_time' es datetime con zona horaria
        if isinstance(senal['entry_time'], str):
            # Si por alguna razón se guardó como string, convertir
            hora_entrada = datetime.strptime(senal['entry_time'], "%Y-%m-%d %H:%M:%S%z")
        else:
            hora_entrada = senal['entry_time']
        if hora_entrada > now:
            señales_vigentes.append(senal)
        else:
            st.session_state.historial.append(f"🗑️ Señal expirada: {senal['asset']}")

    # Ordenar por fuerza descendente
    señales_vigentes.sort(key=lambda x: x['fuerza'], reverse=True)
    # Mantener solo las 3 mejores
    st.session_state.señales_activas = señales_vigentes[:3]

    # Mostrar tarjetas
    if st.session_state.señales_activas:
        cols = st.columns(len(st.session_state.señales_activas))
        for idx, senal in enumerate(st.session_state.señales_activas):
            with cols[idx]:
                # Determinar tipo de activo
                asset = senal['asset']
                if "-OTC" in asset:
                    tipo_mostrar = "📱 OTC"
                    asset_clean = asset.replace("-OTC", "")
                else:
                    tipo_mostrar = "🌍 REAL"
                    asset_clean = asset

                color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"
                # Calcular estado
                if isinstance(senal['entry_time'], str):
                    entry_time = datetime.strptime(senal['entry_time'], "%Y-%m-%d %H:%M:%S%z")
                else:
                    entry_time = senal['entry_time']
                estado = "🔵 EN ESPERA" if entry_time > now else "🟢 LISTO PARA OPERAR"
                # Calcular tiempo restante
                tiempo_restante = (entry_time - now).total_seconds()
                if tiempo_restante > 0:
                    mins, secs = divmod(int(tiempo_restante), 60)
                    countdown = f"{mins}m {secs}s"
                else:
                    countdown = "¡YA!"

                # Escapar para HTML
                asset_display = html.escape(f"{asset_clean} {tipo_mostrar}")
                direccion = html.escape(senal['direccion'])
                estrategia = html.escape(senal['estrategia'])
                entry = html.escape(senal['entry'])
                expiry = html.escape(senal['expiry'])
                fuerza = html.escape(str(senal['fuerza']))

                html_code = f"""
                <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                    <h3 style="margin:0;">{asset_display}</h3>
                    <p style="color:{color}; font-size:1.5rem; margin:5px 0;">{direccion}</p>
                    <p><strong>Estrategia:</strong> {estrategia}</p>
                    <p><strong>Fuerza:</strong> {fuerza}%</p>
                    <p><strong>Entrada:</strong> {entry}</p>
                    <p><strong>Expira:</strong> {expiry}</p>
                    <p><strong>Estado:</strong> {estado} ({countdown})</p>
                </div>
                """
                st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.info("No hay señales activas en este momento.")

    # Historial de análisis
    if st.session_state.historial:
        with st.expander("📋 Historial de análisis", expanded=False):
            for linea in st.session_state.historial[-20:]:
                st.text(linea)

    # Lógica de escaneo continuo (solo si está escaneando)
    if st.session_state.escaneando:
        # Si no hay activos cargados o se terminó la lista, cargar nueva ronda
        if not st.session_state.activos_a_escanear or st.session_state.indice_activo >= len(st.session_state.activos_a_escanear):
            # Obtener activos actualizados
            real, otc = obtener_activos_abiertos(st.session_state.api)
            st.session_state.activos_reales = real
            st.session_state.activos_otc = otc
            st.session_state.activos_a_escanear = real + otc
            st.session_state.indice_activo = 0
            st.session_state.historial.append(f"🔄 Nueva ronda: {len(st.session_state.activos_a_escanear)} activos")
            if st.session_state.activos_a_escanear:
                st.info(f"Esperando {pausa_entre_rondas} segundos para nueva ronda...")
                time.sleep(pausa_entre_rondas)
                st.rerun()
            else:
                st.warning("No hay activos disponibles.")
                st.session_state.escaneando = False
                st.rerun()
        else:
            # Escanear el activo actual
            asset = st.session_state.activos_a_escanear[st.session_state.indice_activo]
            tipo = "🌍 REAL" if "-OTC" not in asset else "📱 OTC"
            st.markdown(f"### 🔍 Analizando: {tipo} {asset}")

            try:
                # Añadir al historial
                st.session_state.historial.append(f"{tipo} Analizando {asset}...")

                candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                if not candles or len(candles) < 50:
                    st.session_state.historial.append(f"⏭️ {asset}: datos insuficientes")
                    time.sleep(0.25)
                    st.session_state.indice_activo += 1
                    st.rerun()

                df = pd.DataFrame(candles)
                for col in ['open', 'max', 'min', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df.dropna(inplace=True)

                if len(df) < 50:
                    st.session_state.historial.append(f"⏭️ {asset}: datos insuficientes después de limpieza")
                    time.sleep(0.25)
                    st.session_state.indice_activo += 1
                    st.rerun()

                # Calcular indicadores
                indicators = calcular_indicadores(df)
                señales_encontradas = evaluar_estrategias(indicators)

                if señales_encontradas:
                    for senal in señales_encontradas:
                        # Añadir info del activo y tiempos
                        # Obtener hora servidor
                        try:
                            server_time = st.session_state.api.get_server_time()
                            now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                        except:
                            now_utc = datetime.now(pytz.UTC)

                        entry_dt = now_utc + timedelta(minutes=1)
                        entry_dt = entry_dt.replace(second=0, microsecond=0)
                        expiry_dt = entry_dt + timedelta(minutes=5)

                        entry_local = entry_dt.astimezone(ecuador)
                        expiry_local = expiry_dt.astimezone(ecuador)

                        señal_completa = {
                            "asset": asset,
                            "direccion": senal['direccion'],
                            "fuerza": senal['fuerza'],
                            "estrategia": senal['estrategia'],
                            "entry": entry_local.strftime("%H:%M:%S"),
                            "expiry": expiry_local.strftime("%H:%M:%S"),
                            "entry_time": entry_local,  # datetime con zona
                            "expiry_time": expiry_local
                        }

                        # Si la fuerza supera el umbral, considerar agregar a señales activas
                        if senal['fuerza'] >= umbral_fuerza:
                            # Verificar si ya existe una señal para este activo
                            existente = next((s for s in st.session_state.señales_activas if s['asset'] == asset), None)
                            if existente:
                                # Reemplazar si la nueva es más fuerte
                                if senal['fuerza'] > existente['fuerza']:
                                    st.session_state.señales_activas.remove(existente)
                                    st.session_state.señales_activas.append(señal_completa)
                                    st.session_state.historial.append(f"🔄 Actualizada señal en {asset} (fuerza {senal['fuerza']}%)")
                            else:
                                # Añadir nueva señal
                                st.session_state.señales_activas.append(señal_completa)
                                st.session_state.historial.append(f"🎯 Nueva señal en {asset}: {senal['estrategia']} ({senal['fuerza']}%)")

                # Avanzar al siguiente activo
                time.sleep(0.25)
                st.session_state.indice_activo += 1
                st.rerun()

            except Exception as e:
                st.session_state.historial.append(f"⚠️ Error en {asset}: {str(e)[:50]}")
                time.sleep(0.25)
                st.session_state.indice_activo += 1
                st.rerun()

else:
    st.warning("🔒 Por favor, conéctate primero desde el panel izquierdo.")
