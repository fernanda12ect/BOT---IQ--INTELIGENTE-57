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

# Lista de activos objetivo (puedes ampliarla o hacerla configurable)
ACTIVOS_TARGET = [
    "Volatility 75 Index", "Volatility 100 Index", "Crash 500 Index", "Boom 500 Index",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"
]

# =========================
# INDICADORES COMUNES
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()  # para niveles

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
# DETECCIÓN DE TENDENCIA
# =========================
def detectar_tendencia(df):
    """
    Retorna: direccion ('CALL'/'PUT'), fuerza (ADX), y si la tendencia es válida.
    Condiciones: ADX > 18 y al menos no esté cayendo en las últimas 3 velas (opcional),
                 y +DI/-DI indican dirección.
    """
    if len(df) < 50:
        return None, 0, False
    last = df.iloc[-1]
    adx = last['adx']
    if adx > 18:
        # Verificar dirección
        if last['plus_di'] > last['minus_di']:
            direccion = 'CALL'
        elif last['plus_di'] < last['minus_di']:
            direccion = 'PUT'
        else:
            return None, adx, False
        # Opcional: verificar que ADX no esté cayendo bruscamente
        if len(df) >= 3:
            adx_prev = df['adx'].iloc[-3:].mean()
            if adx < adx_prev * 0.9:  # si ha caído más del 10%
                return direccion, adx, False
        return direccion, adx, True
    return None, adx, False

# =========================
# DETECCIÓN DE PULLBACK A NIVEL
# =========================
def detectar_pullback(df, direccion):
    """
    Detecta si el precio está cerca de un nivel de soporte/resistencia relevante.
    Usamos EMA100 como nivel dinámico, y máximos/mínimos de las últimas 50 velas.
    Retorna True si el precio está dentro de 1x ATR del nivel.
    """
    if len(df) < 50:
        return False
    last = df.iloc[-1]
    precio = last['close']
    atr = last['atr']
    if direccion == 'CALL':
        # Buscar soporte: mínimo de las últimas 50 velas y EMA100
        soporte = min(df['low'].iloc[-50:].min(), df['ema100'].iloc[-1])
        if precio - soporte <= atr:
            return True
    else:  # PUT
        resistencia = max(df['high'].iloc[-50:].max(), df['ema100'].iloc[-1])
        if resistencia - precio <= atr:
            return True
    return False

# =========================
# CONFIRMACIÓN EXTRA
# =========================
def confirmacion_extra(df, direccion):
    """
    RSI entre 45-55, y vela de rechazo/continuación.
    Vela de rechazo: mecha larga en dirección contraria.
    Vela de continuación: cuerpo grande.
    """
    if len(df) < 2:
        return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    rsi = last['rsi']
    if not (45 <= rsi <= 55):
        return False

    # Vela de rechazo
    if direccion == 'CALL':
        # Vela alcista con mecha inferior larga
        cuerpo = last['close'] - last['open']
        mecha_inf = last['open'] - last['low'] if last['open'] > last['close'] else last['close'] - last['low']
        if last['close'] > last['open'] and mecha_inf > cuerpo * 0.5:
            return True
    else:  # PUT
        cuerpo = last['open'] - last['close']
        mecha_sup = last['high'] - last['open'] if last['open'] < last['close'] else last['high'] - last['close']
        if last['close'] < last['open'] and mecha_sup > cuerpo * 0.5:
            return True

    # Vela de continuación (cuerpo grande)
    rango = last['high'] - last['low']
    cuerpo = abs(last['close'] - last['open'])
    if cuerpo > rango * 0.7:
        return True

    return False

# =========================
# DETECCIÓN DE MERCADO LATERAL
# =========================
def detectar_lateral(df):
    """
    ADX < 20 por al menos 10 velas, Bollinger Bands estrechas, y vela de reversión.
    Retorna True y la dirección probable de la reversión (CALL/PUT) o None.
    """
    if len(df) < 20:
        return False, None
    # ADX bajo sostenido
    adx_bajo = all(df['adx'].iloc[-10:] < 20)
    if not adx_bajo:
        return False, None
    # Bandas estrechas (ancho < 0.5% del precio medio)
    bb_width_pct = df['bb_width'].iloc[-1] / df['close'].iloc[-1]
    if bb_width_pct > 0.005:
        return False, None
    # Vela de reversión (última vela)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    rango = last['high'] - last['low']
    cuerpo = abs(last['close'] - last['open'])
    if cuerpo > rango * 0.7:
        if last['close'] > last['open']:
            return True, 'CALL'
        else:
            return True, 'PUT'
    return False, None

# =========================
# EVALUACIÓN INICIAL (condiciones base)
# =========================
def evaluar_condiciones_base(api, asset):
    """
    Verifica si el activo cumple las condiciones básicas para ser candidato.
    Retorna un dict con la información o None.
    """
    try:
        candles = api.get_candles(asset, 300, 100, time.time())  # M5
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None

        df = calcular_indicadores(df)

        # Primero verificar si es mercado lateral
        lateral, direccion_lateral = detectar_lateral(df)
        if lateral:
            return {
                'asset': asset,
                'tipo': 'lateral',
                'direccion': direccion_lateral,
                'fuerza': 0,
                'df': df
            }

        # Si no, verificar tendencia
        direccion, fuerza, valida = detectar_tendencia(df)
        if not valida:
            return None

        # Verificar pullback
        pullback = detectar_pullback(df, direccion)
        if not pullback:
            return None

        # Confirmación extra (opcional, pero ayuda)
        confirm = confirmacion_extra(df, direccion)
        if not confirm:
            return None

        return {
            'asset': asset,
            'tipo': 'tendencia',
            'direccion': direccion,
            'fuerza': fuerza,
            'df': df
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# EVALUACIÓN PARA SEGUIMIENTO (confirmación final)
# =========================
def evaluar_confirmacion_final(api, asset, info_candidato):
    """
    Monitorea el activo para detectar el punto de entrada final.
    Para tendencia: esperar pullback + confirmación extra en la misma dirección.
    Para lateral: esperar vela de reversión.
    Retorna (lista_para_entrar, direccion, estrategia)
    """
    try:
        candles = api.get_candles(asset, 300, 50, time.time())  # menos velas para rapidez
        if not candles or len(candles) < 20:
            return False, None, None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 20:
            return False, None, None

        df = calcular_indicadores(df)

        if info_candidato['tipo'] == 'tendencia':
            # Verificar que la tendencia se mantiene
            direccion, fuerza, valida = detectar_tendencia(df)
            if not valida or direccion != info_candidato['direccion']:
                return False, None, None
            # Verificar pullback y confirmación
            pullback = detectar_pullback(df, direccion)
            confirm = confirmacion_extra(df, direccion)
            if pullback and confirm:
                return True, direccion, f"Pullback + confirmación en tendencia {direccion}"
            else:
                return False, None, None
        else:  # lateral
            lateral, direccion = detectar_lateral(df)
            if lateral:
                return True, direccion, "Reversión en mercado lateral"
            else:
                return False, None, None
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, None

# =========================
# OBTENER ACTIVOS (si no se especifica lista)
# =========================
def obtener_activos_disponibles(api, tipo_mercado="AMBOS"):
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
# SELECCIONAR CANDIDATO DE UNA LISTA
# =========================
def buscar_candidato(api, lista_activos):
    """
    Itera sobre la lista de activos y retorna el primero que cumpla condiciones base.
    """
    for asset in lista_activos:
        try:
            candidato = evaluar_condiciones_base(api, asset)
            if candidato:
                return candidato
            time.sleep(0.2)
        except:
            continue
    return None
