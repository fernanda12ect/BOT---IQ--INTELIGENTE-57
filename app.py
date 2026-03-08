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
    st.session_state.señales_activas = []  # Lista de dicts con señal + timestamps
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

    # Umbral de fuerza mínima para considerar una señal (se puede bajar para obtener más señales)
    umbral_fuerza = st.slider("🎯 Fuerza mínima para mostrar (%)", 0, 100, 30, 5)

    # Número máximo de tarjetas a mostrar
    max_tarjetas = 4

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

    # --- SECCIÓN DE SEÑALES ACTIVAS (hasta 4 tarjetas) ---
    st.subheader(f"📊 Señales activas (máx {max_tarjetas})")

    # Eliminar señales cuyo tiempo de entrada ya pasó (por si acaso no se actualizaron)
    now = datetime.now(ecuador)
    señales_vigentes = []
    for senal in st.session_state.señales_activas:
        if senal['entry_time'] > now:
            señales_vigentes.append(senal)
        else:
            st.session_state.historial.append(f"🗑️ Señal expirada: {senal['asset']} (hora pasada)")
    st.session_state.señales_activas = señales_vigentes

    # Mostrar tarjetas
    if st.session_state.señales_activas:
        # Ordenar por fuerza descendente
        señales_ordenadas = sorted(st.session_state.señales_activas, key=lambda x: x['fuerza'], reverse=True)[:max_tarjetas]
        cols = st.columns(len(señales_ordenadas))
        for idx, senal in enumerate(señales_ordenadas):
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
                estado = "🔵 EN ESPERA" if senal['entry_time'] > now else "🟢 LISTO PARA OPERAR"
                # Calcular tiempo restante
                tiempo_restante = (senal['entry_time'] - now).total_seconds()
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

                # Determinar la mejor señal para este activo (la de mayor fuerza)
                mejor_senal = None
                if señales_encontradas:
                    mejor_senal = max(señales_encontradas, key=lambda x: x['fuerza'])

                # Obtener hora actual del servidor para calcular tiempos
                try:
                    server_time = st.session_state.api.get_server_time()
                    now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                except:
                    now_utc = datetime.now(pytz.UTC)

                # Calcular tiempos de entrada y expiración (1 minuto después, vencimiento 5 min)
                entry_dt = now_utc + timedelta(minutes=1)
                entry_dt = entry_dt.replace(second=0, microsecond=0)
                expiry_dt = entry_dt + timedelta(minutes=5)

                entry_local = entry_dt.astimezone(ecuador)
                expiry_local = expiry_dt.astimezone(ecuador)

                # Verificar si el activo ya tiene una señal activa
                señal_existente = next((s for s in st.session_state.señales_activas if s['asset'] == asset), None)

                if mejor_senal and mejor_senal['fuerza'] >= umbral_fuerza:
                    # Hay señal válida
                    nueva_senal = {
                        "asset": asset,
                        "direccion": mejor_senal['direccion'],
                        "fuerza": mejor_senal['fuerza'],
                        "estrategia": mejor_senal['estrategia'],
                        "entry": entry_local.strftime("%H:%M:%S"),
                        "expiry": expiry_local.strftime("%H:%M:%S"),
                        "entry_time": entry_local,
                        "expiry_time": expiry_local
                    }

                    if señal_existente:
                        # Actualizar la señal existente (si la fuerza es diferente o misma)
                        st.session_state.señales_activas.remove(señal_existente)
                        st.session_state.señales_activas.append(nueva_senal)
                        st.session_state.historial.append(f"🔄 Actualizada señal en {asset} (fuerza {mejor_senal['fuerza']}%)")
                    else:
                        # Añadir nueva señal
                        st.session_state.señales_activas.append(nueva_senal)
                        st.session_state.historial.append(f"🎯 Nueva señal en {asset}: {mejor_senal['estrategia']} ({mejor_senal['fuerza']}%)")
                else:
                    # No hay señal válida para este activo
                    if señal_existente:
                        # Eliminar la señal existente porque ya no cumple
                        st.session_state.señales_activas.remove(señal_existente)
                        st.session_state.historial.append(f"❌ Señal eliminada: {asset} (dejó de cumplir)")

                # Después de modificar las señales, ordenar y limitar a las 4 más fuertes
                st.session_state.señales_activas = sorted(st.session_state.señales_activas, key=lambda x: x['fuerza'], reverse=True)[:max_tarjetas]

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
