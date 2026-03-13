import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import pytz

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zona horaria
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# CÁLCULO DE INDICADORES BÁSICOS (volumen promedio, etc.)
# =========================
def calcular_indicadores(df):
    df = df.copy()
    # Volumen promedio (20 períodos)
    df['vol_avg'] = df['volume'].rolling(20).mean()
    return df

# =========================
# DETECCIÓN DE NIVELES OCULTOS (puntos de alto volumen dentro de la vela)
# =========================
def detectar_niveles_ocultos(df, ventana=50, umbral_volumen=0.35):
    """
    Simula niveles ocultos buscando puntos donde el volumen intradía es alto.
    Como no tenemos ticks, aproximamos con el volumen total de la vela y su rango.
    """
    niveles = []
    for i in range(1, len(df)-1):
        vela = df.iloc[i]
        # Asumimos que el volumen se concentra en el 60% central del rango
        rango = vela['high'] - vela['low']
        if rango == 0:
            continue
        # Simulamos un nivel en el punto medio ponderado por volumen
        nivel = vela['low'] + rango * 0.5  # podría ser más sofisticado
        if vela['volume'] > vela['vol_avg'] * umbral_volumen:
            niveles.append(nivel)
    # Agrupar niveles cercanos (tolerancia 0.1%)
    niveles_agrupados = []
    for n in sorted(niveles):
        if not niveles_agrupados or abs(n - niveles_agrupados[-1]) / n > 0.001:
            niveles_agrupados.append(n)
    return niveles_agrupados[-10:]  # últimos 10

# =========================
# DETECCIÓN DE SOPORTES/RESISTENCIAS (niveles que han detenido el precio varias veces)
# =========================
def detectar_soportes_resistencias(df, num_toques=3):
    """
    Detecta máximos y mínimos locales que se repiten.
    """
    if len(df) < 20:
        return [], []
    highs = df['high']
    lows = df['low']
    soportes = []
    resistencias = []
    for i in range(2, len(df)-2):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
           highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
            resistencias.append(highs.iloc[i])
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
           lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
            soportes.append(lows.iloc[i])
    # Filtrar por repeticiones (simplificado: agrupar cercanos)
    def agrupar(lista):
        if not lista:
            return []
        lista.sort()
        agrup = [lista[0]]
        for v in lista[1:]:
            if abs(v - agrup[-1]) / v > 0.001:
                agrup.append(v)
        return agrup
    soportes = agrupar(soportes)
    resistencias = agrupar(resistencias)
    return soportes[-5:], resistencias[-5:]  # últimos 5 de cada

# =========================
# DETECCIÓN DE ZONAS DE BALANCE (velas doji o con delta bajo)
# =========================
def es_zona_balance(vela, umbral_delta=10):
    """
    Vela de balance si es doji (cuerpo pequeño) y delta de volumen estimado bajo.
    """
    cuerpo = abs(vela['close'] - vela['open'])
    rango = vela['high'] - vela['low']
    if rango == 0:
        return False
    # Estimación simple de delta: si cierre > apertura, asumimos más compras, etc.
    delta_estimado = (vela['close'] - vela['open']) / rango * 100  # porcentaje
    return cuerpo < rango * 0.2 and abs(delta_estimado) < umbral_delta

# =========================
# CÁLCULO DE FUERZA DE LA VELA
# =========================
def calcular_fuerza(vela):
    """
    Retorna un valor entre 0 y 10 basado en el tamaño del cuerpo y el volumen.
    """
    cuerpo = abs(vela['close'] - vela['open'])
    rango = vela['high'] - vela['low']
    if rango == 0:
        return 0
    tamano = cuerpo / rango
    # Peso del volumen (asumimos que volumen alto da más fuerza)
    vol_factor = min(vela['vol_ratio'] if 'vol_ratio' in vela else 1, 3) / 3
    fuerza = tamano * 10 * vol_factor
    return min(fuerza, 10)

# =========================
# EVALUAR UN ACTIVO (para selección inicial)
# =========================
def evaluar_confiabilidad(api, asset, num_velas=100):
    """
    Evalúa cuán confiable es un activo basado en la cantidad de niveles que respeta.
    """
    try:
        candles = api.get_candles(asset, 60, num_velas, time.time())
        if not candles or len(candles) < 50:
            return 0
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return 0
        df = calcular_indicadores(df)
        soportes, resistencias = detectar_soportes_resistencias(df, num_toques=2)
        # Puntaje: número de niveles detectados (más niveles = más estructura)
        return len(soportes) + len(resistencias)
    except:
        return 0

# =========================
# SELECCIONAR EL ACTIVO MÁS CONFIABLE DE UNA LISTA
# =========================
def seleccionar_activo_confiable(api, lista_activos):
    puntajes = []
    for asset in lista_activos:
        punt = evaluar_confiabilidad(api, asset)
        puntajes.append((punt, asset))
        time.sleep(0.2)
    if not puntajes:
        return None
    puntajes.sort(reverse=True)
    return puntajes[0][1]

# =========================
# ANÁLISIS COMPLETO POR VELA (para el activo seleccionado)
# =========================
def analizar_vela(api, asset):
    """
    Obtiene las últimas 50 velas de 1 minuto y analiza la última vela cerrada.
    Retorna un dict con:
        - vela_actual: la última vela
        - niveles_ocultos: lista de precios
        - soportes: lista
        - resistencias: lista
        - es_zona_balance: bool
        - fuerza: float 0-10
        - direccion_senal: 'CALL'/'PUT' o None (si hay señal)
        - nivel_ruptura: el nivel que se rompió (si aplica)
        - volumen_delta: estimado
    """
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None

        df = calcular_indicadores(df)
        vela_actual = df.iloc[-1]
        vela_anterior = df.iloc[-2] if len(df) > 1 else vela_actual

        # Detectar niveles
        ocultos = detectar_niveles_ocultos(df, ventana=50)
        soportes, resistencias = detectar_soportes_resistencias(df, num_toques=3)

        # Zona de balance?
        balance = es_zona_balance(vela_actual)

        # Fuerza de la vela actual
        fuerza = calcular_fuerza(vela_actual)

        # Delta de volumen estimado
        if vela_actual['close'] > vela_actual['open']:
            delta = vela_actual['volume'] * 0.6  # 60% compras, 40% ventas (simplificado)
        else:
            delta = -vela_actual['volume'] * 0.6

        # Señal: si el precio rompe un nivel relevante con volumen alto
        senal = None
        direccion_senal = None
        nivel_ruptura = None
        umbral_vol_ruptura = 2.0  # volumen > 2x promedio
        if vela_actual['vol_ratio'] > umbral_vol_ruptura:
            # Verificar si se rompió algún nivel
            precio = vela_actual['close']
            for r in resistencias:
                if precio > r and vela_anterior['close'] <= r:
                    # Ruptura de resistencia
                    senal = 'CALL'
                    direccion_senal = 'alcista'
                    nivel_ruptura = r
                    break
            for s in soportes:
                if precio < s and vela_anterior['close'] >= s:
                    senal = 'PUT'
                    direccion_senal = 'bajista'
                    nivel_ruptura = s
                    break

        return {
            'asset': asset,
            'vela_actual': vela_actual.to_dict(),
            'niveles_ocultos': ocultos,
            'soportes': soportes,
            'resistencias': resistencias,
            'es_zona_balance': balance,
            'fuerza': fuerza,
            'delta_volumen': delta,
            'senal': senal,
            'direccion_senal': direccion_senal,
            'nivel_ruptura': nivel_ruptura,
            'timestamp': datetime.now(ecuador)
        }
    except Exception as e:
        logger.error(f"Error analizando {asset}: {e}")
        return None
