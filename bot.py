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
# OBTENER ACTIVOS ABIERTOS
# =========================

def obtener_activos_abiertos(api):
    try:
        open_time = api.get_all_open_time()
        real = []
        otc = []
        now_utc = datetime.now(pytz.UTC)
        dia_semana = now_utc.weekday()
        es_fin_semana = dia_semana >= 5

        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if '-OTC' in asset:
                        otc.append(asset)
                    else:
                        if not es_fin_semana:
                            real.append(asset)
        if es_fin_semana and not otc:
            otc = OTC_ASSETS.copy()
        return real, otc
    except:
        return REAL_ASSETS, OTC_ASSETS

# =========================
# INDICADORES
# =========================

def calcular_indicadores(df):
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
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    # ADX
    df['tr'] = tr
    df['plus_dm'] = np.where((high - high.shift()) > (low.shift() - low), np.maximum(high - high.shift(), 0), 0)
    df['minus_dm'] = np.where((low.shift() - low) > (high - high.shift()), np.maximum(low.shift() - low, 0), 0)
    df['atr_period'] = df['tr'].rolling(14).mean()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr_period'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr_period'])
    df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di']))
    df['adx'] = df['dx'].rolling(14).mean()

    last = df.iloc[-1]
    # Volumen
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    vol_now = last['volume']
    strong_volume = vol_now > vol_avg * 1.2 if not pd.isna(vol_avg) else False

    # Determinar tendencia
    alcista = last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di']
    bajista = last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di']
    tendencia = "CALL" if alcista else ("PUT" if bajista else None)

    # Fuerza de tendencia (usamos ADX como base)
    fuerza = last['adx'] if not pd.isna(last['adx']) else 0
    if strong_volume:
        fuerza = min(fuerza + 10, 100)

    # Verificar estructura de máximos y mínimos (últimas 20 velas)
    ultimos_20 = df.iloc[-20:]
    if tendencia == "CALL":
        # Máximos crecientes y mínimos crecientes
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        estructura_valida = all(maximos[i] <= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] <= minimos[i+1] for i in range(len(minimos)-1))
    elif tendencia == "PUT":
        # Máximos decrecientes y mínimos decrecientes
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        estructura_valida = all(maximos[i] >= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] >= minimos[i+1] for i in range(len(minimos)-1))
    else:
        estructura_valida = False

    return {
        'close': last['close'],
        'high': last['max'],
        'low': last['min'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'adx': last['adx'],
        'plus_di': last['plus_di'],
        'minus_di': last['minus_di'],
        'tendencia': tendencia,
        'fuerza': fuerza,
        'volumen_rel': vol_now / vol_avg if vol_avg else 1,
        'estructura_valida': estructura_valida,
        'df': df
    }

# =========================
# CALCULAR NIVELES DE RETROCESO (23.6%, 38.2%, 50%)
# =========================

def calcular_niveles_retroceso(df, tendencia):
    """
    Calcula niveles de retroceso de Fibonacci: 23.6%, 38.2%, 50%.
    Retorna un dict con los niveles.
    """
    df = df.iloc[-50:].copy()
    minimo = df['low'].min()
    maximo = df['high'].max()
    movimiento = maximo - minimo
    if tendencia == "CALL":
        # Retroceso desde el máximo
        nivel_382 = maximo - movimiento * 0.382
        nivel_236 = maximo - movimiento * 0.236
        nivel_50 = maximo - movimiento * 0.5
    else:  # PUT
        nivel_382 = minimo + movimiento * 0.382
        nivel_236 = minimo + movimiento * 0.236
        nivel_50 = minimo + movimiento * 0.5
    return {'236': nivel_236, '382': nivel_382, '50': nivel_50}

# =========================
# EVALUAR TENDENCIA (para selección inicial y reemplazo)
# =========================

def evaluar_activo(indicators, umbral_fuerza):
    """
    Retorna (direccion, fuerza, niveles) si el activo es confiable.
    Confiable: ADX >= 25, tendencia definida, estructura válida, fuerza >= umbral.
    """
    if indicators['adx'] is None or pd.isna(indicators['adx']) or indicators['adx'] < 25:
        return None
    if indicators['tendencia'] is None:
        return None
    if not indicators['estructura_valida']:
        return None
    if indicators['fuerza'] < umbral_fuerza:
        return None
    niveles = calcular_niveles_retroceso(indicators['df'], indicators['tendencia'])
    return indicators['tendencia'], indicators['fuerza'], niveles
