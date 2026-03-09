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
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMA
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

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

    last = df.iloc[-1]

    # Volumen promedio
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    vol_now = last['volume']
    strong_volume = vol_now > vol_avg * 1.2 if not pd.isna(vol_avg) else False

    # Determinar tendencia
    if last['adx'] >= 25 and last['ema20'] > last['ema50']:
        # Verificar máximos y mínimos crecientes en últimas 20 velas
        ultimos_20 = df.iloc[-20:]
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        if all(maximos[i] <= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] <= minimos[i+1] for i in range(len(minimos)-1)):
            tendencia = "CALL"
            fuerza = last['adx']
        else:
            tendencia = None
            fuerza = 0
    elif last['adx'] >= 25 and last['ema20'] < last['ema50']:
        ultimos_20 = df.iloc[-20:]
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        if all(maximos[i] >= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] >= minimos[i+1] for i in range(len(minimos)-1)):
            tendencia = "PUT"
            fuerza = last['adx']
        else:
            tendencia = None
            fuerza = 0
    else:
        tendencia = None
        fuerza = 0

    # Niveles Fibonacci del último movimiento (50 velas)
    df_50 = df.iloc[-50:]
    minimo_50 = df_50['low'].min()
    maximo_50 = df_50['high'].max()
    movimiento = maximo_50 - minimo_50
    if tendencia == "CALL":
        niveles_fib = {
            '382': maximo_50 - movimiento * 0.382,
            '500': maximo_50 - movimiento * 0.5,
            '618': maximo_50 - movimiento * 0.618
        }
    elif tendencia == "PUT":
        niveles_fib = {
            '382': minimo_50 + movimiento * 0.382,
            '500': minimo_50 + movimiento * 0.5,
            '618': minimo_50 + movimiento * 0.618
        }
    else:
        niveles_fib = {}

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'adx': last['adx'],
        'plus_di': last['plus_di'],
        'minus_di': last['minus_di'],
        'atr': last['atr'],
        'volumen_rel': vol_now / vol_avg if vol_avg else 1,
        'strong_volume': strong_volume,
        'tendencia': tendencia,
        'fuerza': fuerza,
        'niveles_fib': niveles_fib,
        'df': df
    }

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN
# =========================

def evaluar_activo(indicators, umbral_fuerza=30):
    if indicators['tendencia'] is None:
        return None
    if indicators['fuerza'] < umbral_fuerza:
        return None
    return indicators['tendencia'], indicators['fuerza'], indicators['niveles_fib']

# =========================
# VERIFICAR PUNTO DE ENTRADA
# =========================

def verificar_punto_entrada(activo, vela_actual, tolerancia=0.002):
    """
    vela_actual: dict con open, close, high, low, volume, volumen_rel
    Retorna (True, nivel) si el precio está cerca de un nivel Fibonacci y la vela confirma la continuación.
    """
    niveles = activo['niveles_fib']
    direccion = activo['direccion']
    precio = vela_actual['close']

    for key, nivel in niveles.items():
        if direccion == "CALL":
            # El precio debe estar cerca del nivel (por debajo o igual)
            if precio <= nivel * (1 + tolerancia):
                # La vela debe ser alcista (close > open) y tener volumen fuerte
                if vela_actual['close'] > vela_actual['open'] and vela_actual['volumen_rel'] >= 1.2:
                    return True, key
        else:  # PUT
            if precio >= nivel * (1 - tolerancia):
                if vela_actual['close'] < vela_actual['open'] and vela_actual['volumen_rel'] >= 1.2:
                    return True, key
    return False, None
