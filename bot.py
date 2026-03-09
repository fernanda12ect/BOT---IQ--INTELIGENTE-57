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

    # Últimas velas
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    prev2 = df.iloc[-3] if len(df) > 2 else prev

    # Volumen
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    vol_now = last['volume']
    strong_volume = vol_now > vol_avg * 1.2 if not pd.isna(vol_avg) else False

    # Determinar tendencia principal
    if last['adx'] >= 25 and last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di']:
        tendencia = "CALL"
        fuerza_tendencia = last['adx']
    elif last['adx'] >= 25 and last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di']:
        tendencia = "PUT"
        fuerza_tendencia = last['adx']
    else:
        tendencia = None
        fuerza_tendencia = 0

    # Niveles de Fibonacci del último movimiento (50 velas)
    df_50 = df.iloc[-50:]
    minimo_50 = df_50['low'].min()
    maximo_50 = df_50['high'].max()
    movimiento = maximo_50 - minimo_50
    if tendencia == "CALL":
        niveles_fib = {
            '236': maximo_50 - movimiento * 0.236,
            '382': maximo_50 - movimiento * 0.382,
            '500': maximo_50 - movimiento * 0.5,
            '618': maximo_50 - movimiento * 0.618
        }
    elif tendencia == "PUT":
        niveles_fib = {
            '236': minimo_50 + movimiento * 0.236,
            '382': minimo_50 + movimiento * 0.382,
            '500': minimo_50 + movimiento * 0.5,
            '618': minimo_50 + movimiento * 0.618
        }
    else:
        niveles_fib = {}

    # Detectar patrones de reversión
    # Pin bar: cuerpo pequeño, mecha larga en dirección opuesta
    body = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']
    total_range = last['high'] - last['low']
    pin_bar = False
    if total_range > 0:
        if tendencia == "CALL":  # Esperamos una vela bajista en el retroceso, luego reversión alcista? Realmente el patrón es para detectar reversión en el nivel
            # Para CALL, buscamos una vela alcista con mecha inferior larga (rechazo de bajada)
            if lower_wick > body * 2 and lower_wick > upper_wick and body < total_range * 0.3:
                pin_bar = True
        elif tendencia == "PUT":
            # Para PUT, buscamos una vela bajista con mecha superior larga
            if upper_wick > body * 2 and upper_wick > lower_wick and body < total_range * 0.3:
                pin_bar = True

    # Envolvente (engulfing)
    engulfing = False
    if tendencia == "CALL":
        # Vela actual alcista que envuelve a la anterior bajista
        if last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['high'] and last['open'] < prev['low']:
            engulfing = True
    elif tendencia == "PUT":
        # Vela actual bajista que envuelve a la anterior alcista
        if last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['low'] and last['open'] > prev['high']:
            engulfing = True

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'prev_close': prev['close'],
        'prev_high': prev['high'],
        'prev_low': prev['low'],
        'prev_open': prev['open'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'rsi': last['rsi'],
        'adx': last['adx'],
        'plus_di': last['plus_di'],
        'minus_di': last['minus_di'],
        'atr': last['atr'],
        'volumen_rel': vol_now / vol_avg if vol_avg else 1,
        'strong_volume': strong_volume,
        'tendencia': tendencia,
        'fuerza_tendencia': fuerza_tendencia,
        'niveles_fib': niveles_fib,
        'pin_bar': pin_bar,
        'engulfing': engulfing,
        'df': df
    }

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN
# =========================

def evaluar_activo(indicators, umbral_fuerza=30):
    if indicators['tendencia'] is None:
        return None
    if indicators['fuerza_tendencia'] < umbral_fuerza:
        return None
    return indicators['tendencia'], indicators['fuerza_tendencia'], indicators['niveles_fib']

# =========================
# VERIFICAR PUNTO DE ENTRADA (con patrones de reversión)
# =========================

def verificar_punto_entrada(activo, precio_actual, indicators, tolerancia=0.001):
    """
    Verifica si el precio actual está cerca de algún nivel de Fibonacci y si hay un patrón de reversión (pin bar o engulfing) con volumen.
    Retorna (True, nivel_alcanzado) o (False, None).
    """
    niveles = activo['niveles_fib']
    direccion = activo['direccion']
    for key, nivel in niveles.items():
        if direccion == "CALL" and precio_actual <= nivel * (1 + tolerancia):
            # Confirmación: vela alcista con patrón de reversión o engulfing, y volumen
            if (indicators['pin_bar'] or indicators['engulfing']) and indicators['strong_volume']:
                return True, key
        elif direccion == "PUT" and precio_actual >= nivel * (1 - tolerancia):
            if (indicators['pin_bar'] or indicators['engulfing']) and indicators['strong_volume']:
                return True, key
    return False, None
