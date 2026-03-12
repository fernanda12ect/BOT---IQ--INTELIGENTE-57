import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import pytz

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# INDICADORES COMUNES
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR
    high, low, close = df['high'], df['low'], df['close']
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

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE TENDENCIA (menos estricta)
# =========================
def detectar_tendencia_suave(df):
    """
    Detecta tendencia permitiendo pequeñas correcciones.
    Retorna 'CALL', 'PUT' o None, junto con fuerza.
    """
    if len(df) < 20:
        return None, 0
    ultimas = df.iloc[-20:]
    highs = ultimas['high'].values
    lows = ultimas['low'].values
    closes = ultimas['close'].values

    # Tendencia alcista: la mayoría de los máximos y mínimos son crecientes
    count_high_creciente = sum(highs[i] <= highs[i+1] for i in range(len(highs)-1))
    count_low_creciente = sum(lows[i] <= lows[i+1] for i in range(len(lows)-1))
    if count_high_creciente >= 12 and count_low_creciente >= 12:
        fuerza = df['adx'].iloc[-1] + (df['vol_ratio'].iloc[-1] * 10)
        return 'CALL', fuerza

    # Tendencia bajista
    count_high_decreciente = sum(highs[i] >= highs[i+1] for i in range(len(highs)-1))
    count_low_decreciente = sum(lows[i] >= lows[i+1] for i in range(len(lows)-1))
    if count_high_decreciente >= 12 and count_low_decreciente >= 12:
        fuerza = df['adx'].iloc[-1] + (df['vol_ratio'].iloc[-1] * 10)
        return 'PUT', fuerza

    return None, 0

# =========================
# ESTRATEGIA 1: CRUCE DE EMAs
# =========================
def estrategia_ema_crossover(df):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    last = df.iloc[-1]
    if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21'] and last['vol_ratio'] > 1.2:
        return 'CALL', 60 + last['vol_ratio']*5
    if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21'] and last['vol_ratio'] > 1.2:
        return 'PUT', 60 + last['vol_ratio']*5
    return None

# =========================
# ESTRATEGIA 2: RSI EXTREMO
# =========================
def estrategia_rsi_extremo(df):
    last = df.iloc[-1]
    if last['rsi'] < 30 and last['vol_ratio'] > 1.5:
        return 'CALL', 70
    if last['rsi'] > 70 and last['vol_ratio'] > 1.5:
        return 'PUT', 70
    return None

# =========================
# ESTRATEGIA 3: TENDENCIA SUAVE + VOLUMEN
# =========================
def estrategia_tendencia_suave(df):
    direccion, fuerza = detectar_tendencia_suave(df)
    if direccion and fuerza > 15:
        return direccion, fuerza
    return None

# =========================
# ESTRATEGIA 4: BREAKOUT DE MÁXIMO/MÍNIMO RECIENTE
# =========================
def estrategia_breakout(df):
    if len(df) < 10:
        return None
    ultimas10 = df.iloc[-10:]
    maximo10 = ultimas10['high'].max()
    minimo10 = ultimas10['low'].min()
    last = df.iloc[-1]
    if last['close'] > maximo10 and last['vol_ratio'] > 1.5:
        return 'CALL', 65
    if last['close'] < minimo10 and last['vol_ratio'] > 1.5:
        return 'PUT', 65
    return None

# =========================
# ESTRATEGIA 5: SOPORTE/RESISTENCIA CON VELA
# =========================
def estrategia_sr_vela(df):
    if len(df) < 20:
        return None
    ultimas20 = df.iloc[-20:]
    soporte = ultimas20['low'].min()
    resistencia = ultimas20['high'].max()
    last = df.iloc[-1]
    # Cerca de soporte y vela alcista
    if last['close'] <= soporte * 1.001 and last['close'] > last['open'] and last['vol_ratio'] > 1.3:
        return 'CALL', 60
    # Cerca de resistencia y vela bajista
    if last['close'] >= resistencia * 0.999 and last['close'] < last['open'] and last['vol_ratio'] > 1.3:
        return 'PUT', 60
    return None

# Lista de todas las estrategias
ESTRATEGIAS = [
    estrategia_ema_crossover,
    estrategia_rsi_extremo,
    estrategia_tendencia_suave,
    estrategia_breakout,
    estrategia_sr_vela
]

# =========================
# EVALUAR UN ACTIVO CON MÚLTIPLES ESTRATEGIAS
# =========================
def evaluar_activo(api, asset):
    try:
        candles = api.get_candles(asset, 300, 100, time.time())
        if not candles or len(candles) < 50:
            return None, 0, False, None, 0
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None, 0, False, None, 0

        df = calcular_indicadores(df)

        mejor_senal = None
        mejor_fuerza = 0
        mejor_estrategia = ""
        for estrategia in ESTRATEGIAS:
            try:
                res = estrategia(df)
                if res:
                    direccion, fuerza = res
                    if fuerza > mejor_fuerza:
                        mejor_fuerza = fuerza
                        mejor_senal = direccion
                        mejor_estrategia = estrategia.__name__
            except:
                continue

        if mejor_senal:
            return mejor_senal, mejor_fuerza, True, mejor_estrategia, df['close'].iloc[-1]
        else:
            return None, 0, False, None, df['close'].iloc[-1]
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None, 0, False, None, 0

# =========================
# OBTENER ACTIVOS ABIERTOS (con reintentos)
# =========================
def obtener_activos_abiertos(api, tipo_mercado):
    try:
        open_time = api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if tipo_mercado == 'OTC' and '-OTC' in asset:
                        activos.append(asset)
                    elif tipo_mercado == 'REAL' and '-OTC' not in asset:
                        activos.append(asset)
                    elif tipo_mercado == 'AMBOS':
                        activos.append(asset)
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return []

# =========================
# SELECCIONAR MEJORES ACTIVOS POR RONDAS
# =========================
def seleccionar_mejores_activos_por_rondas(api, tipo_mercado, num_activos, max_por_ronda=10):
    """
    Analiza los activos en rondas de max_por_ronda para no saturar la API.
    Retorna lista de (asset, direccion, fuerza) de los mejores.
    """
    todos = obtener_activos_abiertos(api, tipo_mercado)
    if not todos:
        return []

    # Mezclamos para no sesgar
    import random
    random.shuffle(todos)

    resultados = []
    for i in range(0, len(todos), max_por_ronda):
        ronda = todos[i:i+max_por_ronda]
        for asset in ronda:
            direccion, fuerza, _, _, _ = evaluar_activo(api, asset)
            if direccion and fuerza > 5:  # umbral bajo
                resultados.append((fuerza, asset, direccion))
            time.sleep(0.2)  # pausa entre activos
        # Pequeña pausa entre rondas
        time.sleep(1)

    resultados.sort(reverse=True)
    return [(asset, direc, fuerza) for fuerza, asset, direc in resultados[:num_activos]]
