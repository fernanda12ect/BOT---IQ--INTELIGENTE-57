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
# DETECCIÓN DE TENDENCIA (para filtrar dirección)
# =========================
def detectar_tendencia(df, umbral_adx=20):
    """Retorna dirección de la tendencia ('CALL'/'PUT') y su fuerza (ADX)."""
    last = df.iloc[-1]
    if last['adx'] < umbral_adx:
        return None, 0
    if last['ema9'] > last['ema21'] and last['ema9'] > last['ema50']:
        return 'CALL', last['adx']
    elif last['ema9'] < last['ema21'] and last['ema9'] < last['ema50']:
        return 'PUT', last['adx']
    return None, 0

# =========================
# DETECCIÓN DE NIVELES (Soporte/Resistencia)
# =========================
def detectar_niveles_sr(df, num_toques=2, ventana=100):
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    highs = df['high']
    lows = df['low']
    conteo = defaultdict(int)
    for i in range(1, len(df)-1):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            conteo[round(highs.iloc[i], 5)] += 1
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            conteo[round(lows.iloc[i], 5)] += 1
    niveles = []
    precio_actual = df['close'].iloc[-1]
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > precio_actual else 'soporte'
            niveles.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

# =========================
# CÁLCULO DE FIBONACCI (último movimiento)
# =========================
def calcular_fibonacci(df, ventana=20):
    if len(df) < ventana:
        return None
    segmento = df.iloc[-ventana:]
    maximo = segmento['high'].max()
    minimo = segmento['low'].min()
    diff = maximo - minimo
    return {
        'max': maximo,
        'min': minimo,
        '382': maximo - 0.382 * diff,
        '500': maximo - 0.5 * diff,
        '618': maximo - 0.618 * diff
    }

# =========================
# DETECCIÓN DE ZONAS DE OFERTA/DEMANDA (simplificada)
# =========================
def detectar_zonas_od(df, ventana=20):
    """Detecta zonas de alta actividad de volumen (posibles niveles ocultos)."""
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    zonas = []
    # Buscar velas con volumen > 1.5x promedio
    for i, row in df.iterrows():
        if row['vol_ratio'] > 1.5:
            zonas.append({
                'precio': row['close'],
                'tipo': 'volumen alto',
                'intensidad': row['vol_ratio']
            })
    # Agrupar por cercanía
    zonas_unicas = []
    tolerancia = 0.001
    for z in zonas:
        if not zonas_unicas or abs(z['precio'] - zonas_unicas[-1]['precio']) / z['precio'] > tolerancia:
            zonas_unicas.append(z)
    return zonas_unicas[:3]

# =========================
# 8 ESTRATEGIAS (ahora con confirmación de niveles)
# =========================
# Nota: Cada estrategia ahora devuelve (dirección, peso) si se cumple, y además puede proporcionar un nivel sugerido.
def estrategia_1_divergencia(df, niveles):
    """Divergencia + ADX + cerca de nivel"""
    if len(df) < 5:
        return None, 0, None
    last = df.iloc[-1]
    if last['adx'] < 20:
        return None, 0, None
    # Buscar divergencia (simplificada)
    segmento = df.iloc[-5:]
    min_precio_idx = segmento['low'].idxmin()
    max_precio_idx = segmento['high'].idxmax()
    min_rsi_idx = segmento['rsi'].idxmin()
    max_rsi_idx = segmento['rsi'].idxmax()
    # Divergencia alcista
    if min_precio_idx < min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi']:
            # Buscar soporte cercano
            for n in niveles:
                if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                    return 'CALL', 10, n['precio']
    # Divergencia bajista
    if max_precio_idx > max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi']:
            for n in niveles:
                if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                    return 'PUT', 10, n['precio']
    return None, 0, None

def estrategia_2_cruce_ema(df, niveles):
    """Cruce EMAs + ADX + cerca de nivel"""
    if len(df) < 2:
        return None, 0, None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        return None, 0, None
    if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']:
        for n in niveles:
            if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'CALL', 9, n['precio']
    if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']:
        for n in niveles:
            if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'PUT', 9, n['precio']
    return None, 0, None

def estrategia_3_bb_rsi(df, niveles):
    """Bollinger + RSI extremo + cerca de nivel"""
    last = df.iloc[-1]
    if last['close'] <= last['bb_lower'] and last['rsi'] < 30:
        for n in niveles:
            if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'CALL', 8, n['precio']
    if last['close'] >= last['bb_upper'] and last['rsi'] > 70:
        for n in niveles:
            if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'PUT', 8, n['precio']
    return None, 0, None

def estrategia_4_macd_cruce_senal(df, niveles):
    """MACD cruce señal + cerca de nivel"""
    if len(df) < 2:
        return None, 0, None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] <= prev['signal'] and last['macd'] > last['signal'] and last['hist'] > 0:
        for n in niveles:
            if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'CALL', 8, n['precio']
    if prev['macd'] >= prev['signal'] and last['macd'] < last['signal'] and last['hist'] < 0:
        for n in niveles:
            if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'PUT', 8, n['precio']
    return None, 0, None

def estrategia_5_stoch_adx(df, niveles):
    """Stochastic + ADX + cerca de nivel"""
    if len(df) < 2:
        return None, 0, None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        return None, 0, None
    if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
        for n in niveles:
            if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'CALL', 7, n['precio']
    if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
        for n in niveles:
            if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                return 'PUT', 7, n['precio']
    return None, 0, None

def estrategia_6_heiken_ashi_tendencia(df, niveles):
    """Heiken Ashi (2 velas consecutivas) + EMA + nivel"""
    if len(df) < 3:
        return None, 0, None
    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open = (df['open'].shift(1) + df['close'].shift(1)) / 2
    ha_open = ha_open.fillna(ha_close)
    color1 = 1 if ha_close.iloc[-1] > ha_open.iloc[-1] else -1
    color2 = 1 if ha_close.iloc[-2] > ha_open.iloc[-2] else -1
    last = df.iloc[-1]
    if color1 == 1 and color2 == 1:
        if last['ema9'] > last['ema21']:
            for n in niveles:
                if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                    return 'CALL', 7, n['precio']
    if color1 == -1 and color2 == -1:
        if last['ema9'] < last['ema21']:
            for n in niveles:
                if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                    return 'PUT', 7, n['precio']
    return None, 0, None

def estrategia_7_volume_spike(df, niveles):
    """Pico de volumen + vela grande + cerca de nivel"""
    last = df.iloc[-1]
    if last['vol_ratio'] > 1.8:
        cuerpo = abs(last['close'] - last['open'])
        rango = last['high'] - last['low']
        if cuerpo > rango * 0.6:
            if last['close'] > last['open']:
                for n in niveles:
                    if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                        return 'CALL', 7, n['precio']
            else:
                for n in niveles:
                    if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                        return 'PUT', 7, n['precio']
    return None, 0, None

def estrategia_8_tendencia_adx(df, niveles):
    """ADX > 25 + EMAs alineadas + cerca de nivel"""
    last = df.iloc[-1]
    if last['adx'] > 25:
        if last['ema9'] > last['ema21'] and last['ema9'] > last['ema50']:
            for n in niveles:
                if n['tipo'] == 'soporte' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                    return 'CALL', 6, n['precio']
        if last['ema9'] < last['ema21'] and last['ema9'] < last['ema50']:
            for n in niveles:
                if n['tipo'] == 'resistencia' and abs(last['close'] - n['precio']) / last['close'] < 0.002:
                    return 'PUT', 6, n['precio']
    return None, 0, None

# Lista de estrategias (nombre, función, peso base)
ESTRATEGIAS = [
    ("Divergencia RSI/MACD", estrategia_1_divergencia, 10),
    ("Cruce EMAs", estrategia_2_cruce_ema, 9),
    ("Bollinger + RSI", estrategia_3_bb_rsi, 8),
    ("MACD señal", estrategia_4_macd_cruce_senal, 8),
    ("Stochastic + ADX", estrategia_5_stoch_adx, 7),
    ("Heiken Ashi", estrategia_6_heiken_ashi_tendencia, 7),
    ("Volumen Spike", estrategia_7_volume_spike, 7),
    ("Tendencia ADX", estrategia_8_tendencia_adx, 6)
]

# =========================
# EVALUAR UN ACTIVO (con niveles y tendencia)
# =========================
def evaluar_activo(api, asset):
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
        # Detectar tendencia
        tendencia_dir, fuerza_tendencia = detectar_tendencia(df)
        if tendencia_dir is None:
            return None  # sin tendencia clara, no operamos

        # Detectar niveles
        niveles = detectar_niveles_sr(df, num_toques=2)
        # También podríamos añadir Fibonacci, pero por simplicidad usamos niveles
        # Opcional: añadir Fibonacci
        fib = calcular_fibonacci(df)

        # Aplicar estrategias
        votos_call = 0
        votos_put = 0
        peso_call = 0
        peso_put = 0
        estrategias_activas = []
        nivel_sugerido = None

        for nombre, func, peso_base in ESTRATEGIAS:
            try:
                direc, peso_extra, nivel = func(df, niveles)
                if direc:
                    estrategias_activas.append(nombre)
                    if direc == 'CALL':
                        votos_call += 1
                        peso_call += peso_base + (peso_extra or 0)
                        if nivel is not None:
                            nivel_sugerido = nivel
                    else:
                        votos_put += 1
                        peso_put += peso_base + (peso_extra or 0)
                        if nivel is not None:
                            nivel_sugerido = nivel
            except Exception as e:
                logger.error(f"Error en estrategia {nombre}: {e}")
                continue

        if votos_call + votos_put == 0:
            return None

        # Decidir dirección
        if peso_call > peso_put:
            direccion = 'CALL'
            fuerza = (peso_call / (peso_call + peso_put)) * 100
        elif peso_put > peso_call:
            direccion = 'PUT'
            fuerza = (peso_put / (peso_call + peso_put)) * 100
        else:
            # Empate
            return None

        # Verificar que la dirección coincida con la tendencia principal
        if direccion != tendencia_dir:
            return None  # no operar en contra de la tendencia

        # Ajustar fuerza con la tendencia
        fuerza = (fuerza + fuerza_tendencia) / 2

        return {
            'asset': asset,
            'direccion': direccion,
            'estrategias': estrategias_activas,
            'fuerza': min(fuerza, 100),
            'nivel': nivel_sugerido,
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
