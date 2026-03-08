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

# Activos predefinidos (fallback por si falla la API)
REAL_ASSETS = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY",
    "EURJPY", "GBPJPY", "USDCHF", "USDCAD", "NZDUSD"
]
OTC_ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC"]

# =========================
# OBTENER ACTIVOS ABIERTOS EN TIEMPO REAL
# =========================

def obtener_activos_abiertos(api):
    """
    Obtiene listas de activos REAL y OTC que están actualmente abiertos para trading binario.
    Retorna (real_abiertos, otc_abiertos)
    """
    try:
        open_time = api.get_all_open_time()
        real = []
        otc = []
        # La estructura puede variar; asumimos que 'binary' contiene los activos binarios
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if '-OTC' in asset:
                        otc.append(asset)
                    else:
                        real.append(asset)
        logging.info(f"Activos abiertos: {len(real)} REAL, {len(otc)} OTC")
        return real, otc
    except Exception as e:
        logging.error(f"Error obteniendo activos abiertos: {e}")
        # Fallback a listas predefinidas (sin filtrar por apertura)
        return REAL_ASSETS, OTC_ASSETS

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
# PROBABILIDAD (con umbral)
# =========================

def calcular_probabilidad(indicators, umbral=80):
    """
    Retorna (probabilidad, dirección, estrategia) si la probabilidad >= umbral, sino None.
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

    if score >= umbral:
        return score, direction, strategy
    else:
        return None
