import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_tendencia,
    calcular_nivel_retroceso
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - SEGUIMIENTO DE 2 ACTIVOS CON RETROCESO")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'fase' not in st.session_state:
    st.session_state.fase = "seleccion"  # "seleccion" o "seguimiento"
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []  # Lista de dicts con info del activo en seguimiento
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []  # Solo cuando se confirma la entrada
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    # Umbral de fuerza mínima para considerar tendencia
    umbral_fuerza = st.slider("🎯 Fuerza mínima de tendencia", 0, 100, 40, 5)

    # Tiempo de espera entre rondas de escaneo (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas", 5, 120, 15)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    if st.session_state.api is not None and not st.session_state.escaneando:
        if st.button("▶️ Iniciar búsqueda"):
            st.session_state.escaneando = True
            st.session_state.fase = "seleccion"
            st.session_state.activos_seleccionados = []
            st.session_state.señales_activas = []
            st.session_state.historial = []
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
                st.session_state.escaneando = False
                st.success("✅ Conectado")
            else:
                st.error(f"❌ Error: {reason}")
        except Exception as e:
            st.error(f"Error: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.escaneando = False
    st.session_state.activos_seleccionados = []
    st.session_state.señales_activas = []
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    real_count = len(st.session_state.activos_reales)
    otc_count = len(st.session_state.activos_otc)
    if real_count > 0:
        st.success(f"🌍 REAL: {real_count} | 📱 OTC: {otc_count}")
    else:
        st.warning(f"⚠️ Solo OTC ({otc_count})")

    # Mostrar señales activas (solo cuando están listas)
    if st.session_state.señales_activas:
        st.subheader("📊 SEÑALES LISTAS PARA OPERAR")
        for senal in st.session_state.señales_activas:
            asset = senal['asset']
            if "-OTC" in asset:
                tipo = "📱 OTC"
                asset_clean = asset.replace("-OTC", "")
            else:
                tipo = "🌍 REAL"
                asset_clean = asset
            color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"

            html_code = f"""
            <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                <h3>{asset_clean} {tipo}</h3>
                <p style="color:{color}; font-size:2rem;">{senal['direccion']}</p>
                <p><strong>Entrada:</strong> {senal['entry']}</p>
                <p><strong>Expira:</strong> {senal['expiry']}</p>
                <p><strong>Estrategia:</strong> {senal['estrategia']}</p>
                <p style="color:#0f0;">✅ LISTO PARA OPERAR</p>
            </div>
            """
            st.markdown(html_code, unsafe_allow_html=True)

    # Historial
    if st.session_state.historial:
        with st.expander("📋 Historial", expanded=True):
            for linea in st.session_state.historial[-20:]:
                st.text(linea)

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        now = datetime.now(ecuador)

        # FASE DE SELECCIÓN: buscar los 2 mejores activos con tendencia
        if st.session_state.fase == "seleccion":
            st.info("🔍 Buscando los 2 mejores activos con tendencia...")
            # Escanear todos los activos (reales + otc)
            todos_activos = st.session_state.activos_reales + st.session_state.activos_otc
            candidatos = []
            for asset in todos_activos:
                try:
                    candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles or len(candles) < 50:
                        continue
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) < 50:
                        continue
                    indicators = calcular_indicadores(df)
                    res = evaluar_tendencia(indicators)
                    if res:
                        direccion, fuerza = res
                        if fuerza >= umbral_fuerza:
                            # Calcular nivel de retroceso
                            nivel = calcular_nivel_retroceso(indicators['df'], direccion)
                            candidatos.append({
                                'asset': asset,
                                'direccion': direccion,
                                'fuerza': fuerza,
                                'nivel_retroceso': nivel,
                                'precio_actual': indicators['close'],
                                'indicators': indicators
                            })
                except Exception as e:
                    continue
                time.sleep(0.1)  # pausa entre activos

            if candidatos:
                # Ordenar por fuerza y tomar los 2 mejores
                candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                st.session_state.activos_seleccionados = candidatos[:2]
                st.session_state.fase = "seguimiento"
                st.session_state.historial.append(f"✅ Seleccionados: {candidatos[0]['asset']} ({candidatos[0]['fuerza']:.1f}%) y {candidatos[1]['asset']} ({candidatos[1]['fuerza']:.1f}%)")
                # Pequeña pausa antes de empezar seguimiento
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.historial.append("⚠️ No se encontraron activos con tendencia suficiente. Reintentando...")
                time.sleep(pausa_entre_rondas)
                st.rerun()

        # FASE DE SEGUIMIENTO: monitorear los 2 activos seleccionados
        elif st.session_state.fase == "seguimiento":
            st.subheader("🔎 SIGUIENDO ACTIVOS SELECCIONADOS")
            for idx, activo in enumerate(st.session_state.activos_seleccionados):
                asset = activo['asset']
                st.write(f"**{idx+1}. {asset}** - Tendencia: {activo['direccion']} - Nivel retroceso: {activo['nivel_retroceso']:.5f}")

                try:
                    candles = st.session_state.api.get_candles(asset, 60, 5, time.time())  # últimas 5 velas
                    if not candles:
                        continue
                    df = pd.DataFrame(candles)
                    precio_actual = df['close'].iloc[-1]
                    activo['precio_actual'] = precio_actual

                    # Verificar si se alcanzó el nivel de retroceso (con tolerancia)
                    direccion = activo['direccion']
                    nivel = activo['nivel_retroceso']
                    if direccion == "CALL":
                        # En tendencia alcista, esperamos que el precio baje hasta el nivel
                        if precio_actual <= nivel * 1.001:  # tolerancia 0.1%
                            # Generar señal
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

                            señal = {
                                'asset': asset,
                                'direccion': 'CALL',
                                'entry': entry_local.strftime("%H:%M:%S"),
                                'expiry': expiry_local.strftime("%H:%M:%S"),
                                'estrategia': 'Retroceso alcanzado',
                                'fuerza': activo['fuerza']
                            }
                            st.session_state.señales_activas.append(señal)
                            st.session_state.historial.append(f"🎯 Señal CALL para {asset} a las {entry_local.strftime('%H:%M:%S')}")
                            # Eliminar este activo de la lista de seguimiento
                            st.session_state.activos_seleccionados.pop(idx)
                            break
                    else:  # PUT
                        if precio_actual >= nivel * 0.999:
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

                            señal = {
                                'asset': asset,
                                'direccion': 'PUT',
                                'entry': entry_local.strftime("%H:%M:%S"),
                                'expiry': expiry_local.strftime("%H:%M:%S"),
                                'estrategia': 'Retroceso alcanzado',
                                'fuerza': activo['fuerza']
                            }
                            st.session_state.señales_activas.append(señal)
                            st.session_state.historial.append(f"🎯 Señal PUT para {asset} a las {entry_local.strftime('%H:%M:%S')}")
                            st.session_state.activos_seleccionados.pop(idx)
                            break
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error monitoreando {asset}: {str(e)[:50]}")

            # Si ya no hay activos en seguimiento, volver a fase de selección
            if len(st.session_state.activos_seleccionados) == 0:
                st.session_state.fase = "seleccion"
                st.rerun()
            else:
                time.sleep(pausa_entre_rondas)
                st.rerun()

else:
    st.warning("🔒 Conéctate primero desde el panel izquierdo.")
