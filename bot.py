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

    # ADX (simplificado)
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
# DETECCIÓN DE TENDENCIA POR MÁXIMOS Y MÍNIMOS
# =========================
def detectar_tendencia(df):
    """
    Analiza las últimas 20 velas para determinar tendencia alcista o bajista.
    Retorna 'CALL', 'PUT' o None, junto con la fuerza de la tendencia.
    """
    if len(df) < 20:
        return None, 0
    ultimas = df.iloc[-20:]
    highs = ultimas['high'].values
    lows = ultimas['low'].values
    closes = ultimas['close'].values

    # Tendencia alcista: máximos crecientes y mínimos crecientes
    alcista = all(highs[i] <= highs[i+1] for i in range(len(highs)-1)) and all(lows[i] <= lows[i+1] for i in range(len(lows)-1))
    # Tendencia bajista: máximos decrecientes y mínimos decrecientes
    bajista = all(highs[i] >= highs[i+1] for i in range(len(highs)-1)) and all(lows[i] >= lows[i+1] for i in range(len(lows)-1))

    if alcista:
        # Fuerza basada en ADX y volumen
        fuerza = df['adx'].iloc[-1] + (df['vol_ratio'].iloc[-1] * 10)
        return 'CALL', fuerza
    elif bajista:
        fuerza = df['adx'].iloc[-1] + (df['vol_ratio'].iloc[-1] * 10)
        return 'PUT', fuerza
    return None, 0

# =========================
# CONFIRMACIÓN DE CRUCE DE EMAs
# =========================
def confirmar_cruce_ema(df, direccion):
    """
    Verifica si hay cruce de EMAs en la dirección esperada en la última vela.
    """
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    last = df.iloc[-1]
    if direccion == 'CALL':
        return prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
    else:
        return prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']

# =========================
# DETECCIÓN DE AGOTAMIENTO DE LA FUERZA CONTRARIA
# =========================
def agotamiento_fuerza_contraria(df, direccion):
    """
    Analiza las últimas 3 velas para detectar si la fuerza contraria se ha debilitado.
    Para CALL (tendencia alcista), queremos ver que las velas bajistas (si las hay) son pequeñas y con bajo volumen.
    Para PUT, análogo.
    """
    if len(df) < 3:
        return False
    ultimas = df.iloc[-3:]
    if direccion == 'CALL':
        # Buscar velas bajistas en las últimas 3
        velas_bajistas = ultimas[ultimas['close'] < ultimas['open']]
        if len(velas_bajistas) > 0:
            # Verificar que tengan cuerpo pequeño y volumen bajo
            for _, vela in velas_bajistas.iterrows():
                cuerpo = vela['open'] - vela['close']
                rango = vela['high'] - vela['low']
                if cuerpo > rango * 0.3:  # cuerpo significativo
                    return False
                if vela['vol_ratio'] > 1.2:  # volumen alto
                    return False
        # Además, la última vela debería ser alcista
        return ultimas.iloc[-1]['close'] > ultimas.iloc[-1]['open']
    else:
        velas_alcistas = ultimas[ultimas['close'] > ultimas['open']]
        if len(velas_alcistas) > 0:
            for _, vela in velas_alcistas.iterrows():
                cuerpo = vela['close'] - vela['open']
                rango = vela['high'] - vela['low']
                if cuerpo > rango * 0.3:
                    return False
                if vela['vol_ratio'] > 1.2:
                    return False
        return ultimas.iloc[-1]['close'] < ultimas.iloc[-1]['open']

# =========================
# EVALUAR ACTIVO PRINCIPAL (para selección y seguimiento)
# =========================
def evaluar_activo_principal(api, asset, check_agotamiento=False):
    """
    Obtiene datos, calcula tendencia, fuerza y si está listo para entrar.
    Retorna:
        - direccion (CALL/PUT/None)
        - fuerza (float)
        - lista_para_entrar (bool)
        - estrategia (str) o None
        - precio_actual (float)
    """
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
        direccion, fuerza = detectar_tendencia(df)
        if direccion is None:
            return None, 0, False, None, df['close'].iloc[-1]

        # Verificar cruce de EMA para confirmar entrada
        cruce = confirmar_cruce_ema(df, direccion)
        agotamiento = agotamiento_fuerza_contraria(df, direccion) if check_agotamiento else False

        # Condiciones para señal:
        # - Tendencia clara (fuerza mínima)
        # - Cruce de EMA confirmado
        # - Agotamiento de fuerza contraria (si se pide)
        lista_para_entrar = (fuerza > 30) and cruce
        if check_agotamiento:
            lista_para_entrar = lista_para_entrar and agotamiento

        estrategia = f"Tendencia {'alcista' if direccion == 'CALL' else 'bajista'}"
        return direccion, fuerza, lista_para_entrar, estrategia, df['close'].iloc[-1]
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None, 0, False, None, 0

# =========================
# SELECCIONAR EL ACTIVO MÁS CONFIABLE
# =========================
def seleccionar_mejor_activo(api, lista_activos, num_candidatos=10):
    """
    Analiza una lista de activos y retorna el que tenga mayor fuerza de tendencia.
    """
    mejores = []
    for asset in lista_activos[:num_candidatos]:
        direccion, fuerza, _, _, precio = evaluar_activo_principal(api, asset, check_agotamiento=False)
        if direccion and fuerza > 20:
            mejores.append((fuerza, asset, direccion))
        time.sleep(0.2)
    if not mejores:
        return None, None, 0
    mejores.sort(reverse=True)
    return mejores[0][1], mejores[0][2], mejores[0][0]  # asset, direccion, fuerza
