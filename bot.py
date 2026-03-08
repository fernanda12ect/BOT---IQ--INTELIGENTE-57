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
        # Intentar obtener todos los activos (método común en iqoptionapi)
        all_actives = api.get_all_actives()
        # all_actives suele ser un dict {id: {'name': 'EURUSD', 'enabled': True, ...}}
        activos = []
        for id, info in all_actives.items():
            if info.get('enabled', True):  # Solo activos habilitados
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
    """
    Calcula todos los indicadores para la última vela y devuelve un dict con los valores.
    """
    df = df.copy()

    # EMA
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR
    high = df['max']
    low = df['min']
    close = df['close']
    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # Bollinger Bands (20,2)
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['bb_upper'] = ma20 + 2 * std20
    df['bb_lower'] = ma20 - 2 * std20

    # Volumen medio (20)
    df['vol_ma20'] = df['volume'].rolling(20).mean()

    # Última fila
    last = df.iloc[-1]

    # Fuerza de vela
    body = abs(last['close'] - last['open'])
    rng = last['max'] - last['min']
    strong_candle = body > rng * 0.6 if rng != 0 else False

    # Fuerza de volumen
    vol_now = last['volume']
    vol_avg = last['vol_ma20']
    strong_volume = vol_now > vol_avg * 1.5 if not pd.isna(vol_avg) else False

    return {
        'close': last['close'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'rsi': last['rsi'],
        'atr': last['atr'],
        'bb_upper': last['bb_upper'],
        'bb_lower': last['bb_lower'],
        'strong_candle': strong_candle,
        'strong_volume': strong_volume,
        'atr_mean': df['atr'].mean()
    }

# =========================
# PROBABILIDAD
# =========================

def calcular_probabilidad(indicators):
    """
    Retorna (probabilidad, dirección, estrategia) o None.
    """
    score = 0
    direction = None
    strategy = None

    # Tendencia
    if indicators['ema20'] > indicators['ema50']:
        score += 25
        direction = "CALL"
        strategy = "Tendencia alcista"
    elif indicators['ema20'] < indicators['ema50']:
        score += 25
        direction = "PUT"
        strategy = "Tendencia bajista"
    else:
        return None

    # Volatilidad
    if indicators['atr'] > indicators['atr_mean']:
        score += 15

    # Vela fuerte
    if indicators['strong_candle']:
        score += 15

    # Volumen fuerte
    if indicators['strong_volume']:
        score += 15

    # Reversión (sobrescribe dirección si se cumple)
    rsi = indicators['rsi']
    price = indicators['close']
    bb_upper = indicators['bb_upper']
    bb_lower = indicators['bb_lower']

    if rsi > 75 and price >= bb_upper:
        direction = "PUT"
        strategy = "Reversión bajista (sobrecompra)"
        score += 20
    elif rsi < 25 and price <= bb_lower:
        direction = "CALL"
        strategy = "Reversión alcista (sobreventa)"
        score += 20

    score = min(score, 100)
    return score, direction, strategy

# =========================
# ESCÁNER POR GRUPOS (CON DEPURACIÓN)
# =========================

def escanear_activos_por_grupos(api, activos, grupo_size=20, timeout_seconds=30):
    """
    Escanea una lista de activos en grupos de tamaño grupo_size, uno por uno dentro del grupo.
    Retorna la primera señal con probabilidad >= 70 o None.
    Incluye mensajes de depuración (prints) para seguir el proceso.
    """
    print("\n=== INICIANDO ESCANEO ===")
    print(f"DEBUG: Recibidos {len(activos)} activos para escanear.")
    
    # Verificar tipo de activos
    if not isinstance(activos, list):
        print(f"ERROR: activos no es una lista, es {type(activos)}")
        return None
    
    if len(activos) == 0:
        print("ERROR: lista de activos vacía")
        return None
    
    # Verificar que api tenga el método get_candles
    if not hasattr(api, 'get_candles'):
        print("ERROR: api no tiene método get_candles")
        return None

    from itertools import islice

    def chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    start_time = time.time()
    grupo_num = 0

    for grupo in chunks(activos, grupo_size):
        grupo_num += 1
        print(f"\n--- Grupo {grupo_num} de {grupo_size} activos ---")
        
        if time.time() - start_time > timeout_seconds:
            print(f"DEBUG: Timeout de {timeout_seconds}s alcanzado. Deteniendo escaneo.")
            break

        for asset in grupo:
            print(f"  Analizando: {asset}...")
            try:
                # Obtener velas
                candles = api.get_candles(asset, 60, 100, time.time())
                if not candles:
                    print(f"    No se obtuvieron velas para {asset}")
                    continue
                if len(candles) < 50:
                    print(f"    Velas insuficientes: {len(candles)}")
                    continue

                # Crear DataFrame
                df = pd.DataFrame(candles)
                for col in ['open', 'max', 'min', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df.dropna(inplace=True)

                if len(df) < 50:
                    print(f"    DataFrame muy pequeño después de limpiar: {len(df)} filas")
                    continue

                # Calcular indicadores
                indicators = calcular_indicadores(df)
                result = calcular_probabilidad(indicators)

                if result:
                    prob, direction, strategy = result
                    print(f"    Probabilidad calculada: {prob}% - {direction} - {strategy}")
                    
                    if prob >= 70:
                        print(f"    ✅ ¡Señal encontrada en {asset} con probabilidad {prob}%!")
                        
                        # Obtener hora del servidor
                        try:
                            server_time = api.get_server_time()
                            now = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                        except Exception as e:
                            print(f"    Error obteniendo server_time: {e}. Usando hora local UTC.")
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
                    else:
                        print(f"    Probabilidad {prob}% por debajo del umbral (70%).")
                else:
                    print(f"    No se cumplieron condiciones de tendencia para {asset}.")

                # Pausa entre activos
                time.sleep(0.25)

            except Exception as e:
                print(f"    ❌ Error procesando {asset}: {type(e).__name__} - {e}")
                continue

    print("\n=== ESCANEO FINALIZADO SIN SEÑAL ===")
    return None
