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
# CALCULAR INDICADORES (incluye ADX y pendiente)
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()

    # ATR y ADX (simplificado)
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # ADX básico
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
    prev = df.iloc[-2] if len(df) > 1 else last

    # Cruce de EMAs
    cruce_ema10_20 = (prev['ema10'] <= prev['ema20'] and last['ema10'] > last['ema20']) or \
                     (prev['ema10'] >= prev['ema20'] and last['ema10'] < last['ema20'])
    direccion_cruce = "CALL" if last['ema10'] > last['ema20'] else "PUT" if last['ema10'] < last['ema20'] else None

    # Volumen relativo
    vol_rel = last['volume'] / last['vol_avg'] if last['vol_avg'] else 1

    # Rango de la vela
    rango = last['high'] - last['low']

    # Volatilidad (rango porcentual en últimos 20 minutos)
    if len(df) >= 20:
        ultimas_20 = df.iloc[-20:]
        precio_min = ultimas_20['low'].min()
        precio_max = ultimas_20['high'].max()
        volatilidad = (precio_max - precio_min) / precio_min if precio_min > 0 else 0
    else:
        volatilidad = 1.0

    # Estabilidad (baja volatilidad)
    estable = volatilidad < 0.015  # menos de 1.5% en 20 minutos

    # Tendencia (ADX > 25 y EMAs alineadas)
    tendencia_fuerte = False
    direccion_tendencia = None
    if last['adx'] > 25 and not pd.isna(last['adx']):
        if last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di']:
            tendencia_fuerte = True
            direccion_tendencia = "CALL"
        elif last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di']:
            tendencia_fuerte = True
            direccion_tendencia = "PUT"

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'ema10': last['ema10'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'cruce_ema': cruce_ema10_20,
        'direccion_cruce': direccion_cruce,
        'vol_rel': vol_rel,
        'rango': rango,
        'atr': last['atr'],
        'adx': last['adx'],
        'tendencia_fuerte': tendencia_fuerte,
        'direccion_tendencia': direccion_tendencia,
        'estable': estable,
        'df': df
    }

# =========================
# DETECTAR NIVELES HORIZONTALES (con calidad de toque)
# =========================
def detectar_niveles_horizontales(df, num_toques=2):
    """
    Busca niveles con al menos `num_toques` toques de calidad.
    Un toque es de calidad si la vela tiene mecha (rechazo) y volumen > 1.2x promedio.
    """
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    closes = df['close']
    opens = df['open']
    volumes = df['volume']
    vol_avg = df['volume'].rolling(20).mean()

    tolerancia = 0.0005
    niveles = defaultdict(lambda: {'toques': 0, 'calidad': 0})

    for idx in range(len(df)):
        # Máximos (posibles resistencias)
        if idx > 0 and idx < len(df)-1:
            if highs.iloc[idx] > highs.iloc[idx-1] and highs.iloc[idx] > highs.iloc[idx+1]:
                precio = round(highs.iloc[idx], 5)
                niveles[precio]['toques'] += 1
                # Calidad: mecha superior larga y volumen
                mecha_sup = highs.iloc[idx] - max(closes.iloc[idx], opens.iloc[idx])
                if mecha_sup > (highs.iloc[idx] - lows.iloc[idx]) * 0.3 and volumes.iloc[idx] > vol_avg.iloc[idx] * 1.2:
                    niveles[precio]['calidad'] += 1

        # Mínimos (posibles soportes)
        if idx > 0 and idx < len(df)-1:
            if lows.iloc[idx] < lows.iloc[idx-1] and lows.iloc[idx] < lows.iloc[idx+1]:
                precio = round(lows.iloc[idx], 5)
                niveles[precio]['toques'] += 1
                mecha_inf = min(closes.iloc[idx], opens.iloc[idx]) - lows.iloc[idx]
                if mecha_inf > (highs.iloc[idx] - lows.iloc[idx]) * 0.3 and volumes.iloc[idx] > vol_avg.iloc[idx] * 1.2:
                    niveles[precio]['calidad'] += 1

    # Filtrar niveles con al menos num_toques y al menos 1 toque de calidad
    niveles_h = []
    for precio, data in niveles.items():
        if data['toques'] >= num_toques and data['calidad'] >= 1:
            tipo = 'resistencia' if precio > df['close'].iloc[-1] else 'soporte'
            niveles_h.append({
                'precio': precio,
                'tipo': tipo,
                'toques': data['toques'],
                'calidad': data['calidad']
            })

    precio_actual = df['close'].iloc[-1]
    niveles_h.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles_h

# =========================
# DETECTAR LÍNEAS DE TENDENCIA (con calidad de toque)
# =========================
def detectar_lineas_tendencia(df):
    """
    Encuentra líneas de tendencia con al menos 2 toques de calidad.
    """
    df = df.iloc[-50:].copy()
    minimos = df['low'].values
    maximos = df['high'].values
    indices = np.arange(len(df))
    vols = df['volume'].values
    vol_avg = df['volume'].rolling(20).mean().values

    lineas = []

    # Tendencia alcista: 2 mínimos crecientes con volumen en los toques
    for i in range(len(minimos)-10):
        for j in range(i+5, len(minimos)):
            if minimos[j] > minimos[i] and (j - i) > 5:
                # Verificar calidad de los toques (volumen > 1.2x promedio)
                if vols[i] > vol_avg[i] * 1.2 and vols[j] > vol_avg[j] * 1.2:
                    pendiente = (minimos[j] - minimos[i]) / (j - i)
                    lineas.append({
                        'tipo': 'alcista',
                        'pendiente': pendiente,
                        'intercepto': minimos[i] - pendiente * i,
                        'toques': 2,
                        'puntos': (i, j)
                    })

    # Tendencia bajista: 2 máximos decrecientes
    for i in range(len(maximos)-10):
        for j in range(i+5, len(maximos)):
            if maximos[j] < maximos[i] and (j - i) > 5:
                if vols[i] > vol_avg[i] * 1.2 and vols[j] > vol_avg[j] * 1.2:
                    pendiente = (maximos[j] - maximos[i]) / (j - i)
                    lineas.append({
                        'tipo': 'bajista',
                        'pendiente': pendiente,
                        'intercepto': maximos[i] - pendiente * i,
                        'toques': 2,
                        'puntos': (i, j)
                    })
    return lineas[:5]

# =========================
# EVALUAR ACTIVO (selección con filtros de calidad)
# =========================
def evaluar_activo(indicators):
    """
    Retorna un dict si el activo es seleccionable:
    - Estabilidad
    - Nivel horizontal con calidad o línea de tendencia con calidad
    - Fuerza basada en toques y calidad
    """
    if not indicators['estable']:
        return None

    # Buscar niveles horizontales primero
    niveles_h = detectar_niveles_horizontales(indicators['df'], num_toques=2)
    if niveles_h:
        nivel = niveles_h[0]
        direccion = 'CALL' if nivel['tipo'] == 'soporte' else 'PUT'
        fuerza = min(nivel['calidad'] * 30 + nivel['toques'] * 10, 100)
        return {
            'tipo': 'soporte/resistencia',
            'direccion': direccion,
            'nivel': nivel['precio'],
            'fuerza': fuerza,
            'descripcion': f"{nivel['tipo']} ({nivel['toques']} toques, {nivel['calidad']} calidad)"
        }

    # Si no hay horizontales, buscar líneas de tendencia
    lineas = detectar_lineas_tendencia(indicators['df'])
    if lineas:
        linea = lineas[0]
        idx_actual = len(indicators['df']) - 1
        precio_linea = linea['intercepto'] + linea['pendiente'] * idx_actual
        direccion = 'CALL' if linea['tipo'] == 'alcista' else 'PUT'
        fuerza = 70  # valor base
        return {
            'tipo': 'tendencia',
            'direccion': direccion,
            'nivel': precio_linea,
            'fuerza': fuerza,
            'descripcion': f"Línea {linea['tipo']} (2 toques calidad)"
        }

    return None
