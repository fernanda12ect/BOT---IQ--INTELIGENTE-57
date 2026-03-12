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

    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # CCI
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    df['cci'] = (tp - sma_tp) / (0.015 * mad)

    # Heiken Ashi
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)

    # Alligator
    df['jaw'] = df['close'].rolling(13).mean().shift(8)
    df['teeth'] = df['close'].rolling(8).mean().shift(5)
    df['lips'] = df['close'].rolling(5).mean().shift(3)

    # Momentum
    df['momentum'] = df['close'] - df['close'].shift(14)

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE SOPORTES Y RESISTENCIAS
# =========================
def detectar_soportes_resistencias(df, num_toques=2, tolerancia=0.001):
    """
    Detecta niveles horizontales con al menos num_toques toques.
    Retorna lista de (precio, tipo) donde tipo es 'soporte' o 'resistencia'.
    """
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    conteo = {}
    for i in range(1, len(df)-1):
        # Máximos locales
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            precio = round(highs.iloc[i], 5)
            conteo[precio] = conteo.get(precio, 0) + 1
        # Mínimos locales
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            precio = round(lows.iloc[i], 5)
            conteo[precio] = conteo.get(precio, 0) + 1

    niveles = []
    precio_actual = df['close'].iloc[-1]
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > precio_actual else 'soporte'
            niveles.append((precio, tipo))
    # Ordenar por cercanía al precio actual
    niveles.sort(key=lambda x: abs(x[0] - precio_actual))
    return niveles

# =========================
# 10 ESTRATEGIAS (cada una devuelve dirección y peso)
# =========================
def estrategia_1_ema_adx(df):
    """EMA9/21 + ADX > 15"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] > 15:
        if last['ema9'] > last['ema21']:
            return 'CALL', 10
        elif last['ema9'] < last['ema21']:
            return 'PUT', 10
    return None, 0

def estrategia_2_macd_adx(df):
    """MACD cruce señal + ADX < 20 (reversión)"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        if prev['macd'] <= prev['signal'] and last['macd'] > last['signal'] and last['hist'] > 0:
            return 'CALL', 8
        if prev['macd'] >= prev['signal'] and last['macd'] < last['signal'] and last['hist'] < 0:
            return 'PUT', 8
    return None, 0

def estrategia_3_bb_rsi(df):
    """Bollinger + RSI extremo"""
    last = df.iloc[-1]
    if last['close'] <= last['bb_lower'] and last['rsi'] < 30:
        return 'CALL', 9
    if last['close'] >= last['bb_upper'] and last['rsi'] > 70:
        return 'PUT', 9
    return None, 0

def estrategia_4_sar_ema(df):
    """Precio cruza EMA50"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['close'] <= prev['ema50'] and last['close'] > last['ema50']:
        return 'CALL', 7
    if prev['close'] >= prev['ema50'] and last['close'] < last['ema50']:
        return 'PUT', 7
    return None, 0

def estrategia_5_stoch_adx(df):
    """Stochastic oversold/overbought + ADX > 20"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] > 20:
        if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
            return 'CALL', 8
        if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
            return 'PUT', 8
    return None, 0

def estrategia_6_supertrend_ema(df):
    """Simulación de Supertrend con EMAs"""
    last = df.iloc[-1]
    if last['ema9'] > last['ema21'] and last['ema9'] > last['ema50']:
        return 'CALL', 6
    if last['ema9'] < last['ema21'] and last['ema9'] < last['ema50']:
        return 'PUT', 6
    return None, 0

def estrategia_7_heiken_ashi_ema(df):
    """Heiken Ashi + EMA9"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['ha_close'] > prev['ha_open'] and last['ha_close'] > last['ha_open'] and last['close'] > last['ema9']:
        return 'CALL', 7
    if prev['ha_close'] < prev['ha_open'] and last['ha_close'] < last['ha_open'] and last['close'] < last['ema9']:
        return 'PUT', 7
    return None, 0

def estrategia_8_cci_bb(df):
    """CCI + Bollinger"""
    last = df.iloc[-1]
    if last['cci'] > -100 and last['close'] <= last['bb_lower']:
        return 'CALL', 8
    if last['cci'] < 100 and last['close'] >= last['bb_upper']:
        return 'PUT', 8
    return None, 0

def estrategia_9_alligator_momentum(df):
    """Alligator + Momentum"""
    last = df.iloc[-1]
    if last['lips'] > last['teeth'] > last['jaw'] and last['momentum'] > 0:
        return 'CALL', 7
    if last['lips'] < last['teeth'] < last['jaw'] and last['momentum'] < 0:
        return 'PUT', 7
    return None, 0

def estrategia_10_pivot_stoch(df):
    """Pivot points (soportes/resistencias) + Stochastic"""
    niveles = detectar_soportes_resistencias(df, num_toques=1, tolerancia=0.001)
    if not niveles:
        return None, 0
    precio_actual = df['close'].iloc[-1]
    last = df.iloc[-1]
    # Buscar el nivel más cercano
    nivel_cercano, tipo = niveles[0]
    distancia = abs(precio_actual - nivel_cercano) / precio_actual
    if distancia < 0.002:  # 0.2% de distancia
        if tipo == 'soporte' and last['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
            return 'CALL', 9
        if tipo == 'resistencia' and last['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
            return 'PUT', 9
    return None, 0

# Lista de estrategias (nombre, función)
ESTRATEGIAS = [
    ("EMA + ADX", estrategia_1_ema_adx),
    ("MACD reversión", estrategia_2_macd_adx),
    ("BB + RSI", estrategia_3_bb_rsi),
    ("Cruce EMA50", estrategia_4_sar_ema),
    ("Stoch + ADX", estrategia_5_stoch_adx),
    ("Supertrend", estrategia_6_supertrend_ema),
    ("Heiken Ashi", estrategia_7_heiken_ashi_ema),
    ("CCI + BB", estrategia_8_cci_bb),
    ("Alligator", estrategia_9_alligator_momentum),
    ("Pivot + Stoch", estrategia_10_pivot_stoch)
]

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN (consenso de estrategias)
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
        votos_call = 0
        votos_put = 0
        peso_call = 0
        peso_put = 0
        estrategias_activas = []

        for nombre, funcion in ESTRATEGIAS:
            try:
                direccion, peso = funcion(df)
                if direccion:
                    estrategias_activas.append(nombre)
                    if direccion == 'CALL':
                        votos_call += 1
                        peso_call += peso
                    else:
                        votos_put += 1
                        peso_put += peso
            except Exception as e:
                continue

        # Determinar dirección por consenso (mayoría simple, o peso)
        if votos_call + votos_put < 2:  # Necesitamos al menos 2 estrategias
            return None

        if votos_call > votos_put:
            direccion = 'CALL'
            fuerza = peso_call / votos_call if votos_call > 0 else 0
        elif votos_put > votos_call:
            direccion = 'PUT'
            fuerza = peso_put / votos_put if votos_put > 0 else 0
        else:
            # Empate, decidir por peso
            if peso_call > peso_put:
                direccion = 'CALL'
                fuerza = peso_call / votos_call if votos_call > 0 else 0
            else:
                direccion = 'PUT'
                fuerza = peso_put / votos_put if votos_put > 0 else 0

        # Puntuación basada en número de estrategias y peso
        puntuacion = (votos_call + votos_put) * 10 + (peso_call + peso_put)

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': fuerza,
            'votos_call': votos_call,
            'votos_put': votos_put,
            'estrategias': estrategias_activas,
            'puntuacion': puntuacion,
            'precio': df['close'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# DETECCIÓN DE PULLBACK (sensible)
# =========================
def detectar_pullback(df, direccion, umbral_pullback=0.2):
    if len(df) < 5:
        return False
    ultimas = df.iloc[-5:]
    precio_actual = ultimas['close'].iloc[-1]
    atr_actual = df['atr'].iloc[-1]

    if direccion == 'CALL':
        maximo_reciente = ultimas['high'].max()
        if maximo_reciente - precio_actual > umbral_pullback * atr_actual:
            return True
    else:
        minimo_reciente = ultimas['low'].min()
        if precio_actual - minimo_reciente > umbral_pullback * atr_actual:
            return True
    return False

# =========================
# CONFIRMACIÓN DE CRUCE DE EMA (ventana ampliada)
# =========================
def confirmar_cruce_ema(df, direccion, ventana=3):
    if len(df) < ventana + 1:
        return False
    for i in range(1, ventana + 1):
        prev = df.iloc[-i-1]
        last = df.iloc[-i]
        if direccion == 'CALL':
            if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']:
                return True
        else:
            if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']:
                return True
    return False

# =========================
# EVALUAR ACTIVO EN SEGUIMIENTO (para señal)
# =========================
def evaluar_activo_seguimiento(api, asset, direccion_esperada, umbral_pullback=0.2, ventana_cruce=3):
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
        # Verificar que la dirección se mantiene (usando consenso rápido)
        direccion_actual, _ = None, 0
        votos_call = 0
        votos_put = 0
        for _, funcion in ESTRATEGIAS:
            try:
                d, _ = funcion(df)
                if d == 'CALL':
                    votos_call += 1
                elif d == 'PUT':
                    votos_put += 1
            except:
                continue
        if votos_call > votos_put:
            direccion_actual = 'CALL'
        elif votos_put > votos_call:
            direccion_actual = 'PUT'
        else:
            direccion_actual = direccion_esperada  # si hay empate, mantener la esperada

        if direccion_actual != direccion_esperada:
            return False, None, 0, None

        pullback = detectar_pullback(df, direccion_actual, umbral_pullback)
        cruce = confirmar_cruce_ema(df, direccion_actual, ventana_cruce)

        lista_para_entrar = pullback and cruce
        estrategia = f"Pullback ({umbral_pullback} ATR) + cruce EMA (ventana {ventana_cruce})"
        return lista_para_entrar, direccion_actual, 0, estrategia
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, 0, None

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
# SELECCIONAR EL MEJOR ACTIVO DE UNA RONDA
# =========================
def seleccionar_mejor_activo(api, lista_activos, min_estrategias=2):
    """
    Elige el activo con mayor puntuación que tenga al menos min_estrategias votos en la dirección ganadora.
    """
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset)
            if res and (res['votos_call'] + res['votos_put']) >= min_estrategias:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['puntuacion'], reverse=True)
    return mejores[0]
