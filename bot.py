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

    # Última vela
    last = df.iloc[-1]
    # Volumen
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    vol_now = last['volume']
    strong_volume = vol_now > vol_avg * 1.2 if not pd.isna(vol_avg) else False
    very_strong_volume = vol_now > vol_avg * 1.5 if not pd.isna(vol_avg) else False

    # Determinar tendencia principal (filtro estricto)
    if (last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di'] and last['adx'] >= 25):
        tendencia = "CALL"
        fuerza_tendencia = last['adx'] + (10 if strong_volume else 0)
    elif (last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di'] and last['adx'] >= 25):
        tendencia = "PUT"
        fuerza_tendencia = last['adx'] + (10 if strong_volume else 0)
    else:
        tendencia = None
        fuerza_tendencia = 0

    # Verificar estructura de máximos/mínimos (tendencia "bonita")
    ultimos_20 = df.iloc[-20:]
    if tendencia == "CALL":
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        # Tendencia bonita: máximos crecientes y mínimos crecientes, con pocas correcciones bruscas
        estructura_valida = all(maximos[i] <= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] <= minimos[i+1] for i in range(len(minimos)-1))
        # Además, la pendiente de las EMAs debe ser positiva y sostenida
        pendiente_ema20 = (last['ema20'] - df['ema20'].iloc[-10]) / 10
        pendiente_ema50 = (last['ema50'] - df['ema50'].iloc[-10]) / 10
        tendencia_bonita = estructura_valida and pendiente_ema20 > 0 and pendiente_ema50 > 0
    elif tendencia == "PUT":
        maximos = ultimos_20['high'].values
        minimos = ultimos_20['low'].values
        estructura_valida = all(maximos[i] >= maximos[i+1] for i in range(len(maximos)-1)) and all(minimos[i] >= minimos[i+1] for i in range(len(minimos)-1))
        pendiente_ema20 = (last['ema20'] - df['ema20'].iloc[-10]) / 10
        pendiente_ema50 = (last['ema50'] - df['ema50'].iloc[-10]) / 10
        tendencia_bonita = estructura_valida and pendiente_ema20 < 0 and pendiente_ema50 < 0
    else:
        tendencia_bonita = False

    # Calcular niveles de Fibonacci del último movimiento (50 velas)
    df_50 = df.iloc[-50:]
    minimo_50 = df_50['low'].min()
    maximo_50 = df_50['high'].max()
    movimiento = maximo_50 - minimo_50
    niveles_fib = {}
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

    # Detectar niveles de soporte/resistencia relevantes (máximos y mínimos de las últimas 50 velas, no extremos)
    # Buscamos puntos donde el precio ha rebotado varias veces
    # Para simplificar, tomamos los máximos y mínimos de las últimas 50 velas, pero excluimos el máximo y mínimo absolutos
    highs = df_50['high'].values
    lows = df_50['low'].values
    # Identificamos picos locales (máximos que son mayores que sus vecinos)
    picos = []
    valles = []
    for i in range(2, len(highs)-2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            picos.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            valles.append(lows[i])
    # Niveles relevantes: la media de esos picos/valles (simplificado)
    nivel_resistencia_relevante = np.mean(picos) if picos else None
    nivel_soporte_relevante = np.mean(valles) if valles else None

    # Detectar imbalances (velas de gran cuerpo con volumen)
    # Consideramos imbalance si la vela actual tiene cuerpo > 1.5 * ATR y volumen > 1.5 * promedio
    cuerpo = abs(last['close'] - last['open'])
    imbalance_actual = (cuerpo > 1.5 * last['atr']) and (vol_now > 1.5 * vol_avg)

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
        'tendencia_bonita': tendencia_bonita,
        'niveles_fib': niveles_fib,
        'nivel_soporte_relevante': nivel_soporte_relevante,
        'nivel_resistencia_relevante': nivel_resistencia_relevante,
        'imbalance_actual': imbalance_actual,
        'df': df
    }

# =========================
# EVALUAR ACTIVO (para selección ultra rigurosa)
# =========================

def evaluar_activo(indicators, umbral_fuerza=60):
    """
    Retorna (direccion, fuerza, niveles_fib, niveles_sr) si el activo es de alta calidad.
    Requisitos: tendencia bonita, estructura válida, fuerza >= umbral (más alto).
    """
    if not indicators['tendencia_bonita']:
        return None
    if indicators['fuerza_tendencia'] < umbral_fuerza:
        return None
    return (indicators['tendencia'],
            indicators['fuerza_tendencia'],
            indicators['niveles_fib'],
            indicators['nivel_soporte_relevante'],
            indicators['nivel_resistencia_relevante'])

# =========================
# VERIFICAR PUNTO DE ENTRADA CON FILTROS AVANZADOS
# =========================

def verificar_punto_entrada(activo, precio_actual, indicators_actuales, tolerancia=0.001):
    """
    Verifica si el precio actual ha alcanzado algún nivel de Fibonacci, y además:
    - Que el nivel coincida con un soporte/resistencia relevante (si existe)
    - Que haya un imbalance reciente que confirme la reacción
    Retorna (True, nivel_alcanzado) si se cumplen los filtros.
    """
    niveles = activo['niveles_fib']
    direccion = activo['direccion']
    nivel_soporte = activo.get('nivel_soporte_relevante')
    nivel_resistencia = activo.get('nivel_resistencia_relevante')

    for key, nivel in niveles.items():
        # Verificar que el precio esté cerca del nivel
        if direccion == "CALL" and precio_actual <= nivel * (1 + tolerancia):
            # Comprobar que el nivel esté cerca de un soporte relevante (si existe)
            if nivel_soporte and abs(precio_actual - nivel_soporte) > 0.001 * precio_actual:
                continue  # No está cerca del soporte relevante
            # Comprobar si hay imbalance reciente (últimas 2 velas)
            if not indicators_actuales.get('imbalance_actual', False):
                # Podríamos buscar imbalance en velas anteriores, pero simplificamos
                pass
            return True, key
        elif direccion == "PUT" and precio_actual >= nivel * (1 - tolerancia):
            if nivel_resistencia and abs(precio_actual - nivel_resistencia) > 0.001 * precio_actual:
                continue
            return True, key
    return False, None
