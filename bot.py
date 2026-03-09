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
# INDICADORES BASE
# =========================

def calcular_indicadores(df):
    df = df.copy()
    # Renombrar columnas
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

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
    high = df['high']
    low = df['low']
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

    # Última vela
    last = df.iloc[-1]
    # Volumen
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    vol_now = last['volume']
    strong_volume = vol_now > vol_avg * 1.2 if not pd.isna(vol_avg) else False
    very_strong_volume = vol_now > vol_avg * 1.5 if not pd.isna(vol_avg) else False

    # Determinar tendencia principal
    if last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di'] and last['adx'] >= 25:
        tendencia = "CALL"
        fuerza_tendencia = last['adx'] + (10 if strong_volume else 0)
    elif last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di'] and last['adx'] >= 25:
        tendencia = "PUT"
        fuerza_tendencia = last['adx'] + (10 if strong_volume else 0)
    else:
        tendencia = None
        fuerza_tendencia = 0

    # Verificar estructura de máximos/mínimos (últimas 20 velas)
    ultimos_20 = df.iloc[-20:]
    if tendencia == "CALL":
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        estructura_valida = all(maximos[i] <= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] <= minimos[i+1] for i in range(len(minimos)-1))
    elif tendencia == "PUT":
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        estructura_valida = all(maximos[i] >= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] >= minimos[i+1] for i in range(len(minimos)-1))
    else:
        estructura_valida = False

    # Calcular niveles de Fibonacci del último movimiento (50 velas)
    df_50 = df.iloc[-50:]
    minimo_50 = df_50['low'].min()
    maximo_50 = df_50['high'].max()
    movimiento = maximo_50 - minimo_50
    niveles_fib = {
        '236': maximo_50 - movimiento * 0.236 if tendencia == "CALL" else minimo_50 + movimiento * 0.236,
        '382': maximo_50 - movimiento * 0.382 if tendencia == "CALL" else minimo_50 + movimiento * 0.382,
        '500': maximo_50 - movimiento * 0.5 if tendencia == "CALL" else minimo_50 + movimiento * 0.5,
        '618': maximo_50 - movimiento * 0.618 if tendencia == "CALL" else minimo_50 + movimiento * 0.618
    }

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'rsi': last['rsi'],
        'adx': last['adx'],
        'plus_di': last['plus_di'],
        'minus_di': last['minus_di'],
        'atr': last['atr'],
        'volumen_rel': vol_now / vol_avg if vol_avg else 1,
        'strong_volume': strong_volume,
        'very_strong_volume': very_strong_volume,
        'tendencia': tendencia,
        'fuerza_tendencia': min(fuerza_tendencia, 100),
        'estructura_valida': estructura_valida,
        'niveles_fib': niveles_fib,
        'df': df
    }

# =========================
# EVALUAR ACTIVO (para selección)
# =========================

def evaluar_activo(indicators, umbral_fuerza=50):
    """
    Retorna (direccion, fuerza, niveles_fib) si el activo es apto para seguimiento.
    Requisitos: tendencia clara, estructura válida, fuerza >= umbral.
    """
    if indicators['tendencia'] is None:
        return None
    if not indicators['estructura_valida']:
        return None
    if indicators['fuerza_tendencia'] < umbral_fuerza:
        return None
    return indicators['tendencia'], indicators['fuerza_tendencia'], indicators['niveles_fib']

# =========================
# VERIFICAR PUNTO DE ENTRADA (retroceso)
# =========================

def verificar_punto_entrada(activo, precio_actual, tolerancia=0.001):
    """
    Verifica si el precio actual ha alcanzado algún nivel de Fibonacci (con tolerancia).
    Retorna (True, nivel_alcanzado) o (False, None).
    """
    niveles = activo['niveles_fib']
    direccion = activo['direccion']
    for key, nivel in niveles.items():
        if direccion == "CALL" and precio_actual <= nivel * (1 + tolerancia):
            return True, key
        elif direccion == "PUT" and precio_actual >= nivel * (1 - tolerancia):
            return True, key
    return False, None
