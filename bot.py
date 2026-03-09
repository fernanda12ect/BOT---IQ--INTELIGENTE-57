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
    """Obtiene solo activos OTC que estén abiertos en el momento."""
    try:
        open_time = api.get_all_open_time()
        otc = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False) and '-OTC' in asset:
                    otc.append(asset)
        if not otc:
            # Fallback a lista predefinida
            otc = OTC_ASSETS
        return [], otc  # real vacío, otc con los encontrados
    except:
        return [], OTC_ASSETS

# =========================
# CALCULAR INDICADORES BÁSICOS (EMA10, EMA20, ATR, ADX, pendiente)
# =========================
def calcular_indicadores(df):
    """
    df debe tener columnas: open, max, min, close, volume
    Retorna un dict con valores útiles.
    """
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

    # Volumen promedio (20 períodos)
    df['vol_avg'] = df['volume'].rolling(20).mean()

    # ATR (14 períodos)
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # ADX (14 períodos) - simplificado
    df['tr'] = tr
    df['plus_dm'] = np.where((high - high.shift()) > (low.shift() - low), np.maximum(high - high.shift(), 0), 0)
    df['minus_dm'] = np.where((low.shift() - low) > (high - high.shift()), np.maximum(low.shift() - low, 0), 0)
    df['atr_period'] = df['tr'].rolling(14).mean()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr_period'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr_period'])
    df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di']))
    df['adx'] = df['dx'].rolling(14).mean()

    # Pendiente de EMA10 (últimas 3 velas)
    if len(df) >= 4:
        ema10_series = df['ema10'].values
        pendiente_ema10 = (ema10_series[-1] - ema10_series[-4]) / 3  # pendiente por vela
    else:
        pendiente_ema10 = 0

    # Última vela
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # Indicar si hay cruce de EMAs en la última vela
    cruce_ema10_20 = (prev['ema10'] <= prev['ema20'] and last['ema10'] > last['ema20']) or \
                     (prev['ema10'] >= prev['ema20'] and last['ema10'] < last['ema20'])
    direccion_cruce = "CALL" if last['ema10'] > last['ema20'] else "PUT" if last['ema10'] < last['ema20'] else None

    # Volumen relativo
    vol_rel = last['volume'] / last['vol_avg'] if last['vol_avg'] else 1

    # Rango de la vela
    rango = last['high'] - last['low']

    # Rango relativo al ATR
    rango_rel = rango / last['atr'] if last['atr'] > 0 else 0

    # Estabilidad: variación en últimos 10 minutos (10 velas de 1 min)
    if len(df) >= 10:
        ultimas_10 = df.iloc[-10:]
        precio_min = ultimas_10['low'].min()
        precio_max = ultimas_10['high'].max()
        variacion = (precio_max - precio_min) / precio_min if precio_min > 0 else 0
        estable = variacion < 0.008  # menos de 0.8%
    else:
        estable = False

    # Tendencia actual basada en EMAs
    tendencia_actual = None
    if last['ema10'] > last['ema20']:
        tendencia_actual = "CALL"
    elif last['ema10'] < last['ema20']:
        tendencia_actual = "PUT"

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'ema10': last['ema10'],
        'ema20': last['ema20'],
        'cruce_ema': cruce_ema10_20,
        'direccion_cruce': direccion_cruce,
        'vol_rel': vol_rel,
        'rango': rango,
        'rango_rel': rango_rel,
        'atr': last['atr'],
        'adx': last['adx'],
        'pendiente_ema10': pendiente_ema10,
        'tendencia_actual': tendencia_actual,
        'estable': estable,
        'df': df
    }

# =========================
# DETECTAR NIVELES HORIZONTALES (SOPORTE/RESISTENCIA) CON MÍNIMO 2 TOQUES
# =========================
def detectar_niveles_horizontales(df, num_toques=2):
    """
    Busca máximos y mínimos que hayan sido tocados al menos `num_toques` veces.
    Retorna una lista de niveles con su tipo ('soporte' o 'resistencia') y conteo.
    """
    # Tomamos las últimas 100 velas para buscar niveles
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    tolerancia = 0.0005  # 0.05% ajustable

    conteo = defaultdict(int)
    # Contar máximos
    for idx, val in enumerate(highs):
        for j in range(max(0, idx-5), min(len(highs), idx+5)):
            if abs(highs.iloc[j] - val) / val < tolerancia:
                conteo[round(val, 5)] += 1
    # Contar mínimos
    for idx, val in enumerate(lows):
        for j in range(max(0, idx-5), min(len(lows), idx+5)):
            if abs(lows.iloc[j] - val) / val < tolerancia:
                conteo[round(val, 5)] += 1

    # Filtramos los que tengan al menos num_toques
    niveles_h = []
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            # determinar si es soporte o resistencia según posición relativa al precio actual
            tipo = 'resistencia' if precio > df['close'].iloc[-1] else 'soporte'
            niveles_h.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    # Ordenar por cercanía al precio actual
    precio_actual = df['close'].iloc[-1]
    niveles_h.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles_h

# =========================
# DETECTAR LÍNEAS DE TENDENCIA (2 TOQUES)
# =========================
def detectar_lineas_tendencia(df):
    """
    Encuentra posibles líneas de tendencia con 2 toques.
    Retorna una lista de dict con 'tipo' ('alcista'/'bajista'), 'pendiente', 'intercepto' y 'toques'.
    """
    # Usamos mínimos para tendencia alcista (conecta 2 mínimos crecientes)
    # y máximos para tendencia bajista (2 máximos decrecientes)
    # Limitamos a las últimas 50 velas.
    df = df.iloc[-50:].copy()
    minimos = df['low'].values
    maximos = df['high'].values
    indices = np.arange(len(df))

    lineas = []
    # Tendencia alcista: buscar 2 mínimos que sean crecientes
    for i in range(len(minimos)-10):
        for j in range(i+5, len(minimos)):
            if minimos[j] > minimos[i] and (j - i) > 5:
                pendiente = (minimos[j] - minimos[i]) / (j - i)
                lineas.append({
                    'tipo': 'alcista',
                    'pendiente': pendiente,
                    'intercepto': minimos[i] - pendiente * i,
                    'toques': 2,
                    'puntos': (i, j)
                })
    # Tendencia bajista: buscar 2 máximos decrecientes
    for i in range(len(maximos)-10):
        for j in range(i+5, len(maximos)):
            if maximos[j] < maximos[i] and (j - i) > 5:
                pendiente = (maximos[j] - maximos[i]) / (j - i)
                lineas.append({
                    'tipo': 'bajista',
                    'pendiente': pendiente,
                    'intercepto': maximos[i] - pendiente * i,
                    'toques': 2,
                    'puntos': (i, j)
                })
    # Devolvemos las primeras (o las más recientes)
    return lineas[:5]

# =========================
# ESTRATEGIA 1: SOPORTE/RESISTENCIA (EXISTENTE)
# =========================
def evaluar_activo(indicators, umbral_estabilidad=True):
    """
    Retorna un dict con la información del activo si es seleccionable:
    - tipo: 'soporte/resistencia' o 'tendencia'
    - direccion: 'CALL' o 'PUT' según el nivel
    - nivel: precio del nivel (para horizontal) o línea (para tendencia)
    - fuerza: basada en toques y estabilidad
    - descripcion: texto para mostrar
    """
    if umbral_estabilidad and not indicators['estable']:
        return None

    # Buscar niveles horizontales primero
    niveles_h = detectar_niveles_horizontales(indicators['df'], num_toques=2)
    if niveles_h:
        # Tomamos el nivel más cercano
        nivel = niveles_h[0]
        direccion = 'CALL' if nivel['tipo'] == 'soporte' else 'PUT'
        fuerza = min(nivel['toques'] * 20, 100)  # a más toques más fuerza
        return {
            'tipo': 'soporte/resistencia',
            'direccion': direccion,
            'nivel': nivel['precio'],
            'fuerza': fuerza,
            'descripcion': f"{nivel['tipo']} con {nivel['toques']} toques",
            'nivel_info': nivel
        }

    # Si no hay horizontales, buscar líneas de tendencia
    lineas = detectar_lineas_tendencia(indicators['df'])
    if lineas:
        # Elegimos la línea más reciente (con toques más cercanos)
        linea = lineas[0]
        # Calcular precio en la línea en el índice actual
        idx_actual = len(indicators['df']) - 1
        precio_linea = linea['intercepto'] + linea['pendiente'] * idx_actual
        direccion = 'CALL' if linea['tipo'] == 'alcista' else 'PUT'
        fuerza = 60  # valor base
        return {
            'tipo': 'tendencia',
            'direccion': direccion,
            'nivel': precio_linea,
            'fuerza': fuerza,
            'descripcion': f"Línea {linea['tipo']} (2 toques)",
            'linea_info': linea
        }

    return None

# =========================
# ESTRATEGIA 2: IMBALANCE (NIVELES OCULTOS)
# =========================
def estrategia_imbalance(indicators):
    """
    Detecta velas con volumen y rango extremadamente altos, indicando imbalance.
    Retorna dict con dirección, fuerza y descripción si se cumple.
    """
    # Condiciones: volumen relativo > 2.0, rango relativo > 1.5, y tendencia definida
    if indicators['vol_rel'] < 2.0:
        return None
    if indicators['rango_rel'] < 1.5:
        return None
    if indicators['tendencia_actual'] is None:
        return None

    direccion = indicators['tendencia_actual']
    fuerza = min(70 + indicators['vol_rel'] * 10, 100)  # fuerza basada en volumen
    return {
        'tipo': 'imbalance',
        'direccion': direccion,
        'nivel': indicators['close'],  # nivel es el precio actual (señal inmediata)
        'fuerza': fuerza,
        'descripcion': f"Imbalance (vol {indicators['vol_rel']:.1f}x, rango {indicators['rango_rel']:.1f} ATR)"
    }

# =========================
# ESTRATEGIA 3: CONTINUACIÓN DE TENDENCIA FUERTE
# =========================
def estrategia_continuacion(indicators):
    """
    Detecta tendencia fuerte con ADX alto y pendiente de EMA, anticipando continuación.
    """
    if indicators['adx'] is None or pd.isna(indicators['adx']) or indicators['adx'] < 35:
        return None
    if indicators['tendencia_actual'] is None:
        return None
    # Pendiente de EMA10 debe ser coherente con la tendencia
    if indicators['tendencia_actual'] == "CALL" and indicators['pendiente_ema10'] <= 0:
        return None
    if indicators['tendencia_actual'] == "PUT" and indicators['pendiente_ema10'] >= 0:
        return None
    # Volumen relativo > 1.2 para confirmar fuerza
    if indicators['vol_rel'] < 1.2:
        return None

    direccion = indicators['tendencia_actual']
    fuerza = min(indicators['adx'] + 20, 100)
    return {
        'tipo': 'continuacion',
        'direccion': direccion,
        'nivel': indicators['close'],
        'fuerza': fuerza,
        'descripcion': f"Continuación (ADX {indicators['adx']:.1f}, pendiente {indicators['pendiente_ema10']:.5f})"
    }
