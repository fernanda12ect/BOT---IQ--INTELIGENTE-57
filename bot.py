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
# DETECCIÓN DE ZONAS DE OFERTA/DEMANDA (Rally-Base-Caída / Caída-Base-Rally)
# =========================
def detectar_zonas_od(df, ventana=50, sensibilidad=2.0):
    """
    Detecta zonas de oferta (resistencia) y demanda (soporte) basadas en el patrón Rally-Base-Caída / Caída-Base-Rally.
    Retorna una lista de zonas con: tipo ('oferta'/'demanda'), precio_min, precio_max, y fuerza.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    # Identificar máximos y mínimos locales
    highs = df['high']
    lows = df['low']
    indices = np.arange(len(df))

    # Detectar máximos locales (picos)
    picos_high = []
    for i in range(2, len(df)-2):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
           highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
            picos_high.append((i, highs.iloc[i]))

    # Detectar mínimos locales (valles)
    valles_low = []
    for i in range(2, len(df)-2):
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
           lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
            valles_low.append((i, lows.iloc[i]))

    # Buscar patrones Rally-Base-Caída (para oferta)
    zonas_oferta = []
    for i in range(len(picos_high)-1):
        idx1, precio1 = picos_high[i]
        idx2, precio2 = picos_high[i+1]
        if idx2 - idx1 > 5:  # distancia suficiente entre picos
            # Buscar una base (rango estrecho) entre ellos
            segmento = df.iloc[idx1:idx2+1]
            rango = segmento['high'].max() - segmento['low'].min()
            if rango / segmento['close'].mean() < 0.01:  # base estrecha (<1%)
                zonas_oferta.append({
                    'tipo': 'oferta',
                    'precio_min': segmento['low'].min(),
                    'precio_max': segmento['high'].max(),
                    'fuerza': 3 + len(segmento) // 5  # a más velas en la base, más fuerza
                })

    # Buscar patrones Caída-Base-Rally (para demanda)
    zonas_demanda = []
    for i in range(len(valles_low)-1):
        idx1, precio1 = valles_low[i]
        idx2, precio2 = valles_low[i+1]
        if idx2 - idx1 > 5:
            segmento = df.iloc[idx1:idx2+1]
            rango = segmento['high'].max() - segmento['low'].min()
            if rango / segmento['close'].mean() < 0.01:
                zonas_demanda.append({
                    'tipo': 'demanda',
                    'precio_min': segmento['low'].min(),
                    'precio_max': segmento['high'].max(),
                    'fuerza': 3 + len(segmento) // 5
                })

    # Ordenar por cercanía al precio actual
    precio_actual = df['close'].iloc[-1]
    todas = zonas_oferta + zonas_demanda
    for z in todas:
        z['distancia'] = min(abs(precio_actual - z['precio_min']), abs(precio_actual - z['precio_max']))
    todas.sort(key=lambda x: x['distancia'])
    return todas[:3]  # devolver las 3 más cercanas

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
            return 'CALL', 8
        elif last['ema9'] < last['ema21']:
            return 'PUT', 8
    return None, 0

def estrategia_2_macd_adx(df):
    """MACD cruce señal + ADX < 20 (reversión)"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        if prev['macd'] <= prev['signal'] and last['macd'] > last['signal'] and last['hist'] > 0:
            return 'CALL', 7
        if prev['macd'] >= prev['signal'] and last['macd'] < last['signal'] and last['hist'] < 0:
            return 'PUT', 7
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
        return 'CALL', 6
    if prev['close'] >= prev['ema50'] and last['close'] < last['ema50']:
        return 'PUT', 6
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

def estrategia_10_volumen_ema(df):
    """Volumen alto + EMA alineada"""
    last = df.iloc[-1]
    if last['vol_ratio'] > 1.5 and last['ema9'] > last['ema21']:
        return 'CALL', 6
    if last['vol_ratio'] > 1.5 and last['ema9'] < last['ema21']:
        return 'PUT', 6
    return None, 0

# Lista de estrategias (nombre, función, peso base)
ESTRATEGIAS = [
    ("EMA + ADX", estrategia_1_ema_adx, 8),
    ("MACD reversión", estrategia_2_macd_adx, 7),
    ("BB + RSI", estrategia_3_bb_rsi, 9),
    ("Cruce EMA50", estrategia_4_sar_ema, 6),
    ("Stoch + ADX", estrategia_5_stoch_adx, 8),
    ("Supertrend", estrategia_6_supertrend_ema, 6),
    ("Heiken Ashi", estrategia_7_heiken_ashi_ema, 7),
    ("CCI + BB", estrategia_8_cci_bb, 8),
    ("Alligator", estrategia_9_alligator_momentum, 7),
    ("Volumen + EMA", estrategia_10_volumen_ema, 6)
]

# =========================
# DETECCIÓN DE VELA DE CONFIRMACIÓN (rechazo)
# =========================
def es_vela_rechazo(df, direccion_esperada):
    """
    Determina si la última vela es una vela de rechazo (martillo, estrella fugaz, envolvente)
    en la dirección esperada.
    Retorna (True, tipo_vela) o (False, None)
    """
    if len(df) < 2:
        return False, None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']
    mecha_inf = min(last['open'], last['close']) - last['low']
    mecha_sup = last['high'] - max(last['open'], last['close'])

    # Martillo (alcista) - mecha inferior larga, cuerpo pequeño
    if direccion_esperada == 'CALL' and mecha_inf > 2 * cuerpo and cuerpo < rango * 0.3 and last['close'] > last['open']:
        return True, "Martillo alcista"
    # Estrella fugaz (bajista)
    if direccion_esperada == 'PUT' and mecha_sup > 2 * cuerpo and cuerpo < rango * 0.3 and last['close'] < last['open']:
        return True, "Estrella fugaz"
    # Envolvente alcista
    if direccion_esperada == 'CALL' and last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['high'] and last['open'] < prev['low']:
        return True, "Envolvente alcista"
    # Envolvente bajista
    if direccion_esperada == 'PUT' and last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['low'] and last['open'] > prev['high']:
        return True, "Envolvente bajista"
    return False, None

# =========================
# EVALUAR ACTIVO COMPLETO (zonas + votación + confirmación)
# =========================
def evaluar_activo(api, asset, umbral_adx=18):
    """
    Evalúa un activo y retorna un dict con:
        - asset
        - direccion (CALL/PUT)
        - fuerza (consenso ponderado)
        - zona_cercana (dict con tipo, precio_min, precio_max, fuerza_zona)
        - distancia_a_zona (en ATR)
        - vela_confirmacion (bool)
        - tipo_vela (str)
        - vencimiento_sugerido (1,3,5)
        - precio_actual
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
        precio_actual = df['close'].iloc[-1]
        atr_actual = df['atr'].iloc[-1]

        # 1. Detectar zonas de oferta/demanda
        zonas = detectar_zonas_od(df, ventana=50)
        if not zonas:
            return None

        # 2. Tomar la zona más cercana
        zona = zonas[0]
        distancia = min(abs(precio_actual - zona['precio_min']), abs(precio_actual - zona['precio_max'])) / atr_actual

        # 3. Sistema de votación ponderado
        peso_total_call = 0
        peso_total_put = 0
        votos_call = 0
        votos_put = 0

        for nombre, func, peso_base in ESTRATEGIAS:
            try:
                direc, peso_extra = func(df)
                if direc == 'CALL':
                    votos_call += 1
                    peso_total_call += peso_base + (peso_extra or 0)
                elif direc == 'PUT':
                    votos_put += 1
                    peso_total_put += peso_base + (peso_extra or 0)
            except:
                continue

        if votos_call + votos_put < 2:
            return None

        # Dirección ganadora (mayor peso total)
        if peso_total_call > peso_total_put:
            direccion = 'CALL'
            fuerza = peso_total_call / (peso_total_call + peso_total_put) * 100
        elif peso_total_put > peso_total_call:
            direccion = 'PUT'
            fuerza = peso_total_put / (peso_total_call + peso_total_put) * 100
        else:
            return None  # empate

        # 4. Verificar si la zona es coherente con la dirección
        if direccion == 'CALL' and zona['tipo'] != 'demanda':
            return None  # queremos comprar en demanda (soporte)
        if direccion == 'PUT' and zona['tipo'] != 'oferta':
            return None  # queremos vender en oferta (resistencia)

        # 5. Verificar si hay vela de confirmación
        confirmacion, tipo_vela = es_vela_rechazo(df, direccion)

        # 6. Determinar vencimiento sugerido
        if confirmacion:
            if tipo_vela in ["Martillo alcista", "Estrella fugaz"]:
                vencimiento = 1  # velas de reversión fuertes, esperamos movimiento rápido
            elif "Envolvente" in tipo_vela:
                vencimiento = 3  # envolvente tiene más fuerza, pero puede tardar un poco
            else:
                vencimiento = 5  # por defecto
        else:
            # Si no hay confirmación pero la zona es muy fuerte y la fuerza es alta, podemos esperar
            if fuerza > 80 and zona['fuerza'] > 5:
                vencimiento = 5
            else:
                return None  # no hay condiciones suficientes

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': fuerza,
            'zona': zona,
            'distancia': distancia,
            'confirmacion': confirmacion,
            'tipo_vela': tipo_vela,
            'vencimiento': vencimiento,
            'precio': precio_actual
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
def buscar_mejor_senal(api, lista_activos):
    """
    Analiza todos los activos y retorna el que tenga la mejor señal según:
        - confirmación (prioridad)
        - fuerza de la zona
        - fuerza del consenso
    """
    candidatos = []
    for asset in lista_activos:
        try:
            res = evaluar_activo(api, asset)
            if res:
                candidatos.append(res)
            time.sleep(0.1)
        except:
            continue
    if not candidatos:
        return None
    # Ordenar: primero los que tienen confirmación, luego por fuerza de zona, luego por fuerza de consenso
    candidatos.sort(key=lambda x: (x['confirmacion'], x['zona']['fuerza'], x['fuerza']), reverse=True)
    return candidatos[0]
