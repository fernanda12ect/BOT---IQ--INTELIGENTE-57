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

    # Bollinger Bands
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
# DETECCIÓN DE CONDICIONES BASE (para selección)
# =========================
def condiciones_base(df):
    """
    Retorna (direccion, fuerza) si se cumplen las condiciones base para tendencia:
    - ADX > 20 (o >18 y subiendo)
    - EMA20 y EMA50 alineadas (o precio sobre EMA20)
    - RSI entre 45-55 (opcional, para evitar extremos)
    """
    if len(df) < 50:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    prev2 = df.iloc[-3] if len(df) > 2 else prev

    # Condición ADX
    adx_ok = last['adx'] > 20 or (last['adx'] > 18 and last['adx'] > prev['adx'] > prev2['adx'])
    if not adx_ok:
        return None, 0

    # Dirección basada en EMAs y +DI/-DI
    if last['ema20'] > last['ema50'] and last['plus_di'] > last['minus_di']:
        direccion = 'CALL'
    elif last['ema20'] < last['ema50'] and last['minus_di'] > last['plus_di']:
        direccion = 'PUT'
    else:
        # Si no está clara, usamos precio sobre EMA20
        if last['close'] > last['ema20'] and last['plus_di'] > last['minus_di']:
            direccion = 'CALL'
        elif last['close'] < last['ema20'] and last['minus_di'] > last['plus_di']:
            direccion = 'PUT'
        else:
            return None, 0

    # RSI en rango neutral (opcional, podemos relajar)
    rsi_ok = 40 <= last['rsi'] <= 60
    if not rsi_ok:
        # No descartamos, solo reducimos fuerza
        pass

    fuerza = last['adx'] + (last['vol_ratio'] * 5)
    return direccion, fuerza

# =========================
# DETECCIÓN DE MERCADO LATERAL (para posibles reversiones)
# =========================
def condiciones_lateral(df):
    """
    Detecta si el mercado está lateral: ADX <20 por al menos 10 velas y BB apretadas.
    """
    if len(df) < 20:
        return False
    ultimas_adx = df['adx'].iloc[-10:]
    if all(ultimas_adx < 20):
        bb_estrecho = df['bb_width'].iloc[-1] / df['close'].iloc[-1] < 0.02  # 2% de ancho
        return bb_estrecho
    return False

# =========================
# DETECCIÓN DE PULLBACK A SOPORTE/RESISTENCIA
# =========================
def detectar_pullback(df, direccion):
    """
    Verifica si el precio ha hecho un pullback a una zona de soporte/resistencia.
    Usamos máximos y mínimos recientes (últimas 20 velas) como niveles.
    """
    if len(df) < 20:
        return False
    ultimas20 = df.iloc[-20:]
    precio_actual = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]
    if direccion == 'CALL':
        # Buscamos soporte: mínimo reciente
        soporte = ultimas20['low'].min()
        distancia = abs(precio_actual - soporte)
        return distancia <= atr  # tolerancia 1 ATR
    else:
        # Resistencia
        resistencia = ultimas20['high'].max()
        distancia = abs(resistencia - precio_actual)
        return distancia <= atr

# =========================
# CONFIRMACIÓN FINAL (vela de rechazo/continuación)
# =========================
def confirmacion_final(df, direccion):
    """
    Busca una vela de rechazo en la dirección esperada.
    Para CALL: vela alcista con mecha inferior larga (rechazo de soporte).
    Para PUT: vela bajista con mecha superior larga.
    """
    if len(df) < 1:
        return False
    last = df.iloc[-1]
    rango = last['high'] - last['low']
    if rango == 0:
        return False
    if direccion == 'CALL':
        # Mecha inferior larga (rechazo)
        mecha_inf = min(last['open'], last['close']) - last['low']
        return mecha_inf > 0.5 * rango and last['close'] > last['open']
    else:
        mecha_sup = last['high'] - max(last['open'], last['close'])
        return mecha_sup > 0.5 * rango and last['close'] < last['open']

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN
# =========================
def evaluar_activo_seleccion(api, asset):
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
        direccion, fuerza = condiciones_base(df)
        if direccion is None:
            # Verificar si es lateral
            if condiciones_lateral(df):
                return {'asset': asset, 'tipo': 'lateral', 'fuerza': 10}
            return None

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': fuerza,
            'tipo': 'tendencia',
            'precio': df['close'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# EVALUAR ACTIVO EN SEGUIMIENTO (para confirmación)
# =========================
def evaluar_activo_seguimiento(api, asset, direccion_esperada, tipo='tendencia'):
    try:
        candles = api.get_candles(asset, 300, 100, time.time())
        if not candles or len(candles) < 50:
            return False, None, 0
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return False, None, 0

        df = calcular_indicadores(df)
        if tipo == 'tendencia':
            # Verificar que la tendencia sigue
            direccion_actual, fuerza = condiciones_base(df)
            if direccion_actual != direccion_esperada:
                return False, None, 0
            # Verificar pullback y confirmación
            pullback_ok = detectar_pullback(df, direccion_actual)
            confirmacion_ok = confirmacion_final(df, direccion_actual)
            if pullback_ok and confirmacion_ok:
                return True, direccion_actual, fuerza
        else:  # lateral
            # Buscar vela de reversión
            if confirmacion_final(df, 'CALL') or confirmacion_final(df, 'PUT'):
                # Determinar dirección por la vela
                last = df.iloc[-1]
                direccion = 'CALL' if last['close'] > last['open'] else 'PUT'
                return True, direccion, 30  # fuerza baja
        return False, None, 0
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, 0

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
# SELECCIONAR EL MEJOR ACTIVO DE UNA RONDA
# =========================
def seleccionar_mejor_activo(api, lista_activos):
    """
    Elige el activo con mayor fuerza (o lateral) que cumpla condiciones base.
    """
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset)
            if res:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    # Ordenar por fuerza descendente, dando prioridad a tendencia sobre lateral
    mejores.sort(key=lambda x: (x.get('tipo') == 'tendencia', x['fuerza']), reverse=True)
    return mejores[0]
