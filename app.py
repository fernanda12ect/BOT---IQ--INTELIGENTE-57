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
    detectar_punto_entrada,
    REAL_ASSETS,
    OTC_ASSETS
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - ESTRATEGIA DE TENDENCIA CON PUNTO DE ENTRADA")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'tarjetas' not in st.session_state:
    st.session_state.tarjetas = []  # Lista de dicts: {asset, direccion, fuerza, estrategia, estado, entry_time (cuando se activa), expiry_time, timestamp_inicio}
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

    # Umbral de fuerza mínima para considerar un activo como candidato
    umbral_fuerza = st.slider("🎯 Fuerza mínima para candidato (%)", 0, 100, 50, 5)

    # Número máximo de tarjetas
    max_tarjetas = 4

    # Tiempo de espera entre rondas completas (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", min_value=5, max_value=120, value=20)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    if st.session_state.api is not None and not st.session_state.escaneando:
        if st.button("▶️ Iniciar escaneo"):
            real, otc = obtener_activos_abiertos(st.session_state.api)
            st.session_state.activos_reales = real
            st.session_state.activos_otc = otc
            st.session_state.activos_a_escanear = real + otc
            st.session_state.indice_activo = 0
            st.session_state.historial = []
            st.session_state.tarjetas = []
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
                st.session_state.tarjetas = []
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
    st.session_state.tarjetas = []
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

    # --- SECCIÓN DE TARJETAS ACTIVAS ---
    st.subheader(f"📊 Tarjetas de monitoreo (máx {max_tarjetas})")

    # Eliminar tarjetas cuyo vencimiento ya pasó (por si acaso)
    now = datetime.now(ecuador)
    tarjetas_vigentes = []
    for tarj in st.session_state.tarjetas:
        if tarj['estado'] == "ACTIVA" and tarj.get('expiry_time') and tarj['expiry_time'] < now:
            st.session_state.historial.append(f"🗑️ Operación finalizada: {tarj['asset']}")
            continue
        tarjetas_vigentes.append(tarj)
    st.session_state.tarjetas = tarjetas_vigentes

    # Mostrar tarjetas
    if st.session_state.tarjetas:
        # Ordenar por fuerza descendente (las más fuertes primero)
        tarjetas_ordenadas = sorted(st.session_state.tarjetas, key=lambda x: x['fuerza'], reverse=True)
        cols = st.columns(len(tarjetas_ordenadas))
        for idx, tarj in enumerate(tarjetas_ordenadas):
            with cols[idx]:
                asset = tarj['asset']
                if "-OTC" in asset:
                    tipo_mostrar = "📱 OTC"
                    asset_clean = asset.replace("-OTC", "")
                else:
                    tipo_mostrar = "🌍 REAL"
                    asset_clean = asset

                color = "#006400" if tarj['direccion'] == "CALL" else "#8B0000"
                estado_texto = tarj['estado']
                if estado_texto == "NEUTRO":
                    estado_color = "#888"
                    estado_emoji = "⚪"
                elif estado_texto == "COMPRAR AHORA":
                    estado_color = "#00FF00"
                    estado_emoji = "🟢"
                elif estado_texto == "VENDER AHORA":
                    estado_color = "#FF0000"
                    estado_emoji = "🔴"
                else:
                    estado_color = "#888"
                    estado_emoji = "⚪"

                # Mostrar hora de entrada si está activa
                if estado_texto == "COMPRAR AHORA" or estado_texto == "VENDER AHORA":
                    hora_entrada = tarj['entry_time'].strftime("%H:%M:%S")
                    hora_expiry = tarj['expiry_time'].strftime("%H:%M:%S")
                    info_tiempo = f"Entrada: {hora_entrada} | Expira: {hora_expiry}"
                else:
                    info_tiempo = "Esperando punto de entrada..."

                html_code = f"""
                <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                    <h3 style="margin:0;">{asset_clean} {tipo_mostrar}</h3>
                    <p style="color:{color}; font-size:1.5rem; margin:5px 0;">{tarj['direccion']}</p>
                    <p><strong>Estrategia:</strong> {tarj['estrategia']}</p>
                    <p><strong>Fuerza:</strong> {tarj['fuerza']}%</p>
                    <p><strong>Estado:</strong> <span style="color:{estado_color};">{estado_emoji} {estado_texto}</span></p>
                    <p><small>{info_tiempo}</small></p>
                </div>
                """
                st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.info("No hay activos siendo monitoreados.")

    # Historial de análisis
    if st.session_state.historial:
        with st.expander("📋 Historial de análisis", expanded=False):
            for linea in st.session_state.historial[-20:]:
                st.text(linea)

    # Lógica de escaneo continuo
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
                señales = evaluar_estrategias(indicators)

                # Si hay señales, tomar la de mayor fuerza
                mejor_senal = None
                if señales:
                    mejor_senal = max(señales, key=lambda x: x['fuerza'])

                # Verificar si el activo ya está en las tarjetas
                tarjeta_existente = next((t for t in st.session_state.tarjetas if t['asset'] == asset), None)

                # Si hay una señal fuerte y el activo no está en tarjetas, y tenemos espacio, añadirlo
                if mejor_senal and mejor_senal['fuerza'] >= umbral_fuerza:
                    if not tarjeta_existente:
                        if len(st.session_state.tarjetas) < max_tarjetas:
                            # Añadir nueva tarjeta en estado NEUTRO
                            nueva_tarjeta = {
                                "asset": asset,
                                "direccion": mejor_senal['direccion'],
                                "fuerza": mejor_senal['fuerza'],
                                "estrategia": mejor_senal['estrategia'],
                                "estado": "NEUTRO",
                                "entry_time": None,
                                "expiry_time": None
                            }
                            st.session_state.tarjetas.append(nueva_tarjeta)
                            st.session_state.historial.append(f"➕ Nuevo monitoreo: {asset} (fuerza {mejor_senal['fuerza']}%)")
                        else:
                            # Si no hay espacio, reemplazar la de menor fuerza si la nueva es más fuerte
                            tarjeta_menor = min(st.session_state.tarjetas, key=lambda x: x['fuerza'])
                            if mejor_senal['fuerza'] > tarjeta_menor['fuerza']:
                                st.session_state.tarjetas.remove(tarjeta_menor)
                                nueva_tarjeta = {
                                    "asset": asset,
                                    "direccion": mejor_senal['direccion'],
                                    "fuerza": mejor_senal['fuerza'],
                                    "estrategia": mejor_senal['estrategia'],
                                    "estado": "NEUTRO",
                                    "entry_time": None,
                                    "expiry_time": None
                                }
                                st.session_state.tarjetas.append(nueva_tarjeta)
                                st.session_state.historial.append(f"🔄 Reemplazado {tarjeta_menor['asset']} por {asset} (fuerza {mejor_senal['fuerza']}%)")
                    else:
                        # El activo ya está en tarjetas, actualizar su fuerza y estrategia (si ha cambiado)
                        if mejor_senal['fuerza'] != tarjeta_existente['fuerza'] or mejor_senal['estrategia'] != tarjeta_existente['estrategia']:
                            tarjeta_existente['fuerza'] = mejor_senal['fuerza']
                            tarjeta_existente['estrategia'] = mejor_senal['estrategia']
                            st.session_state.historial.append(f"🔄 Actualizada fuerza de {asset}: {mejor_senal['fuerza']}%")
                else:
                    # No hay señal fuerte para este activo
                    if tarjeta_existente:
                        # Si el activo está en tarjetas pero ya no cumple, eliminarlo
                        st.session_state.tarjetas.remove(tarjeta_existente)
                        st.session_state.historial.append(f"❌ Eliminado {asset} (dejó de cumplir)")

                # Ahora, para cada tarjeta activa, verificar si se ha alcanzado el punto de entrada
                for tarj in st.session_state.tarjetas:
                    if tarj['estado'] == "NEUTRO":
                        # Necesitamos los indicadores actuales de ese activo (podríamos tener que obtenerlos de nuevo)
                        # Para simplificar, asumimos que el activo actual es el que estamos analizando y si coincide, usamos indicators
                        if tarj['asset'] == asset:
                            punto_entrada, mensaje = detectar_punto_entrada(indicators, tarj['direccion'])
                            if punto_entrada:
                                # Cambiar estado a COMPRAR/VENDER AHORA y fijar tiempos
                                now_utc = datetime.now(pytz.UTC)
                                entry_dt = now_utc + timedelta(minutes=1)  # Entrada en 1 minuto (tiempo para prepararse)
                                entry_dt = entry_dt.replace(second=0, microsecond=0)
                                expiry_dt = entry_dt + timedelta(minutes=5)
                                entry_local = entry_dt.astimezone(ecuador)
                                expiry_local = expiry_dt.astimezone(ecuador)
                                tarj['estado'] = "COMPRAR AHORA" if tarj['direccion'] == "CALL" else "VENDER AHORA"
                                tarj['entry_time'] = entry_local
                                tarj['expiry_time'] = expiry_local
                                st.session_state.historial.append(f"🎯 Señal de entrada en {asset}: {tarj['estado']} a las {entry_local.strftime('%H:%M:%S')}")
                        else:
                            # No tenemos los indicadores ahora, se evaluará cuando ese activo sea escaneado
                            pass

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
