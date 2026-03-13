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

# Lista de activos comunes (fallback)
FALLBACK_ACTIVOS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC",
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "NZDUSD", "USDCAD"
]

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

    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE DIRECCIÓN (EMA + Stochastic + ADX)
# =========================
def detectar_direccion(df, umbral_adx=20):
    """
    Retorna 'CALL' o 'PUT' si se cumplen:
    - EMA9 > EMA21 (para CALL) o EMA9 < EMA21 (para PUT)
    - Stochastic %K cruza sobre %D (para CALL) o bajo %D (para PUT)
    - ADX > umbral_adx
    Además, verifica que el cruce de Stochastic sea reciente (últimas 2 velas)
    """
    if len(df) < 50:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    if last['adx'] <= umbral_adx:
        return None

    # Cruce de Stochastic (en la última vela)
    cruce_stoch_call = prev['stoch_k'] <= prev['stoch_d'] and last['stoch_k'] > last['stoch_d']
    cruce_stoch_put = prev['stoch_k'] >= prev['stoch_d'] and last['stoch_k'] < last['stoch_d']

    if last['ema9'] > last['ema21'] and cruce_stoch_call:
        return 'CALL'
    elif last['ema9'] < last['ema21'] and cruce_stoch_put:
        return 'PUT'
    return None

# =========================
# CÁLCULO DE NIVELES FIBONACCI
# =========================
def calcular_fibonacci(df, ventana=20):
    """
    Calcula los niveles de Fibonacci del último movimiento (máximo y mínimo en las últimas `ventana` velas).
    Retorna un dict con los niveles 0.382, 0.5, 0.618 y el máximo y mínimo.
    """
    if len(df) < ventana:
        return None
    ultimas = df.iloc[-ventana:]
    maximo = ultimas['high'].max()
    minimo = ultimas['low'].min()
    diff = maximo - minimo
    return {
        'max': maximo,
        'min': minimo,
        '382': maximo - 0.382 * diff if diff > 0 else maximo,
        '500': maximo - 0.5 * diff if diff > 0 else maximo,
        '618': maximo - 0.618 * diff if diff > 0 else maximo
    }

# =========================
# DETECCIÓN DE VELA DE RECHAZO
# =========================
def es_vela_rechazo(df, direccion):
    """
    Determina si la última vela es una vela de rechazo en la dirección esperada.
    Para CALL: vela alcista con mecha inferior larga (pinbar alcista) o envolvente alcista.
    Para PUT: vela bajista con mecha superior larga (pinbar bajista) o envolvente bajista.
    """
    if len(df) < 2:
        return False
    last = df.iloc[-1]
    prev = df.iloc[-2]

    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']
    mecha_inferior = min(last['open'], last['close']) - last['low']
    mecha_superior = last['high'] - max(last['open'], last['close'])

    if direccion == 'CALL':
        # Pinbar alcista: mecha inferior larga (> 2x cuerpo) y cuerpo pequeño
        if mecha_inferior > 2 * cuerpo and cuerpo < rango * 0.3:
            return True
        # Envolvente alcista: vela actual alcista que envuelve a la anterior bajista
        if last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['high'] and last['open'] < prev['low']:
            return True
        # Cierre fuerte: cuerpo > 70% del rango
        if cuerpo > rango * 0.7 and last['close'] > last['open']:
            return True
    else:  # PUT
        if mecha_superior > 2 * cuerpo and cuerpo < rango * 0.3:
            return True
        if last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['low'] and last['open'] > prev['high']:
            return True
        if cuerpo > rango * 0.7 and last['close'] < last['open']:
            return True
    return False

# =========================
# EVALUAR ACTIVO PARA SEÑAL
# =========================
def evaluar_activo(api, asset, umbral_adx=20):
    """
    Evalúa un activo y retorna un dict con la información si cumple las condiciones:
        - dirección (CALL/PUT)
        - nivel Fibonacci de entrada (el más cercano al precio)
        - si hay vela de rechazo en ese nivel
        - precio actual
        - fuerza (ADX)
    Si no cumple, retorna None.
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
        direccion = detectar_direccion(df, umbral_adx)
        if direccion is None:
            return None

        # Calcular niveles Fibonacci
        fib = calcular_fibonacci(df, ventana=20)
        if fib is None:
            return None

        precio_actual = df['close'].iloc[-1]
        # Determinar si el precio está cerca de algún nivel Fibonacci (tolerancia 0.1% o 0.5*ATR)
        atr = df['atr'].iloc[-1]
        niveles = []
        for nivel in ['382', '500', '618']:
            distancia = abs(precio_actual - fib[nivel])
            if distancia < 0.5 * atr or distancia / precio_actual < 0.001:
                niveles.append((fib[nivel], nivel))

        if not niveles:
            return None

        # Tomar el nivel más cercano
        nivel_cercano, nombre_nivel = min(niveles, key=lambda x: abs(x[0] - precio_actual))

        # Verificar vela de rechazo
        rechazo = es_vela_rechazo(df, direccion)

        return {
            'asset': asset,
            'direccion': direccion,
            'nivel_fib': nivel_cercano,
            'nombre_fib': nombre_nivel,
            'rechazo': rechazo,
            'precio': precio_actual,
            'fuerza': df['adx'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS ABIERTOS (con fallback)
# =========================
def obtener_activos_abiertos(api, tipo_mercado="AMBOS"):
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
        logger.info(f"Se obtuvieron {len(activos)} activos abiertos")
        if not activos:
            logger.warning("Usando lista de activos predeterminada (fallback)")
            if tipo_mercado == 'OTC':
                return [a for a in FALLBACK_ACTIVOS if '-OTC' in a]
            elif tipo_mercado == 'REAL':
                return [a for a in FALLBACK_ACTIVOS if '-OTC' not in a]
            else:
                return FALLBACK_ACTIVOS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS

# =========================
# BUSCAR LA MEJOR SEÑAL ENTRE TODOS LOS ACTIVOS
# =========================
def buscar_mejor_senal(api, lista_activos, umbral_adx=20):
    """
    Analiza todos los activos de la lista y retorna el que tenga la mejor señal.
    Prioriza los que tienen vela de rechazo y mayor fuerza.
    """
    candidatos = []
    for asset in lista_activos:
        try:
            res = evaluar_activo(api, asset, umbral_adx)
            if res:
                candidatos.append(res)
            time.sleep(0.1)
        except:
            continue
    if not candidatos:
        return None
    # Ordenar: primero los que tienen rechazo, luego por fuerza (ADX)
    candidatos.sort(key=lambda x: (x['rechazo'], x['fuerza']), reverse=True)
    return candidatos[0]
