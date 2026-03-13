import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

logger = logging.getLogger(__name__)
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# INDICADORES COMUNES
# =========================
def calcular_indicadores(df):
    """Calcula EMAs, RSI, ATR, ADX, volumen promedio y retorna el df."""
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    # EMAs
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
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
    # ADX (simplificado, requerido para confiabilidad)
    df['tr'] = tr
    df['plus_dm'] = np.where((high - high.shift()) > (low.shift() - low), np.maximum(high - high.shift(), 0), 0)
    df['minus_dm'] = np.where((low.shift() - low) > (high - high.shift()), np.maximum(low.shift() - low, 0), 0)
    df['atr_period'] = df['tr'].rolling(14).mean()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr_period'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr_period'])
    df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di']))
    df['adx'] = df['dx'].rolling(14).mean()
    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']
    return df

# =========================
# DETECCIÓN DE NIVELES (Soportes/Resistencias)
# =========================
def detectar_niveles_sr(df, num_toques=2):
    """Detecta niveles de soporte/resistencia horizontales basados en toques."""
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    closes = df['close']
    conteo = defaultdict(int)
    # Buscar máximos locales
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
    return niveles[:5]  # los 5 más cercanos

# =========================
# DETECCIÓN DE NIVELES OCULTOS (VOLUME PROFILE SIMPLIFICADO)
# =========================
def detectar_niveles_ocultos(df_1min, ventana=20):
    """
    Detecta niveles ocultos basados en el volumen intradía.
    Busca, para cada vela, el precio donde se negoció más del 35% del volumen total de la vela.
    Esto es una aproximación; en un bot real se usarían datos de tick, que no tenemos.
    Como alternativa, usaremos el punto medio del rango si el volumen es alto.
    """
    if len(df_1min) < ventana:
        return []
    df = df_1min.iloc[-ventana:].copy()
    niveles = []
    for _, row in df.iterrows():
        # Si el volumen de la vela es significativamente alto y el cuerpo es pequeño, podría ser un nivel.
        if row['vol_ratio'] > 1.5 and abs(row['close'] - row['open']) < (row['high'] - row['low']) * 0.2:
            # El precio de equilibrio podría ser el punto medio.
            nivel_oculto = (row['high'] + row['low']) / 2
            niveles.append({'precio': round(nivel_oculto, 5), 'tipo': 'oculto'})
    # Eliminar duplicados cercanos
    niveles_unicos = []
    for nivel in niveles:
        if not any(abs(nivel['precio'] - n['precio']) / nivel['precio'] < 0.001 for n in niveles_unicos):
            niveles_unicos.append(nivel)
    return niveles_unicos

# =========================
# ANÁLISIS DE FUERZA Y GENERACIÓN DE SEÑAL
# =========================
def analizar_fuerza_y_senal(ultima_vela, niveles_sr, niveles_ocultos):
    """
    Evalúa la fuerza de la última vela y genera una señal si corresponde.
    Retorna (direccion, fuerza, nivel_activador, descripción) o (None, 0, None, "")
    """
    precio = ultima_vela['close']
    volumen = ultima_vela['volume']
    vol_ratio = ultima_vela['vol_ratio']
    rango = ultima_vela['high'] - ultima_vela['low']
    cuerpo = abs(ultima_vela['close'] - ultima_vela['open'])
    direccion_vela = 'CALL' if ultima_vela['close'] > ultima_vela['open'] else 'PUT'

    # 1. Ruptura de soporte/resistencia
    for nivel in niveles_sr:
        distancia = abs(precio - nivel['precio']) / precio
        if distancia < 0.001:  # Toca el nivel
            if direccion_vela == 'CALL' and nivel['tipo'] == 'resistencia' and precio > nivel['precio'] and vol_ratio > 1.5:
                fuerza = min(8 + (vol_ratio * 1.5), 10)
                return direccion_vela, fuerza, nivel['precio'], f"Ruptura Resistencia ({nivel['toques']} toques)"
            if direccion_vela == 'PUT' and nivel['tipo'] == 'soporte' and precio < nivel['precio'] and vol_ratio > 1.5:
                fuerza = min(8 + (vol_ratio * 1.5), 10)
                return direccion_vela, fuerza, nivel['precio'], f"Ruptura Soporte ({nivel['toques']} toques)"

    # 2. Reacción en nivel oculto
    for nivel in niveles_ocultos:
        distancia = abs(precio - nivel['precio']) / precio
        if distancia < 0.001:
            # Vela de rechazo (mecha larga)
            mecha_sup = ultima_vela['high'] - max(ultima_vela['open'], ultima_vela['close'])
            mecha_inf = min(ultima_vela['open'], ultima_vela['close']) - ultima_vela['low']
            if mecha_inf > 1.5 * cuerpo and direccion_vela == 'CALL':
                fuerza = 7
                return direccion_vela, fuerza, nivel['precio'], "Rechazo en nivel oculto (demanda)"
            if mecha_sup > 1.5 * cuerpo and direccion_vela == 'PUT':
                fuerza = 7
                return direccion_vela, fuerza, nivel['precio'], "Rechazo en nivel oculto (oferta)"

    # 3. Vela de alta fuerza sin nivel (pura fuerza direccional)
    if cuerpo > rango * 0.7 and vol_ratio > 2.0:
        fuerza = 6 + (vol_ratio * 1.5)
        return direccion_vela, min(fuerza, 10), None, "Vela de alta fuerza direccional"

    return None, 0, None, ""

# =========================
# EVALUAR CONFIABILIDAD DE UN ACTIVO
# =========================
def evaluar_confiabilidad_activo(api, asset):
    """
    Analiza un activo y devuelve una puntuación de confiabilidad.
    Criterios: volumen promedio, respeto de niveles, ADX medio.
    """
    try:
        candles = api.get_candles(asset, 60, 50, time.time())  # 50 velas de 1 min
        if not candles or len(candles) < 30:
            return 0
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 30:
            return 0

        df = calcular_indicadores(df)
        # 1. Liquidez (volumen promedio)
        vol_prom = df['volume'].mean()
        # 2. Respeto de niveles (simulado: cuántos rebotes funcionaron)
        #    Para simplificar, usamos la desviación estándar del precio: a menor desviación, más "respeto"?
        #    O mejor, ver cuántas veces el precio tocó un nivel y rebotó.
        niveles = detectar_niveles_sr(df, num_toques=2)
        #    No tenemos una métrica directa, así que usaremos una combinación de ADX y ATR.
        adx_medio = df['adx'].iloc[-20:].mean()
        atr_medio = df['atr'].iloc[-20:].mean()
        # Puntuación: entre más alto el ADX, más tendencia (bueno para algunas estrategias). Entre más bajo el ATR, más estable.
        puntuacion = (vol_prom * 1e-6) + (adx_medio * 0.5) + (100 / (atr_medio * 1000 + 1))
        return puntuacion
    except Exception as e:
        logger.error(f"Error evaluando confiabilidad de {asset}: {e}")
        return 0

# =========================
# OBTENER ACTIVOS ABIERTOS (AUTOMÁTICO)
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
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return []

# =========================
# SELECCIONAR EL ACTIVO MÁS CONFIABLE
# =========================
def seleccionar_activo_confiable(api, tipo_mercado):
    activos = obtener_activos_abiertos(api, tipo_mercado)
    if not activos:
        return None
    puntuaciones = []
    for asset in activos[:30]:  # Limitamos a 30 para no saturar la API
        try:
            punt = evaluar_confiabilidad_activo(api, asset)
            puntuaciones.append((punt, asset))
            time.sleep(0.2)
        except:
            continue
    if not puntuaciones:
        return None
    puntuaciones.sort(reverse=True)
    return puntuaciones[0][1]  # Retorna el nombre del activo con mayor puntuación
