import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import pytz
from collections import defaultdict

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

    # MACD
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']

    # Bollinger Bands
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE SOPORTES Y RESISTENCIAS (niveles con 2+ toques)
# =========================
def detectar_niveles_sr(df, num_toques=2, ventana=50):
    """
    Detecta niveles horizontales con al menos num_toques toques en las últimas ventana velas.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    highs = df['high']
    lows = df['low']
    conteo = {}
    for i in range(1, len(df)-1):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            precio = round(highs.iloc[i], 5)
            conteo[precio] = conteo.get(precio, 0) + 1
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            precio = round(lows.iloc[i], 5)
            conteo[precio] = conteo.get(precio, 0) + 1
    niveles = []
    precio_actual = df['close'].iloc[-1]
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > precio_actual else 'soporte'
            niveles.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    # Ordenar por cercanía
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

# =========================
# DETECCIÓN DE NIVELES DE FIBONACCI (38.2% del último movimiento)
# =========================
def detectar_fibonacci(df, ventana=30):
    """
    Calcula el nivel de Fibonacci 38.2% del último movimiento (máximo-mínimo).
    """
    if len(df) < ventana:
        return None
    df = df.iloc[-ventana:].copy()
    maximo = df['high'].max()
    minimo = df['low'].min()
    movimiento = maximo - minimo
    nivel_382 = maximo - movimiento * 0.382
    return nivel_382

# =========================
# DETECCIÓN DE VELA DE RECHAZO (martillo/estrella fugaz)
# =========================
def es_vela_rechazo(df, direccion_esperada):
    """
    Determina si la última vela es una vela de rechazo en la dirección esperada.
    Para CALL (alcista): martillo (mecha inferior larga, cuerpo pequeño)
    Para PUT (bajista): estrella fugaz (mecha superior larga, cuerpo pequeño)
    """
    if len(df) < 1:
        return False
    last = df.iloc[-1]
    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']
    mecha_inf = min(last['open'], last['close']) - last['low']
    mecha_sup = last['high'] - max(last['open'], last['close'])

    if direccion_esperada == 'CALL':
        if mecha_inf > 2 * cuerpo and cuerpo < rango * 0.3:
            return True
    else:
        if mecha_sup > 2 * cuerpo and cuerpo < rango * 0.3:
            return True
    return False

# =========================
# EVALUAR ACTIVO (tendencia + fuerza + punto de entrada)
# =========================
def evaluar_activo(api, asset):
    """
    Retorna un dict con la información de la señal si cumple:
        - Tendencia fuerte (ADX > 25, EMAs alineadas)
        - Nivel cercano (soporte/resistencia o Fibonacci)
        - Volumen > 1.2x
        - Vela de rechazo en la dirección correcta
    """
    try:
        candles = api.get_candles(asset, 300, 100, time.time())  # 5 min velas
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

        # 1. Determinar tendencia
        if last['adx'] < 25:
            return None
        if last['ema20'] > last['ema50'] and last['ema9'] > last['ema20']:
            tendencia = 'CALL'
        elif last['ema20'] < last['ema50'] and last['ema9'] < last['ema20']:
            tendencia = 'PUT'
        else:
            return None

        # 2. Detectar nivel clave cercano
        niveles = detectar_niveles_sr(df, num_toques=2)
        nivel_fib = detectar_fibonacci(df)
        precio_actual = last['close']

        # Buscar el nivel más cercano (soporte para CALL, resistencia para PUT)
        nivel_cercano = None
        if tendencia == 'CALL':
            # Buscar soporte
            for n in niveles:
                if n['tipo'] == 'soporte' and abs(precio_actual - n['precio']) < 0.5 * last['atr']:
                    nivel_cercano = n
                    break
            if nivel_cercano is None and nivel_fib and precio_actual > nivel_fib:
                if (precio_actual - nivel_fib) < 0.5 * last['atr']:
                    nivel_cercano = {'precio': nivel_fib, 'tipo': 'soporte', 'desc': 'Fibonacci 38.2%'}
        else:  # PUT
            for n in niveles:
                if n['tipo'] == 'resistencia' and abs(precio_actual - n['precio']) < 0.5 * last['atr']:
                    nivel_cercano = n
                    break
            if nivel_cercano is None and nivel_fib and precio_actual < nivel_fib:
                if (nivel_fib - precio_actual) < 0.5 * last['atr']:
                    nivel_cercano = {'precio': nivel_fib, 'tipo': 'resistencia', 'desc': 'Fibonacci 38.2%'}

        if nivel_cercano is None:
            return None

        # 3. Verificar volumen
        if last['vol_ratio'] < 1.2:
            return None

        # 4. Verificar vela de rechazo en la última vela
        if not es_vela_rechazo(df, tendencia):
            return None

        # 5. Calcular fuerza (basada en ADX y volumen)
        fuerza = min(50 + last['adx'] * 0.5 + last['vol_ratio'] * 5, 100)

        return {
            'asset': asset,
            'direccion': tendencia,
            'fuerza': fuerza,
            'nivel': nivel_cercano['precio'],
            'descripcion': nivel_cercano.get('desc', f"{nivel_cercano['tipo']} con {nivel_cercano.get('toques', '?')} toques"),
            'precio': precio_actual,
            'timestamp': datetime.now(ecuador)
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
                    if '-OTC' in asset:
                        if tipo_mercado in ['OTC', 'AMBOS']:
                            activos.append(asset)
                    else:
                        if tipo_mercado in ['REAL', 'AMBOS']:
                            activos.append(asset)
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
# SELECCIONAR EL MEJOR ACTIVO (el que tenga mayor fuerza)
# =========================
def seleccionar_mejor_activo(api, lista_activos):
    mejor = None
    mejor_fuerza = -1
    for asset in lista_activos:
        res = evaluar_activo(api, asset)
        if res and res['fuerza'] > mejor_fuerza:
            mejor_fuerza = res['fuerza']
            mejor = res
        time.sleep(0.1)
    return mejor
