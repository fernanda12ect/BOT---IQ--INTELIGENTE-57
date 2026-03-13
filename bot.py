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
# INDICADORES
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    # ADX
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
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
    Retorna dirección ('CALL'/'PUT') si se cumplen:
    - ADX > umbral (o >18 y subiendo)
    - Cruce de EMA9 y EMA21 en dirección
    - Cruce de Stochastic %K sobre %D en dirección
    """
    if len(df) < 50:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # Verificar ADX
    adx_ok = last['adx'] > umbral_adx
    # Opcional: ADX subiendo en últimas 3 velas
    if not adx_ok and len(df) >= 3:
        adx_series = df['adx'].iloc[-3:].values
        if all(adx_series[i] <= adx_series[i+1] for i in range(len(adx_series)-1)) and last['adx'] > 18:
            adx_ok = True

    if not adx_ok:
        return None

    # Cruce de EMA
    ema_cruce_call = prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
    ema_cruce_put = prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']

    # Cruce de Stochastic
    stoch_cruce_call = prev['stoch_k'] <= prev['stoch_d'] and last['stoch_k'] > last['stoch_d']
    stoch_cruce_put = prev['stoch_k'] >= prev['stoch_d'] and last['stoch_k'] < last['stoch_d']

    if ema_cruce_call and stoch_cruce_call:
        return 'CALL'
    elif ema_cruce_put and stoch_cruce_put:
        return 'PUT'
    return None

# =========================
# DETECCIÓN DE ÚLTIMO IMPULSO Y NIVELES FIBONACCI
# =========================
def detectar_impulso_fib(df, direccion, ventana=20):
    """
    Encuentra el último impulso (máximo y mínimo) en las últimas `ventana` velas.
    Calcula niveles Fibonacci (38.2%, 50%, 61.8%) y devuelve el nivel más cercano al precio actual.
    También devuelve la zona de entrada con ATR.
    """
    if len(df) < ventana:
        return None, None
    segmento = df.iloc[-ventana:].copy()
    if direccion == 'CALL':
        # Impulso alcista: buscamos mínimo y máximo
        minimo = segmento['low'].min()
        maximo = segmento['high'].max()
        movimiento = maximo - minimo
        niveles = {
            '382': maximo - movimiento * 0.382,
            '500': maximo - movimiento * 0.5,
            '618': maximo - movimiento * 0.618
        }
        # Para CALL, el retroceso es desde el máximo hacia abajo
        nivel_retroceso = min(niveles.values(), key=lambda x: abs(x - df['close'].iloc[-1]))
        # Zona de entrada: nivel_retroceso ± 0.5 * ATR
        atr_actual = df['atr'].iloc[-1]
        zona_inferior = nivel_retroceso - 0.5 * atr_actual
        zona_superior = nivel_retroceso + 0.5 * atr_actual
        return nivel_retroceso, (zona_inferior, zona_superior)
    else:  # PUT
        minimo = segmento['low'].min()
        maximo = segmento['high'].max()
        movimiento = maximo - minimo
        niveles = {
            '382': minimo + movimiento * 0.382,
            '500': minimo + movimiento * 0.5,
            '618': minimo + movimiento * 0.618
        }
        nivel_retroceso = min(niveles.values(), key=lambda x: abs(x - df['close'].iloc[-1]))
        atr_actual = df['atr'].iloc[-1]
        zona_inferior = nivel_retroceso - 0.5 * atr_actual
        zona_superior = nivel_retroceso + 0.5 * atr_actual
        return nivel_retroceso, (zona_inferior, zona_superior)

# =========================
# DETECCIÓN DE VELA DE RECHAZO
# =========================
def es_vela_rechazo(vela, direccion):
    """
    Determina si una vela (dict con open, high, low, close) es de rechazo.
    Para CALL (rechazo bajista que termina en alcista): mecha inferior larga, cierre > apertura.
    Para PUT (rechazo alcista que termina en bajista): mecha superior larga, cierre < apertura.
    """
    cuerpo = abs(vela['close'] - vela['open'])
    rango = vela['high'] - vela['low']
    if rango == 0:
        return False
    if direccion == 'CALL':
        # Mecha inferior (open - low) o (close - low) si es alcista
        mecha_inferior = min(vela['open'], vela['close']) - vela['low']
        return mecha_inferior > cuerpo * 0.5 and vela['close'] > vela['open']
    else:  # PUT
        mecha_superior = vela['high'] - max(vela['open'], vela['close'])
        return mecha_superior > cuerpo * 0.5 and vela['close'] < vela['open']

# =========================
# EVALUAR ACTIVO PARA SEÑAL (estrategia completa)
# =========================
def evaluar_activo_senal(api, asset):
    """
    Evalúa si el activo cumple la estrategia completa:
    1. Dirección confirmada (EMA+Stoch+ADX)
    2. Precio en zona de Fibonacci (último impulso)
    3. Vela de rechazo en esa zona
    Retorna (direccion, fuerza, nivel_fib, zona) o None.
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
        direccion = detectar_direccion(df, umbral_adx=20)
        if direccion is None:
            return None

        # Detectar niveles Fibonacci del último impulso
        nivel_fib, zona = detectar_impulso_fib(df, direccion, ventana=20)
        if nivel_fib is None:
            return None

        # Verificar si el precio actual está en la zona
        precio_actual = df['close'].iloc[-1]
        if not (zona[0] <= precio_actual <= zona[1]):
            return None

        # Verificar vela de rechazo (última vela completa)
        ultima_vela = df.iloc[-1]
        if not es_vela_rechazo(ultima_vela, direccion):
            return None

        # Calcular fuerza (podría basarse en ADX y volumen)
        fuerza = min(df['adx'].iloc[-1] + df['vol_ratio'].iloc[-1] * 10, 100)

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': fuerza,
            'nivel_fib': nivel_fib,
            'zona': zona,
            'precio': precio_actual,
            'adx': df['adx'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS ABIERTOS
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
def buscar_mejor_senal(api, tipo_mercado, min_fuerza=50):
    """
    Escanea todos los activos y retorna el que tenga la mejor señal (mayor fuerza).
    """
    activos = obtener_activos_abiertos(api, tipo_mercado)
    mejores = []
    for asset in activos:
        res = evaluar_activo_senal(api, asset)
        if res and res['fuerza'] >= min_fuerza:
            mejores.append(res)
        time.sleep(0.1)
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['fuerza'], reverse=True)
    return mejores[0]
