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
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

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

    # Bollinger Bands (20,2)
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']
    df['bb_width'] = df['bb_upper'] - df['bb_lower']

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE TENDENCIA (ADX, EMAs, DI)
# =========================
def detectar_tendencia(df, umbral_adx=20):
    """
    Retorna dirección de tendencia ('CALL'/'PUT') si:
    - ADX > umbral_adx y está subiendo en las últimas 3 velas
    - EMA20 alineada con EMA50 (corta > larga para CALL, inverso para PUT)
    - +DI > -DI para CALL, -DI > +DI para PUT
    """
    if len(df) < 50:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    prev2 = df.iloc[-3] if len(df) > 2 else prev

    # Verificar ADX creciente
    adx_vals = [df['adx'].iloc[-3], df['adx'].iloc[-2], df['adx'].iloc[-1]]
    adx_creciente = adx_vals[0] < adx_vals[1] < adx_vals[2]

    if last['adx'] > umbral_adx and adx_creciente:
        if last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di']:
            return 'CALL'
        elif last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di']:
            return 'PUT'
    return None

# =========================
# DETECCIÓN DE MERCADO LATERAL
# =========================
def es_lateral(df):
    """
    Retorna True si:
    - ADX < 20 por al menos 10 velas
    - Bollinger Bands apretadas (ancho < 0.5% del precio)
    """
    if len(df) < 20:
        return False
    ultimas_20 = df.iloc[-20:]
    adx_bajo = all(ultimas_20['adx'] < 20)
    if not adx_bajo:
        return False
    precio_medio = df['close'].iloc[-1]
    bb_ancho_medio = (df['bb_upper'] - df['bb_lower']).rolling(20).mean().iloc[-1]
    return bb_ancho_medio / precio_medio < 0.005  # 0.5%

# =========================
# DETECCIÓN DE ZONA DE SOPORTE/RESISTENCIA (usando EMAs largas y niveles)
# =========================
def en_zona_sr(df, direccion, tolerancia_atr=1.0):
    """
    Verifica si el precio actual está cerca de un nivel de soporte/resistencia.
    Para CALL: cerca de soporte (EMA100, EMA200 o mínimo reciente)
    Para PUT: cerca de resistencia (EMA100, EMA200 o máximo reciente)
    Tolerancia: 1x ATR (configurable)
    """
    last = df.iloc[-1]
    atr = last['atr']
    precio = last['close']

    # Niveles
    soporte1 = df['low'].rolling(20).min().iloc[-1]
    resistencia1 = df['high'].rolling(20).max().iloc[-1]
    soporte2 = min(df['ema100'].iloc[-1], df['ema200'].iloc[-1])
    resistencia2 = max(df['ema100'].iloc[-1], df['ema200'].iloc[-1])

    if direccion == 'CALL':
        # Buscar soporte cercano
        distancia_s1 = abs(precio - soporte1)
        distancia_s2 = abs(precio - soporte2)
        return (distancia_s1 <= tolerancia_atr * atr) or (distancia_s2 <= tolerancia_atr * atr)
    else:
        distancia_r1 = abs(precio - resistencia1)
        distancia_r2 = abs(precio - resistencia2)
        return (distancia_r1 <= tolerancia_atr * atr) or (distancia_r2 <= tolerancia_atr * atr)

# =========================
# CONFIRMACIÓN DE VELA DE REVERSIÓN/CONTINUACIÓN
# =========================
def vela_confirmacion(df, direccion):
    """
    Para CALL: vela alcista con cierre > apertura, cuerpo > 50% del rango
    Para PUT: vela bajista con cierre < apertura, cuerpo > 50% del rango
    """
    if len(df) < 1:
        return False
    last = df.iloc[-1]
    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']
    if rango == 0:
        return False
    if direccion == 'CALL':
        return last['close'] > last['open'] and cuerpo > 0.5 * rango
    else:
        return last['close'] < last['open'] and cuerpo > 0.5 * rango

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN (fase 1)
# =========================
def evaluar_activo_seleccion(api, asset, umbral_adx=20):
    """
    Retorna un dict con información si el activo cumple condiciones base:
    - Tendencia detectada (ADX, EMAs, DI) O mercado lateral.
    - Para tendencia, también verifica RSI entre 45-55 y zona de S/R.
    Para mercado lateral, verifica vela de reversión.
    """
    try:
        candles = api.get_candles(asset, 300, 100, time.time())
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None

        df = calcular_indicadores(df)
        last = df.iloc[-1]

        # 1. Detectar tendencia
        tendencia = detectar_tendencia(df, umbral_adx)
        if tendencia:
            # Verificar RSI entre 45-55
            rsi_ok = 45 <= last['rsi'] <= 55
            # Verificar zona de soporte/resistencia
            zona_ok = en_zona_sr(df, tendencia, tolerancia_atr=1.0)
            if rsi_ok and zona_ok:
                # Condiciones base cumplidas, listo para seguimiento
                fuerza = last['adx']  # usamos ADX como fuerza
                return {
                    'asset': asset,
                    'tipo': 'tendencia',
                    'direccion': tendencia,
                    'fuerza': fuerza,
                    'precio': last['close'],
                    'rsi': last['rsi'],
                    'atr': last['atr']
                }
        # 2. Detectar mercado lateral
        elif es_lateral(df):
            # Verificar vela de reversión
            # Para lateral, podemos esperar una vela de reversión en cualquier dirección
            # Aquí simplificamos: si hay una vela de reversión fuerte, consideramos señal de entrada inminente
            # Pero para selección, solo marcamos como lateral y esperamos confirmación
            return {
                'asset': asset,
                'tipo': 'lateral',
                'direccion': None,  # se determinará después
                'fuerza': 0,
                'precio': last['close'],
                'rsi': last['rsi'],
                'atr': last['atr']
            }
        return None
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# EVALUAR ACTIVO EN SEGUIMIENTO (fase 2)
# =========================
def evaluar_activo_seguimiento(api, asset, info_seleccion):
    """
    Para un activo ya seleccionado, monitorea hasta que se cumplan las condiciones finales.
    Retorna (lista_para_entrar, direccion, fuerza, estrategia)
    """
    try:
        candles = api.get_candles(asset, 300, 100, time.time())
        if not candles or len(candles) < 50:
            return False, None, 0, None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return False, None, 0, None

        df = calcular_indicadores(df)
        last = df.iloc[-1]

        if info_seleccion['tipo'] == 'tendencia':
            # Para tendencia, esperamos que el precio esté en zona de pullback (ya lo estaba) y ahora vela de confirmación
            direccion = info_seleccion['direccion']
            # Verificar que el RSI siga en rango (opcional)
            rsi_ok = 40 <= last['rsi'] <= 60  # un poco más amplio
            vela_ok = vela_confirmacion(df, direccion)
            if rsi_ok and vela_ok:
                estrategia = f"Pullback en tendencia {direccion} con vela de confirmación"
                return True, direccion, last['adx'], estrategia
        elif info_seleccion['tipo'] == 'lateral':
            # Para lateral, esperamos una vela de reversión clara y que el RSI no esté extremo
            # Podemos tomar la dirección de la vela
            if vela_confirmacion(df, 'CALL'):
                direccion = 'CALL'
                estrategia = "Reversión lateral alcista"
                return True, direccion, last['adx'], estrategia
            elif vela_confirmacion(df, 'PUT'):
                direccion = 'PUT'
                estrategia = "Reversión lateral bajista"
                return True, direccion, last['adx'], estrategia
        return False, None, 0, None
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, 0, None

# =========================
# OBTENER ACTIVOS ABIERTOS
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
# SELECCIONAR EL PRIMER ACTIVO QUE CUMPLA CONDICIONES BASE (de una lista)
# =========================
def seleccionar_primer_activo(api, lista_activos, umbral_adx=20):
    """
    Itera sobre la lista y devuelve el primer activo que cumpla las condiciones base.
    """
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset, umbral_adx)
            if res:
                return res
            time.sleep(0.2)
        except:
            continue
    return None
