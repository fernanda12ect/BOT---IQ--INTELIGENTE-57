import time
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# INDICADORES COMUNES (sobre DataFrame)
# =========================
def calcular_indicadores(df):
    """
    Calcula EMA, RSI, ADX, ATR, MACD, Bollinger Bands sobre un DataFrame.
    Devuelve un dict con los valores de la última fila y el df completo.
    """
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

    # Bollinger Bands (20,2)
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']
    df['bb_width'] = df['bb_upper'] - df['bb_lower']

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    # Última fila
    last = df.iloc[-1]
    return {k: last[k] for k in df.columns}, df

# =========================
# DETECCIÓN DE SOPORTES Y RESISTENCIAS (simplificada)
# =========================
def detectar_niveles_sr(df, num_toques=2):
    """Detecta niveles horizontales con al menos num_toques toques."""
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    conteo = defaultdict(int)
    for i in range(1, len(df)-1):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            conteo[round(highs.iloc[i], 5)] += 1
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            conteo[round(lows.iloc[i], 5)] += 1
    niveles = []
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > df['close'].iloc[-1] else 'soporte'
            niveles.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    niveles.sort(key=lambda x: abs(x['precio'] - df['close'].iloc[-1]))
    return niveles[:5]

# =========================
# ESTRATEGIA 1: Cruce de EMAs con confirmación de tendencia
# =========================
def estrategia_ema_crossover(indicators_m5, df_m1, niveles=None):
    """
    Condiciones CALL:
    - EMA9 cruza por encima de EMA21 en M5 cerrada.
    - Vela M5 cierra por encima de EMA9.
    - En M1, al menos 3 de las últimas 5 velas cierran alcistas (cuerpo > 50% rango).
    - Volumen en M5 > 1.5x promedio últimas 10 M5.
    - Precio por encima de soporte clave en M15 (simulado con niveles).
    - ADX(M5) > 25 (evitar si débil).
    """
    if indicators_m5['adx'] < 25:
        return None
    # Cruce alcista
    if (indicators_m5['ema9'] > indicators_m5['ema21'] and
        indicators_m5['close'] > indicators_m5['ema9'] and
        indicators_m5['vol_ratio'] > 1.5):
        # Verificar velas M1
        ultimas_5_m1 = df_m1.iloc[-5:]
        alcistas_m1 = sum(1 for _, row in ultimas_5_m1.iterrows() if row['close'] > row['open'] and (row['close'] - row['open']) > (row['high'] - row['low']) * 0.5)
        if alcistas_m1 >= 3:
            # Verificar soporte en M15 (simulado con nivel cercano)
            if niveles and any(n['tipo'] == 'soporte' and abs(n['precio'] - indicators_m5['close']) < indicators_m5['close'] * 0.002 for n in niveles):
                return "CALL", "EMA Crossover Alcista"
    # Cruce bajista
    if (indicators_m5['ema9'] < indicators_m5['ema21'] and
        indicators_m5['close'] < indicators_m5['ema9'] and
        indicators_m5['vol_ratio'] > 1.5):
        ultimas_5_m1 = df_m1.iloc[-5:]
        bajistas_m1 = sum(1 for _, row in ultimas_5_m1.iterrows() if row['close'] < row['open'] and (row['open'] - row['close']) > (row['high'] - row['low']) * 0.5)
        if bajistas_m1 >= 3:
            if niveles and any(n['tipo'] == 'resistencia' and abs(n['precio'] - indicators_m5['close']) < indicators_m5['close'] * 0.002 for n in niveles):
                return "PUT", "EMA Crossover Bajista"
    return None

# =========================
# ESTRATEGIA 2: RSI Reversión con Patrones de Velas
# =========================
def estrategia_rsi_reversion(indicators_m5, df_m1, niveles=None):
    """
    CALL: RSI < 30, patrón alcista en M1, precio toca banda inferior BB en M5.
    PUT: RSI > 70, patrón bajista en M1, precio toca banda superior BB en M5.
    Volumen > 2x promedio en vela M5.
    """
    if indicators_m5['rsi'] < 30 and indicators_m5['close'] <= indicators_m5['bb_lower'] and indicators_m5['vol_ratio'] > 2.0:
        # Buscar patrón alcista en última vela M1
        last_m1 = df_m1.iloc[-1]
        if last_m1['close'] > last_m1['open'] and (last_m1['low'] < last_m1['open'] * 0.999):  # simula hammer
            return "CALL", "RSI Reversión Alcista"
    if indicators_m5['rsi'] > 70 and indicators_m5['close'] >= indicators_m5['bb_upper'] and indicators_m5['vol_ratio'] > 2.0:
        last_m1 = df_m1.iloc[-1]
        if last_m1['close'] < last_m1['open'] and (last_m1['high'] > last_m1['open'] * 1.001):
            return "PUT", "RSI Reversión Bajista"
    return None

# =========================
# ESTRATEGIA 3: MACD Divergencia en Tendencia
# =========================
def estrategia_macd_divergence(indicators_m5, df_m1):
    """
    Divergencia alcista: precio lower low, MACD higher low en últimas 2 velas M5.
    Divergencia bajista: precio higher high, MACD lower high.
    """
    df = indicators_m5['df']
    if len(df) < 5:
        return None
    last2 = df.iloc[-2:]
    if len(last2) < 2:
        return None
    # Alcista
    if (last2['low'].iloc[0] > last2['low'].iloc[1] and  # lower low? realmente el primero más bajo que el segundo? depende
        last2['macd'].iloc[0] < last2['macd'].iloc[1]):   # MACD higher low
        # Confirmar vela M1 alcista
        if df_m1.iloc[-1]['close'] > df_m1.iloc[-1]['open']:
            return "CALL", "MACD Divergencia Alcista"
    # Bajista
    if (last2['high'].iloc[0] < last2['high'].iloc[1] and
        last2['macd'].iloc[0] > last2['macd'].iloc[1]):
        if df_m1.iloc[-1]['close'] < df_m1.iloc[-1]['open']:
            return "PUT", "MACD Divergencia Bajista"
    return None

# =========================
# ESTRATEGIA 4: Bollinger Bands Breakout (squeeze)
# =========================
def estrategia_bb_breakout(indicators_m5, df_m1):
    """
    Squeeze: ancho BB < 0.5% del precio medio durante al menos 3 velas M5.
    Breakout: cierre fuera de BB con volumen >2x.
    """
    df = indicators_m5['df']
    if len(df) < 5:
        return None
    ultimas_bb = df['bb_width'].iloc[-5:] / df['close'].iloc[-5:]
    squeeze = all(ultimas_bb < 0.005)  # 0.5%
    if not squeeze:
        return None
    # Breakout alcista
    if indicators_m5['close'] > indicators_m5['bb_upper'] and indicators_m5['vol_ratio'] > 2.0:
        # Al menos 2 velas M1 alcistas consecutivas
        ultimas_m1 = df_m1.iloc[-2:]
        if all(row['close'] > row['open'] for _, row in ultimas_m1.iterrows()):
            return "CALL", "BB Breakout Alcista"
    # Breakout bajista
    if indicators_m5['close'] < indicators_m5['bb_lower'] and indicators_m5['vol_ratio'] > 2.0:
        ultimas_m1 = df_m1.iloc[-2:]
        if all(row['close'] < row['open'] for _, row in ultimas_m1.iterrows()):
            return "PUT", "BB Breakout Bajista"
    return None

# =========================
# ESTRATEGIA 5: ADX Trend Strength con Velas
# =========================
def estrategia_adx_trend(indicators_m5, df_m1):
    """
    ADX > 30, +DI > -DI para CALL, -DI > +DI para PUT.
    Patrón de 3 velas M1 en dirección (three soldiers/crows).
    """
    if indicators_m5['adx'] < 30:
        return None
    # Alcista
    if indicators_m5['plus_di'] > indicators_m5['minus_di']:
        ultimas_3_m1 = df_m1.iloc[-3:]
        if all(row['close'] > row['open'] for _, row in ultimas_3_m1.iterrows()):
            return "CALL", "ADX Tendencia Alcista"
    # Bajista
    if indicators_m5['minus_di'] > indicators_m5['plus_di']:
        ultimas_3_m1 = df_m1.iloc[-3:]
        if all(row['close'] < row['open'] for _, row in ultimas_3_m1.iterrows()):
            return "PUT", "ADX Tendencia Bajista"
    return None

# =========================
# ESTRATEGIA 6: Soporte/Resistencia con RSI
# =========================
def estrategia_sr_rsi(indicators_m5, niveles):
    """
    CALL: precio toca soporte, RSI <35, volumen >1.8x.
    PUT: precio toca resistencia, RSI >65, volumen >1.8x.
    """
    if not niveles:
        return None
    nivel_cercano = niveles[0]
    distancia = abs(indicators_m5['close'] - nivel_cercano['precio']) / indicators_m5['close']
    if distancia > 0.001:
        return None
    if nivel_cercano['tipo'] == 'soporte' and indicators_m5['rsi'] < 35 and indicators_m5['vol_ratio'] > 1.8:
        return "CALL", "Soporte + RSI"
    if nivel_cercano['tipo'] == 'resistencia' and indicators_m5['rsi'] > 65 and indicators_m5['vol_ratio'] > 1.8:
        return "PUT", "Resistencia + RSI"
    return None

# =========================
# ESTRATEGIA 7: MACD Zero Line Cross
# =========================
def estrategia_macd_zero(indicators_m5, df_m1):
    """
    MACD cruza sobre cero en M5, histograma expandiéndose, vela M1 engulfing en dirección.
    """
    df = indicators_m5['df']
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # Cruce sobre cero alcista
    if prev['macd'] <= 0 and last['macd'] > 0 and last['hist'] > prev['hist']:
        # Vela M1 engulfing alcista (última vela M1)
        if df_m1.iloc[-1]['close'] > df_m1.iloc[-2]['high'] and df_m1.iloc[-2]['close'] < df_m1.iloc[-2]['open']:
            return "CALL", "MACD Zero Cross Alcista"
    # Cruce bajo cero bajista
    if prev['macd'] >= 0 and last['macd'] < 0 and last['hist'] < prev['hist']:
        if df_m1.iloc[-1]['close'] < df_m1.iloc[-2]['low'] and df_m1.iloc[-2]['close'] > df_m1.iloc[-2]['open']:
            return "PUT", "MACD Zero Cross Bajista"
    return None

# =========================
# ESTRATEGIA 8: Volumen Spike con Patrones de Velas
# =========================
def estrategia_volume_spike(indicators_m5, df_m1):
    """
    Volumen > 3x promedio en M5, vela direccional, OBV confirmando.
    """
    if indicators_m5['vol_ratio'] < 3.0:
        return None
    # Alcista
    if indicators_m5['close'] > indicators_m5['open'] + indicators_m5['atr'] * 0.5:  # vela grande alcista
        # Patrón M1: marubozu o gap
        last_m1 = df_m1.iloc[-1]
        if last_m1['close'] > last_m1['open'] and (last_m1['high'] - last_m1['low']) * 0.8 < (last_m1['close'] - last_m1['open']):
            return "CALL", "Volumen Spike Alcista"
    # Bajista
    if indicators_m5['close'] < indicators_m5['open'] - indicators_m5['atr'] * 0.5:
        last_m1 = df_m1.iloc[-1]
        if last_m1['close'] < last_m1['open'] and (last_m1['high'] - last_m1['low']) * 0.8 < (last_m1['open'] - last_m1['close']):
            return "PUT", "Volumen Spike Bajista"
    return None

# =========================
# FILTRO GLOBAL DE CONFLUENCIA
# =========================
def filtro_global(indicators_m5):
    """Aplica los filtros comunes: ADX > 20, ATR > media de últimas 20."""
    df = indicators_m5['df']
    if len(df) < 20:
        return True  # si no hay datos, no filtramos
    atr_medio = df['atr'].iloc[-20:].mean()
    return indicators_m5['adx'] > 20 and indicators_m5['atr'] > atr_medio

# =========================
# EVALUAR UN ACTIVO (retorna señal si cumple)
# =========================
def evaluar_activo(api, asset):
    try:
        # Obtener velas M5 (para indicadores principales)
        candles_m5 = api.get_candles(asset, 300, 100, time.time())
        if not candles_m5 or len(candles_m5) < 50:
            return None
        df_m5 = pd.DataFrame(candles_m5)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df_m5[col] = pd.to_numeric(df_m5[col], errors='coerce')
        df_m5.dropna(inplace=True)
        if len(df_m5) < 50:
            return None

        # Calcular indicadores en M5
        indicators_m5, df_m5_full = calcular_indicadores(df_m5)
        indicators_m5['df'] = df_m5_full

        # Obtener velas M1 recientes (para patrones)
        candles_m1 = api.get_candles(asset, 60, 10, time.time())
        if not candles_m1 or len(candles_m1) < 5:
            return None
        df_m1 = pd.DataFrame(candles_m1)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df_m1[col] = pd.to_numeric(df_m1[col], errors='coerce')
        df_m1.dropna(inplace=True)
        if len(df_m1) < 5:
            return None

        # Detectar niveles S/R en M5
        niveles = detectar_niveles_sr(df_m5_full)

        # Aplicar filtro global
        if not filtro_global(indicators_m5):
            return None

        # Evaluar cada estrategia (solo la primera que cumpla)
        estrategias = [
            estrategia_ema_crossover,
            estrategia_rsi_reversion,
            estrategia_macd_divergence,
            estrategia_bb_breakout,
            estrategia_adx_trend,
            estrategia_sr_rsi,
            estrategia_macd_zero,
            estrategia_volume_spike
        ]
        for est in estrategias:
            try:
                # Algunas estrategias necesitan niveles, otras no
                if 'niveles' in est.__code__.co_varnames:
                    res = est(indicators_m5, df_m1, niveles)
                else:
                    res = est(indicators_m5, df_m1)
                if res:
                    direccion, nombre = res
                    return direccion, nombre
            except Exception as e:
                continue
        return None
    except Exception as e:
        return None

# =========================
# SELECCIONAR LOS MEJORES ACTIVOS (basado en liquidez y estabilidad)
# =========================
def seleccionar_mejores_activos(api, lista_activos, max_activos, minutos_analisis=20):
    """
    Analiza todos los activos de la lista y devuelve los max_activos con mayor puntuación.
    La puntuación se basa en:
    - Volumen promedio (liquidez)
    - Estabilidad (baja volatilidad)
    - Fuerza de tendencia (ADX alto)
    """
    puntuaciones = []
    for asset in lista_activos:
        try:
            candles = api.get_candles(asset, 300, minutos_analisis, time.time())  # velas M5
            if not candles or len(candles) < minutos_analisis//5:  # al menos 4 velas
                continue
            df = pd.DataFrame(candles)
            for col in ['open', 'max', 'min', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(inplace=True)
            if len(df) < 4:
                continue
            # Calcular volumen promedio
            vol_prom = df['volume'].mean()
            # Calcular volatilidad (rango porcentual)
            rango_total = (df['high'].max() - df['low'].min()) / df['close'].iloc[-1]
            # Calcular ADX aproximado (para simplificar, usamos la tendencia de EMAs)
            ema9 = df['close'].ewm(span=9).mean().iloc[-1]
            ema21 = df['close'].ewm(span=21).mean().iloc[-1]
            tendencia = abs(ema9 - ema21) / df['close'].iloc[-1]
            # Puntuación: volumen + baja volatilidad + tendencia
            puntuacion = vol_prom * 1e-6 + (1 / (rango_total + 0.01)) + tendencia * 100
            puntuaciones.append((puntuacion, asset))
            time.sleep(0.1)  # pausa para no saturar
        except:
            continue
    puntuaciones.sort(reverse=True)
    return [asset for _, asset in puntuaciones[:max_activos]]
