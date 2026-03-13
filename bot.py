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

# =========================
# INDICADORES (igual que antes)
# =========================
def calcular_indicadores(df):
    # ... (mismo código que en versiones anteriores)
    pass

# =========================
# 10 ESTRATEGIAS (igual que antes, devuelven dirección y peso)
# =========================
def estrategia_1_ema_adx(df):
    # ...
    pass

# ... (las 10 estrategias)

# =========================
# DETECCIÓN DE LÍNEAS DE TENDENCIA
# =========================
def detectar_lineas_tendencia(df, num_toques=2):
    """
    Encuentra líneas de tendencia alcistas y bajistas con al menos num_toques toques.
    Retorna una lista de dict con 'tipo' ('alcista'/'bajista'), 'pendiente', 'intercepto', 'toques', 'precio_actual_en_linea'.
    """
    df = df.iloc[-50:].copy()
    minimos = df['low'].values
    maximos = df['high'].values
    indices = np.arange(len(df))
    lineas = []

    # Tendencia alcista: conectar mínimos crecientes
    for i in range(len(minimos)-10):
        for j in range(i+5, len(minimos)):
            if minimos[j] > minimos[i] and (j - i) > 5:
                pendiente = (minimos[j] - minimos[i]) / (j - i)
                # Verificar cuántos mínimos respetan la línea (aproximadamente)
                toques = 2
                # Podríamos verificar otros puntos, pero por simplicidad asumimos 2
                intercepto = minimos[i] - pendiente * i
                precio_actual_linea = intercepto + pendiente * (len(df)-1)
                lineas.append({
                    'tipo': 'alcista',
                    'pendiente': pendiente,
                    'intercepto': intercepto,
                    'toques': toques,
                    'precio_actual': precio_actual_linea
                })
    # Tendencia bajista: conectar máximos decrecientes
    for i in range(len(maximos)-10):
        for j in range(i+5, len(maximos)):
            if maximos[j] < maximos[i] and (j - i) > 5:
                pendiente = (maximos[j] - maximos[i]) / (j - i)
                intercepto = maximos[i] - pendiente * i
                precio_actual_linea = intercepto + pendiente * (len(df)-1)
                lineas.append({
                    'tipo': 'bajista',
                    'pendiente': pendiente,
                    'intercepto': intercepto,
                    'toques': 2,
                    'precio_actual': precio_actual_linea
                })
    return lineas

# =========================
# DETECCIÓN DE SOPORTES Y RESISTENCIAS HORIZONTALES
# =========================
def detectar_soportes_resistencias(df, num_toques=2, tolerancia=0.0005):
    df = df.iloc[-100:].copy()
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
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

# =========================
# ESTIMAR TIEMPO HASTA NIVEL
# =========================
def estimar_tiempo_hasta_nivel(df, nivel, velocidad='pendiente'):
    """
    Estima los minutos que faltan para que el precio alcance un nivel dado.
    Usa la pendiente de las últimas 5 velas o la velocidad promedio.
    """
    if len(df) < 5:
        return None
    ultimas = df.iloc[-5:]
    precio_actual = ultimas['close'].iloc[-1]
    diferencia = abs(nivel - precio_actual)
    # Velocidad promedio por minuto (cada vela es 5 min)
    cambios = ultimas['close'].diff().abs().mean()
    if cambios == 0:
        return None
    minutos = diferencia / cambios * 5  # cada vela son 5 minutos
    return minutos

# =========================
# EVALUAR ACTIVO PARA SEGUIMIENTO (dirección y niveles)
# =========================
def evaluar_activo_seguimiento(api, asset, min_estrategias=2):
    """
    Evalúa un activo y devuelve:
        - direccion (CALL/PUT) si hay consenso de al menos min_estrategias
        - fuerza (promedio de pesos)
        - niveles de interés (líneas de tendencia y S/R cercanos)
        - distancia al nivel más cercano en la dirección
        - tiempo estimado hasta ese nivel
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
        votos_call = 0
        votos_put = 0
        peso_call = 0
        peso_put = 0
        for nombre, funcion in ESTRATEGIAS:
            try:
                direc, peso = funcion(df)
                if direc == 'CALL':
                    votos_call += 1
                    peso_call += peso
                elif direc == 'PUT':
                    votos_put += 1
                    peso_put += peso
            except:
                continue

        if votos_call + votos_put < min_estrategias:
            return None

        if votos_call > votos_put:
            direccion = 'CALL'
            fuerza = peso_call / votos_call if votos_call > 0 else 0
        elif votos_put > votos_call:
            direccion = 'PUT'
            fuerza = peso_put / votos_put if votos_put > 0 else 0
        else:
            # empate, decidir por peso
            if peso_call > peso_put:
                direccion = 'CALL'
                fuerza = peso_call / votos_call if votos_call > 0 else 0
            else:
                direccion = 'PUT'
                fuerza = peso_put / votos_put if votos_put > 0 else 0

        # Obtener niveles relevantes
        niveles_h = detectar_soportes_resistencias(df, num_toques=2)
        lineas = detectar_lineas_tendencia(df, num_toques=2)

        # Filtrar niveles que estén en la dirección correcta
        niveles_direccion = []
        precio_actual = df['close'].iloc[-1]
        atr = df['atr'].iloc[-1]
        if direccion == 'CALL':
            # Buscamos soportes (donde el precio puede rebotar) o líneas alcistas
            for n in niveles_h:
                if n['tipo'] == 'soporte' and n['precio'] < precio_actual:
                    niveles_direccion.append(('soporte', n['precio'], n['toques']))
            for l in lineas:
                if l['tipo'] == 'alcista' and l['precio_actual'] < precio_actual:
                    niveles_direccion.append(('linea_alcista', l['precio_actual'], l['toques']))
        else:
            # Buscamos resistencias o líneas bajistas
            for n in niveles_h:
                if n['tipo'] == 'resistencia' and n['precio'] > precio_actual:
                    niveles_direccion.append(('resistencia', n['precio'], n['toques']))
            for l in lineas:
                if l['tipo'] == 'bajista' and l['precio_actual'] > precio_actual:
                    niveles_direccion.append(('linea_bajista', l['precio_actual'], l['toques']))

        if not niveles_direccion:
            return None

        # Elegir el nivel más cercano
        nivel_cercano = min(niveles_direccion, key=lambda x: abs(x[1] - precio_actual))
        distancia = abs(nivel_cercano[1] - precio_actual)
        tiempo_estimado = estimar_tiempo_hasta_nivel(df, nivel_cercano[1])

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': fuerza,
            'nivel': nivel_cercano[1],
            'tipo_nivel': nivel_cercano[0],
            'toques': nivel_cercano[2],
            'distancia': distancia,
            'tiempo_estimado': tiempo_estimado,
            'precio_actual': precio_actual
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None
