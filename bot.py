import time
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import pytz

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Activos predefinidos (fallback)
REAL_ASSETS = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY",
    "EURJPY", "GBPJPY", "USDCHF", "USDCAD", "NZDUSD"
]
OTC_ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC"]

# =========================
# OBTENER TODOS LOS ACTIVOS DESDE LA API
# =========================

def obtener_todos_activos(api):
    """
    Obtiene la lista de todos los activos disponibles en IQ Option.
    En caso de error, retorna la lista predefinida (REAL+OTC).
    """
    try:
        all_actives = api.get_all_actives()
        activos = []
        for id, info in all_actives.items():
            if info.get('enabled', True):
                nombre = info.get('name')
                if nombre:
                    activos.append(nombre)
        if activos:
            logging.info(f"Se obtuvieron {len(activos)} activos desde la API")
            return activos
        else:
            raise ValueError("Lista de activos vacía")
    except Exception as e:
        logging.error(f"Error al obtener activos: {e}. Usando lista predefinida.")
        return REAL_ASSETS + OTC_ASSETS

# =========================
# INDICADORES (optimizados)
# =========================

def calcular_indicadores(df):
    # ... (sin cambios)
    # (mantener el mismo código de la versión anterior)
    pass

# =========================
# PROBABILIDAD
# =========================

def calcular_probabilidad(indicators):
    # ... (sin cambios)
    pass

# =========================
# ESCÁNER POR GRUPOS (NUEVO)
# =========================

def escanear_activos_por_grupos(api, activos, batch_size=20, timeout_seconds=60):
    """
    Escanea todos los activos en grupos de batch_size.
    Por cada grupo, escanea uno por uno con pausa de 0.25s.
    Si encuentra una señal con probabilidad >=80, la retorna inmediatamente.
    Si termina todos sin señal, retorna None.
    Además, reporta el progreso a través de un callback opcional.
    """
    total_activos = len(activos)
    num_grupos = (total_activos + batch_size - 1) // batch_size
    start_time = time.time()

    for grupo_idx in range(num_grupos):
        inicio = grupo_idx * batch_size
        fin = min(inicio + batch_size, total_activos)
        grupo_actual = activos[inicio:fin]
        
        logging.info(f"Escaneando grupo {grupo_idx+1}/{num_grupos} (activos {inicio+1}-{fin})")
        
        for asset in grupo_actual:
            # Verificar timeout global
            if time.time() - start_time > timeout_seconds:
                logging.warning("Tiempo de escaneo agotado")
                return None

            try:
                # Obtener velas
                candles = api.get_candles(asset, 60, 100, time.time())
                if not candles or len(candles) < 50:
                    logging.warning(f"Activo {asset}: datos insuficientes ({len(candles) if candles else 0} velas)")
                    continue

                df = pd.DataFrame(candles)
                for col in ['open', 'max', 'min', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df.dropna(inplace=True)

                if len(df) < 50:
                    continue

                indicators = calcular_indicadores(df)
                result = calcular_probabilidad(indicators)

                if result:
                    prob, direction, strategy = result
                    if prob >= 80:
                        # Obtener hora del servidor (UTC)
                        try:
                            server_time = api.get_server_time()
                            now = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                        except:
                            now = datetime.now(pytz.UTC)

                        entry_dt = now + timedelta(minutes=1)
                        entry_dt = entry_dt.replace(second=0, microsecond=0)
                        expiry_dt = entry_dt + timedelta(minutes=5)

                        entry_local = entry_dt.astimezone(ecuador)
                        expiry_local = expiry_dt.astimezone(ecuador)

                        return {
                            "asset": asset,
                            "direction": direction,
                            "prob": prob,
                            "strategy": strategy,
                            "entry": entry_local.strftime("%H:%M:%S"),
                            "expiry": expiry_local.strftime("%H:%M:%S"),
                            "entry_utc": entry_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "expiry_utc": expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
                        }

                # Pausa entre activos
                time.sleep(0.25)

            except Exception as e:
                logging.error(f"Error al procesar {asset}: {e}")
                continue

    # Si llegamos aquí, no se encontró señal
    return None
