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
    # Renombrar columnas para claridad
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
    # Velas anteriores para patrones
    prev = df.iloc[-2] if len(df) > 1 else last

    # Volumen
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    vol_now = last['volume']
    strong_volume = vol_now > vol_avg * 1.2 if not pd.isna(vol_avg) else False
    very_strong_volume = vol_now > vol_avg * 1.5 if not pd.isna(vol_avg) else False

    # Soportes y resistencias (máximos y mínimos de las últimas 50 velas)
    soporte = df['low'].rolling(50).min().iloc[-1]
    resistencia = df['high'].rolling(50).max().iloc[-1]
    distancia_soporte = abs(last['close'] - soporte) / (last['close'] + 1e-10)
    distancia_resistencia = abs(last['close'] - resistencia) / (last['close'] + 1e-10)
    cerca_soporte = distancia_soporte < 0.002  # 0.2%
    cerca_resistencia = distancia_resistencia < 0.002

    # Rango lateral (diferencia entre máximos y mínimos recientes)
    rango_reciente = df['high'].iloc[-20:].max() - df['low'].iloc[-20:].min()
    atr_actual = last['atr']
    lateral = rango_reciente < atr_actual * 2.5  # Rango estrecho respecto al ATR

    # Bandas de Bollinger (20,2)
    bb_ma20 = df['close'].rolling(20).mean().iloc[-1]
    bb_std20 = df['close'].rolling(20).std().iloc[-1]
    bb_upper = bb_ma20 + 2 * bb_std20
    bb_lower = bb_ma20 - 2 * bb_std20

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'prev_close': prev['close'],
        'prev_high': prev['high'],
        'prev_low': prev['low'],
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
        'soporte': soporte,
        'resistencia': resistencia,
        'cerca_soporte': cerca_soporte,
        'cerca_resistencia': cerca_resistencia,
        'lateral': lateral,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'df': df
    }

# =========================
# ESTRATEGIA 1: TENDENCIA ADX + FIBONACCI
# =========================

def estrategia_tendencia_adx(indicators):
    """
    Detecta tendencia fuerte (ADX >= 25) y calcula niveles de Fibonacci (23.6%, 38.2%, 50%)
    para el retroceso. Devuelve dirección, fuerza, nombre y el nivel de entrada (el más cercano al precio actual).
    """
    if indicators['adx'] is None or pd.isna(indicators['adx']) or indicators['adx'] < 25:
        return None
    direccion = None
    if indicators['ema20'] > indicators['ema50'] and indicators['plus_di'] > indicators['minus_di']:
        direccion = "CALL"
    elif indicators['ema20'] < indicators['ema50'] and indicators['minus_di'] > indicators['plus_di']:
        direccion = "PUT"
    else:
        return None

    # Calcular niveles de Fibonacci del último movimiento (50 velas)
    df = indicators['df'].iloc[-50:]
    minimo = df['low'].min()
    maximo = df['high'].max()
    movimiento = maximo - minimo
    if direccion == "CALL":
        # Retroceso desde el máximo
        niveles = {
            '236': maximo - movimiento * 0.236,
            '382': maximo - movimiento * 0.382,
            '50': maximo - movimiento * 0.5
        }
    else:
        niveles = {
            '236': minimo + movimiento * 0.236,
            '382': minimo + movimiento * 0.382,
            '50': minimo + movimiento * 0.5
        }

    # Elegir el nivel más cercano al precio actual
    precio_actual = indicators['close']
    nivel_cercano = min(niveles.values(), key=lambda x: abs(x - precio_actual))
    fuerza = indicators['adx']
    if indicators['strong_volume']:
        fuerza = min(fuerza + 10, 100)
    return direccion, fuerza, "Tendencia ADX + Fibonacci", nivel_cercano

# =========================
# ESTRATEGIA 2: SOPORTE FUERTE (COMPRA EN REBOTE)
# =========================

def estrategia_soporte_fuerte(indicators):
    """
    CALL: precio cerca de soporte, vela alcista, volumen alto.
    Nivel de entrada = soporte.
    """
    if not indicators['cerca_soporte']:
        return None
    if indicators['close'] <= indicators['open']:  # vela no alcista
        return None
    if not indicators['strong_volume']:
        return None
    # Confirmación adicional: cuerpo de vela decente
    cuerpo = abs(indicators['close'] - indicators['open'])
    rango = indicators['high'] - indicators['low']
    if cuerpo < rango * 0.5:
        return None
    fuerza = 60 + (20 if indicators['very_strong_volume'] else 0) + (10 if cuerpo > rango * 0.7 else 0)
    fuerza = min(fuerza, 100)
    return "CALL", fuerza, "Soporte fuerte", indicators['soporte']

# =========================
# ESTRATEGIA 3: RESISTENCIA FUERTE (VENTA EN RECHAZO)
# =========================

def estrategia_resistencia_fuerte(indicators):
    """
    PUT: precio cerca de resistencia, vela bajista, volumen alto.
    Nivel de entrada = resistencia.
    """
    if not indicators['cerca_resistencia']:
        return None
    if indicators['close'] >= indicators['open']:  # vela no bajista
        return None
    if not indicators['strong_volume']:
        return None
    cuerpo = abs(indicators['close'] - indicators['open'])
    rango = indicators['high'] - indicators['low']
    if cuerpo < rango * 0.5:
        return None
    fuerza = 60 + (20 if indicators['very_strong_volume'] else 0) + (10 if cuerpo > rango * 0.7 else 0)
    fuerza = min(fuerza, 100)
    return "PUT", fuerza, "Resistencia fuerte", indicators['resistencia']

# =========================
# ESTRATEGIA 4: REVERSIÓN (BB + RSI + VELA)
# =========================

def estrategia_reversion(indicators):
    """
    Detecta posibles reversiones en sobrecompra/sobreventa.
    CALL: RSI < 30, precio cerca de banda inferior, vela alcista.
    PUT: RSI > 70, precio cerca de banda superior, vela bajista.
    Nivel de entrada = banda correspondiente (para monitoreo de precio).
    """
    # CALL
    if indicators['rsi'] < 30 and indicators['close'] <= indicators['bb_lower'] * 1.01:
        if indicators['close'] > indicators['open']:  # vela alcista
            cuerpo = indicators['close'] - indicators['open']
            rango = indicators['high'] - indicators['low']
            if cuerpo > rango * 0.4 and indicators['strong_volume']:
                fuerza = 70 + (10 if indicators['very_strong_volume'] else 0)
                return "CALL", min(fuerza, 100), "Reversión sobreventa", indicators['bb_lower']
    # PUT
    if indicators['rsi'] > 70 and indicators['close'] >= indicators['bb_upper'] * 0.99:
        if indicators['close'] < indicators['open']:  # vela bajista
            cuerpo = indicators['open'] - indicators['close']
            rango = indicators['high'] - indicators['low']
            if cuerpo > rango * 0.4 and indicators['strong_volume']:
                fuerza = 70 + (10 if indicators['very_strong_volume'] else 0)
                return "PUT", min(fuerza, 100), "Reversión sobrecompra", indicators['bb_upper']
    return None

# =========================
# ESTRATEGIA 5: BREAKOUT DE RANGO LATERAL
# =========================

def estrategia_breakout(indicators):
    """
    Detecta ruptura de un rango lateral con volumen.
    CALL: precio supera la resistencia del rango reciente.
    PUT: precio perfora el soporte del rango reciente.
    Nivel de entrada = borde del rango.
    """
    if not indicators['lateral']:
        return None
    # Rango de las últimas 20 velas
    df = indicators['df'].iloc[-20:]
    rango_alto = df['high'].max()
    rango_bajo = df['low'].min()
    precio = indicators['close']
    if precio > rango_alto * 1.001 and indicators['strong_volume']:
        fuerza = 70 + (10 if indicators['very_strong_volume'] else 0)
        return "CALL", min(fuerza, 100), "Breakout alcista", rango_alto
    if precio < rango_bajo * 0.999 and indicators['strong_volume']:
        fuerza = 70 + (10 if indicators['very_strong_volume'] else 0)
        return "PUT", min(fuerza, 100), "Breakout bajista", rango_bajo
    return None

# =========================
# EVALUADOR PRINCIPAL
# =========================

def evaluar_activo(indicators, umbral_fuerza=40):
    """
    Ejecuta las 5 estrategias y retorna la mejor señal (dirección, fuerza, nombre, nivel)
    si alguna supera el umbral.
    """
    mejores = []
    # Estrategia 1
    res1 = estrategia_tendencia_adx(indicators)
    if res1:
        direccion, fuerza, nombre, nivel = res1
        if fuerza >= umbral_fuerza:
            mejores.append((fuerza, direccion, nombre, nivel))

    # Estrategia 2
    res2 = estrategia_soporte_fuerte(indicators)
    if res2:
        direccion, fuerza, nombre, nivel = res2
        if fuerza >= umbral_fuerza:
            mejores.append((fuerza, direccion, nombre, nivel))

    # Estrategia 3
    res3 = estrategia_resistencia_fuerte(indicators)
    if res3:
        direccion, fuerza, nombre, nivel = res3
        if fuerza >= umbral_fuerza:
            mejores.append((fuerza, direccion, nombre, nivel))

    # Estrategia 4
    res4 = estrategia_reversion(indicators)
    if res4:
        direccion, fuerza, nombre, nivel = res4
        if fuerza >= umbral_fuerza:
            mejores.append((fuerza, direccion, nombre, nivel))

    # Estrategia 5
    res5 = estrategia_breakout(indicators)
    if res5:
        direccion, fuerza, nombre, nivel = res5
        if fuerza >= umbral_fuerza:
            mejores.append((fuerza, direccion, nombre, nivel))

    if not mejores:
        return None
    # Ordenar por fuerza descendente
    mejores.sort(reverse=True)
    fuerza, direccion, nombre, nivel = mejores[0]
    return direccion, fuerza, nombre, nivel
