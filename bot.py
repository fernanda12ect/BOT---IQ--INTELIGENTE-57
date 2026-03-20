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

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# 8 ESTRATEGIAS EFECTIVAS (cada una devuelve dirección y peso)
# =========================

def estrategia_1_divergencia(df):
    """Divergencia RSI/MACD + ADX > 20 + volumen"""
    if len(df) < 5:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] < 20:
        return None, 0

    segmento = df.iloc[-5:]
    min_precio_idx = segmento['low'].idxmin()
    max_precio_idx = segmento['high'].idxmax()
    min_rsi_idx = segmento['rsi'].idxmin()
    max_rsi_idx = segmento['rsi'].idxmax()
    min_macd_idx = segmento['macd'].idxmin()
    max_macd_idx = segmento['macd'].idxmax()

    # Volumen confirmación
    ultimas = df.iloc[-3:]
    vol_alcista = ultimas[ultimas['close'] > ultimas['open']]['volume'].mean()
    vol_bajista = ultimas[ultimas['close'] < ultimas['open']]['volume'].mean()
    vol_total = ultimas['volume'].mean()

    # Divergencia alcista RSI
    if min_precio_idx < min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi'] and vol_alcista > vol_total * 1.2:
            return 'CALL', 10
    # Divergencia bajista RSI
    if max_precio_idx > max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi'] and vol_bajista > vol_total * 1.2:
            return 'PUT', 10
    # Divergencia alcista MACD
    if min_precio_idx < min_macd_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_macd_idx, 'low']:
        if segmento.loc[min_macd_idx, 'macd'] > segmento.loc[min_precio_idx, 'macd'] and vol_alcista > vol_total * 1.2:
            return 'CALL', 10
    # Divergencia bajista MACD
    if max_precio_idx > max_macd_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_macd_idx, 'high']:
        if segmento.loc[max_macd_idx, 'macd'] < segmento.loc[max_precio_idx, 'macd'] and vol_bajista > vol_total * 1.2:
            return 'PUT', 10
    return None, 0

def estrategia_2_cruce_ema(df):
    """EMA9 cruza EMA21 + ADX > 20 + RSI en zona no extrema"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        return None, 0
    if 30 <= last['rsi'] <= 70:
        if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']:
            return 'CALL', 9
        if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']:
            return 'PUT', 9
    return None, 0

def estrategia_3_bb_rsi(df):
    """Bollinger + RSI extremo (sobreventa/sobrecompra)"""
    last = df.iloc[-1]
    if last['close'] <= last['bb_lower'] and last['rsi'] < 30:
        return 'CALL', 8
    if last['close'] >= last['bb_upper'] and last['rsi'] > 70:
        return 'PUT', 8
    return None, 0

def estrategia_4_macd_cruce_senal(df):
    """MACD cruza línea de señal con histograma expandiéndose"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] <= prev['signal'] and last['macd'] > last['signal'] and last['hist'] > 0:
        return 'CALL', 8
    if prev['macd'] >= prev['signal'] and last['macd'] < last['signal'] and last['hist'] < 0:
        return 'PUT', 8
    return None, 0

def estrategia_5_stoch_adx(df):
    """Stochastic oversold/overbought + ADX > 20"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        return None, 0
    if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
        return 'CALL', 7
    if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
        return 'PUT', 7
    return None, 0

def estrategia_6_heiken_ashi_ema(df):
    """Heiken Ashi + EMA9 (tendencia)"""
    if len(df) < 2:
        return None, 0
    # Calcular Heiken Ashi simplificado
    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open = (df['open'].shift(1) + df['close'].shift(1)) / 2
    last = df.iloc[-1]
    if ha_close.iloc[-1] > ha_open.iloc[-1] and last['close'] > last['ema9']:
        return 'CALL', 7
    if ha_close.iloc[-1] < ha_open.iloc[-1] and last['close'] < last['ema9']:
        return 'PUT', 7
    return None, 0

def estrategia_7_volume_spike(df):
    """Pico de volumen + vela grande en dirección"""
    last = df.iloc[-1]
    if last['vol_ratio'] > 1.8:
        cuerpo = abs(last['close'] - last['open'])
        rango = last['high'] - last['low']
        if cuerpo > rango * 0.6:
            if last['close'] > last['open']:
                return 'CALL', 7
            else:
                return 'PUT', 7
    return None, 0

def estrategia_8_tendencia_adx(df):
    """ADX > 25 y EMAs alineadas"""
    last = df.iloc[-1]
    if last['adx'] > 25:
        if last['ema9'] > last['ema21'] and last['ema9'] > last['ema50']:
            return 'CALL', 6
        if last['ema9'] < last['ema21'] and last['ema9'] < last['ema50']:
            return 'PUT', 6
    return None, 0

# Lista de estrategias (nombre, función, peso base)
ESTRATEGIAS = [
    ("Divergencia RSI/MACD", estrategia_1_divergencia, 10),
    ("Cruce EMAs", estrategia_2_cruce_ema, 9),
    ("Bollinger + RSI", estrategia_3_bb_rsi, 8),
    ("MACD señal", estrategia_4_macd_cruce_senal, 8),
    ("Stochastic + ADX", estrategia_5_stoch_adx, 7),
    ("Heiken Ashi + EMA9", estrategia_6_heiken_ashi_ema, 7),
    ("Volumen Spike", estrategia_7_volume_spike, 7),
    ("Tendencia ADX", estrategia_8_tendencia_adx, 6)
]

# =========================
# EVALUAR UN ACTIVO (con votación)
# =========================
def evaluar_activo(api, asset):
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

        votos_call = 0
        votos_put = 0
        peso_call = 0
        peso_put = 0
        estrategias_activas = []

        for nombre, func, peso_base in ESTRATEGIAS:
            try:
                direc, peso_extra = func(df)
                if direc:
                    estrategias_activas.append(nombre)
                    if direc == 'CALL':
                        votos_call += 1
                        peso_call += peso_base + (peso_extra or 0)
                    else:
                        votos_put += 1
                        peso_put += peso_base + (peso_extra or 0)
            except Exception as e:
                logger.error(f"Error en estrategia {nombre}: {e}")
                continue

        if votos_call + votos_put == 0:
            return None

        # Decidir dirección por peso total
        if peso_call > peso_put:
            direccion = 'CALL'
            peso_total = peso_call
            fuerza = (peso_call / (peso_call + peso_put)) * 100 if (peso_call + peso_put) > 0 else 0
        elif peso_put > peso_call:
            direccion = 'PUT'
            peso_total = peso_put
            fuerza = (peso_put / (peso_call + peso_put)) * 100
        else:
            # Empate, decidir por número de votos
            if votos_call > votos_put:
                direccion = 'CALL'
                fuerza = (votos_call / (votos_call + votos_put)) * 100
            elif votos_put > votos_call:
                direccion = 'PUT'
                fuerza = (votos_put / (votos_call + votos_put)) * 100
            else:
                return None

        # Fuerza final combinada (peso y número de estrategias)
        fuerza = min(fuerza + (peso_total / 10), 100)

        return {
            'asset': asset,
            'direccion': direccion,
            'estrategias': estrategias_activas,
            'fuerza': fuerza,
            'precio': df['close'].iloc[-1],
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
        otc_count = 0
        real_count = 0
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if '-OTC' in asset:
                        otc_count += 1
                        if tipo_mercado in ['OTC', 'AMBOS']:
                            activos.append(asset)
                    else:
                        real_count += 1
                        if tipo_mercado in ['REAL', 'AMBOS']:
                            activos.append(asset)
        logger.info(f"Activos disponibles: OTC={otc_count}, REAL={real_count}, total={len(activos)}")
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
# SELECCIONAR EL MEJOR ACTIVO (mayor fuerza)
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
