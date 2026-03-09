import time
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Solo activos OTC (para este bot)
OTC_ASSETS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC"
]

# =========================
# OBTENER ACTIVOS ABIERTOS (solo OTC)
# =========================
def obtener_activos_abiertos(api):
    try:
        open_time = api.get_all_open_time()
        otc = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False) and '-OTC' in asset:
                    otc.append(asset)
        if not otc:
            otc = OTC_ASSETS
        return [], otc
    except:
        return [], OTC_ASSETS

# =========================
# CALCULAR INDICADORES BÁSICOS (incluye RSI)
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

    # RSI (14 períodos)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()

    # Última vela
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # Cruce de EMAs
    cruce_ema10_20 = (prev['ema10'] <= prev['ema20'] and last['ema10'] > last['ema20']) or \
                     (prev['ema10'] >= prev['ema20'] and last['ema10'] < last['ema20'])
    direccion_cruce = "CALL" if last['ema10'] > last['ema20'] else "PUT" if last['ema10'] < last['ema20'] else None

    # Volumen relativo
    vol_rel = last['volume'] / last['vol_avg'] if last['vol_avg'] else 1

    # Volatilidad en últimos 20 minutos
    if len(df) >= 20:
        ultimas_20 = df.iloc[-20:]
        precio_min = ultimas_20['low'].min()
        precio_max = ultimas_20['high'].max()
        volatilidad = (precio_max - precio_min) / precio_min if precio_min > 0 else 0
    else:
        volatilidad = 1.0

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'ema10': last['ema10'],
        'ema20': last['ema20'],
        'rsi': last['rsi'],
        'cruce_ema': cruce_ema10_20,
        'direccion_cruce': direccion_cruce,
        'vol_rel': vol_rel,
        'volatilidad': volatilidad,
        'df': df
    }

# =========================
# DETECTAR NIVELES HORIZONTALES (2 TOQUES, SIN CALIDAD)
# =========================
def detectar_niveles_horizontales(df, num_toques=2):
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    closes = df['close']
    tolerancia = 0.0005
    conteo = defaultdict(int)

    for idx in range(len(df)):
        # Máximos locales
        if idx > 0 and idx < len(df)-1:
            if highs.iloc[idx] > highs.iloc[idx-1] and highs.iloc[idx] > highs.iloc[idx+1]:
                precio = round(highs.iloc[idx], 5)
                conteo[precio] += 1
        # Mínimos locales
        if idx > 0 and idx < len(df)-1:
            if lows.iloc[idx] < lows.iloc[idx-1] and lows.iloc[idx] < lows.iloc[idx+1]:
                precio = round(lows.iloc[idx], 5)
                conteo[precio] += 1

    niveles_h = []
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > df['close'].iloc[-1] else 'soporte'
            niveles_h.append({
                'precio': precio,
                'tipo': tipo,
                'toques': cnt
            })

    precio_actual = df['close'].iloc[-1]
    niveles_h.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles_h

# =========================
# DETECTAR LÍNEAS DE TENDENCIA (2 TOQUES, SIMPLE)
# =========================
def detectar_lineas_tendencia(df):
    df = df.iloc[-50:].copy()
    minimos = df['low'].values
    maximos = df['high'].values
    indices = np.arange(len(df))

    lineas = []
    # Tendencia alcista: 2 mínimos crecientes
    for i in range(len(minimos)-10):
        for j in range(i+5, len(minimos)):
            if minimos[j] > minimos[i]:
                pendiente = (minimos[j] - minimos[i]) / (j - i)
                lineas.append({
                    'tipo': 'alcista',
                    'pendiente': pendiente,
                    'intercepto': minimos[i] - pendiente * i,
                    'toques': 2
                })
    # Tendencia bajista: 2 máximos decrecientes
    for i in range(len(maximos)-10):
        for j in range(i+5, len(maximos)):
            if maximos[j] < maximos[i]:
                pendiente = (maximos[j] - maximos[i]) / (j - i)
                lineas.append({
                    'tipo': 'bajista',
                    'pendiente': pendiente,
                    'intercepto': maximos[i] - pendiente * i,
                    'toques': 2
                })
    return lineas[:5]

# =========================
# EVALUAR ACTIVO (con umbral de estabilidad)
# =========================
def evaluar_activo(indicators, umbral_estabilidad=0.025):
    if indicators['volatilidad'] > umbral_estabilidad:
        return None

    niveles_h = detectar_niveles_horizontales(indicators['df'], num_toques=2)
    if niveles_h:
        nivel = niveles_h[0]
        direccion = 'CALL' if nivel['tipo'] == 'soporte' else 'PUT'
        fuerza = min(30 + nivel['toques'] * 10, 100)
        return {
            'tipo': 'soporte/resistencia',
            'direccion': direccion,
            'nivel': nivel['precio'],
            'fuerza': fuerza,
            'descripcion': f"{nivel['tipo']} ({nivel['toques']} toques)"
        }

    lineas = detectar_lineas_tendencia(indicators['df'])
    if lineas:
        linea = lineas[0]
        idx_actual = len(indicators['df']) - 1
        precio_linea = linea['intercepto'] + linea['pendiente'] * idx_actual
        direccion = 'CALL' if linea['tipo'] == 'alcista' else 'PUT'
        fuerza = 50
        return {
            'tipo': 'tendencia',
            'direccion': direccion,
            'nivel': precio_linea,
            'fuerza': fuerza,
            'descripcion': f"Línea {linea['tipo']}"
        }

    return None
