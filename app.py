import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_activo
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - SEGUIMIENTO DE 6 ACTIVOS CONFIABLES")

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
if 'activos_seguimiento' not in st.session_state:
    st.session_state.activos_seguimiento = []  # Lista de dicts con info de los 6 activos
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []  # Lista de señales confirmadas
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

    # Número de activos a seguir
    NUM_ACTIVOS = 6

    # Tiempo de espera entre rondas de escaneo (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas", 5, 120, 10)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

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
                st.session_state.escaneando = True
                st.session_state.fase = "seleccion"
                st.session_state.activos_seguimiento = []
                st.session_state.señales_activas = []
                st.session_state.historial = []
                st.success("✅ Conectado - Iniciando búsqueda de activos...")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.escaneando = False
    st.session_state.activos_seguimiento = []
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

    # --- SECCIÓN DE SEÑALES ACTIVAS (tarjetas) ---
    if st.session_state.señales_activas:
        st.subheader(f"📊 SEÑALES LISTAS PARA OPERAR ({len(st.session_state.señales_activas)})")
        # Mostrar en cuadrícula de 2 columnas
        cols = st.columns(2)
        for idx, senal in enumerate(st.session_state.señales_activas):
            with cols[idx % 2]:
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

    # --- SECCIÓN DE ACTIVOS EN SEGUIMIENTO ---
    if st.session_state.activos_seguimiento:
        st.subheader(f"🔎 ACTIVOS EN SEGUIMIENTO ({len(st.session_state.activos_seguimiento)})")
        # Tabla o lista con los datos
        data = []
        for activo in st.session_state.activos_seguimiento:
            niveles = activo.get('niveles_retroceso', {})
            data.append({
                "Activo": activo['asset'],
                "Tendencia": activo['direccion'],
                "Fuerza": f"{activo['fuerza']:.1f}%",
                "Nivel 23.6%": f"{niveles.get('236', 0):.5f}",
                "Nivel 38.2%": f"{niveles.get('382', 0):.5f}",
                "Nivel 50%": f"{niveles.get('50', 0):.5f}",
                "Precio actual": f"{activo.get('precio_actual', 0):.5f}"
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

    # Historial
    if st.session_state.historial:
        with st.expander("📋 Historial", expanded=False):
            for linea in st.session_state.historial[-30:]:
                st.text(linea)

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        now = datetime.now(ecuador)

        # FASE DE SELECCIÓN INICIAL: buscar los 6 mejores activos
        if st.session_state.fase == "seleccion":
            st.info("🔍 Buscando los 6 mejores activos con tendencia...")
            todos_activos = st.session_state.activos_reales + st.session_state.activos_otc
            if not todos_activos:
                st.warning(f"No hay activos disponibles. Reintentando en {pausa_entre_rondas} seg...")
                time.sleep(pausa_entre_rondas)
                real, otc = obtener_activos_abiertos(st.session_state.api)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.rerun()

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
                    res = evaluar_activo(indicators, umbral_fuerza)
                    if res:
                        direccion, fuerza, niveles = res
                        candidatos.append({
                            'asset': asset,
                            'direccion': direccion,
                            'fuerza': fuerza,
                            'niveles_retroceso': niveles,
                            'precio_actual': indicators['close'],
                            'indicators': indicators
                        })
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error con {asset}: {str(e)[:50]}")
                    continue
                time.sleep(0.1)

            if candidatos:
                # Ordenar por fuerza y tomar los 6 mejores
                candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                st.session_state.activos_seguimiento = candidatos[:NUM_ACTIVOS]
                st.session_state.fase = "seguimiento"
                st.session_state.historial.append(f"✅ Seleccionados {len(st.session_state.activos_seguimiento)} activos:")
                for a in st.session_state.activos_seguimiento:
                    st.session_state.historial.append(f"   - {a['asset']} ({a['direccion']}, {a['fuerza']:.1f}%)")
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.historial.append("⚠️ No se encontraron activos confiables. Reintentando...")
                time.sleep(pausa_entre_rondas)
                st.rerun()

        # FASE DE SEGUIMIENTO: monitorear los 6 activos y reemplazar si es necesario
        elif st.session_state.fase == "seguimiento":
            st.info("🔄 Monitoreando activos seleccionados...")
            nuevos_seguimiento = []
            activos_a_remover = []

            # Primero, revisar cada activo actual para ver si sigue siendo confiable
            for activo in st.session_state.activos_seguimiento:
                asset = activo['asset']
                try:
                    candles = st.session_state.api.get_candles(asset, 60, 5, time.time())  # últimas 5 velas
                    if not candles:
                        continue
                    df = pd.DataFrame(candles)
                    precio_actual = df['close'].iloc[-1]
                    activo['precio_actual'] = precio_actual

                    # Verificar si se alcanzó algún nivel de retroceso (con tolerancia 0.1%)
                    direccion = activo['direccion']
                    niveles = activo['niveles_retroceso']
                    nivel_alcanzado = None
                    for key, nivel in niveles.items():
                        if direccion == "CALL" and precio_actual <= nivel * 1.001:
                            nivel_alcanzado = key
                            break
                        elif direccion == "PUT" and precio_actual >= nivel * 0.999:
                            nivel_alcanzado = key
                            break

                    if nivel_alcanzado:
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
                            'direccion': direccion,
                            'entry': entry_local.strftime("%H:%M:%S"),
                            'expiry': expiry_local.strftime("%H:%M:%S"),
                            'estrategia': f'Retroceso {nivel_alcanzado} alcanzado',
                            'fuerza': activo['fuerza']
                        }
                        st.session_state.señales_activas.append(señal)
                        st.session_state.historial.append(f"🎯 Señal {direccion} para {asset} a las {entry_local.strftime('%H:%M:%S')} (nivel {nivel_alcanzado})")
                        # Este activo se remueve del seguimiento (ya dio señal)
                        activos_a_remover.append(activo)
                        continue

                    # Si no dio señal, verificar si sigue siendo confiable
                    # Necesitamos más velas para reevaluar tendencia
                    candles_full = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles_full or len(candles_full) < 50:
                        activos_a_remover.append(activo)
                        continue
                    df_full = pd.DataFrame(candles_full)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df_full[col] = pd.to_numeric(df_full[col], errors='coerce')
                    df_full.dropna(inplace=True)
                    if len(df_full) < 50:
                        activos_a_remover.append(activo)
                        continue
                    indicators = calcular_indicadores(df_full)
                    res = evaluar_activo(indicators, umbral_fuerza)
                    if res:
                        # Sigue siendo confiable, actualizar niveles y precio
                        direccion, fuerza, niveles = res
                        activo['fuerza'] = fuerza
                        activo['niveles_retroceso'] = niveles
                        activo['precio_actual'] = indicators['close']
                        nuevos_seguimiento.append(activo)
                    else:
                        # Ya no es confiable
                        activos_a_remover.append(activo)
                        st.session_state.historial.append(f"❌ Activo {asset} perdió confianza - será reemplazado")
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error monitoreando {asset}: {str(e)[:50]}")
                    activos_a_remover.append(activo)

            # Eliminar los que ya no son confiables o dieron señal
            for a in activos_a_remover:
                if a in st.session_state.activos_seguimiento:
                    st.session_state.activos_seguimiento.remove(a)

            # Si hay espacios vacíos, buscar reemplazos
            if len(st.session_state.activos_seguimiento) < NUM_ACTIVOS:
                st.session_state.historial.append(f"🔍 Buscando {NUM_ACTIVOS - len(st.session_state.activos_seguimiento)} reemplazos...")
                # Obtener lista de activos no seleccionados actualmente
                todos_activos = st.session_state.activos_reales + st.session_state.activos_otc
                seleccionados = [a['asset'] for a in st.session_state.activos_seguimiento]
                disponibles = [a for a in todos_activos if a not in seleccionados]

                candidatos = []
                for asset in disponibles:
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
                        res = evaluar_activo(indicators, umbral_fuerza)
                        if res:
                            direccion, fuerza, niveles = res
                            candidatos.append({
                                'asset': asset,
                                'direccion': direccion,
                                'fuerza': fuerza,
                                'niveles_retroceso': niveles,
                                'precio_actual': indicators['close'],
                                'indicators': indicators
                            })
                    except:
                        continue
                    time.sleep(0.1)

                if candidatos:
                    candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                    cuantos_faltan = NUM_ACTIVOS - len(st.session_state.activos_seguimiento)
                    nuevos = candidatos[:cuantos_faltan]
                    st.session_state.activos_seguimiento.extend(nuevos)
                    for n in nuevos:
                        st.session_state.historial.append(f"➕ Nuevo activo añadido: {n['asset']} ({n['direccion']}, {n['fuerza']:.1f}%)")
                else:
                    st.session_state.historial.append("⚠️ No se encontraron reemplazos disponibles.")

            # Si después de todo no hay activos, volver a selección
            if len(st.session_state.activos_seguimiento) == 0:
                st.session_state.fase = "seleccion"
                st.rerun()
            else:
                time.sleep(pausa_entre_rondas)
                st.rerun()

else:
    st.warning("🔒 Conéctate primero desde el panel izquierdo.")
