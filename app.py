import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_activos_fuertes,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER PRO - 8 ESTRATEGIAS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ... (estilos CSS igual que antes, con el mismo diseño profesional) ...

# Inicializar session_state (igual que antes, incluyendo indice_ronda)
if 'api' not in st.session_state:
    st.session_state.api = None
if 'conectado' not in st.session_state:
    st.session_state.conectado = False
if 'tipo_cuenta' not in st.session_state:
    st.session_state.tipo_cuenta = "PRACTICE"
if 'saldo' not in st.session_state:
    st.session_state.saldo = 0.0
if 'monitoreando' not in st.session_state:
    st.session_state.monitoreando = False
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = {}
if 'log' not in st.session_state:
    st.session_state.log = []
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0

# ... (resto de funciones y lógica igual que antes, con las mismas mejoras de espera y reemplazo) ...

# Dentro de la lógica de monitoreo, al generar señal, añadir los votos:
if res and 'direccion' in res:
    entrada = now + timedelta(seconds=anticipacion)
    entrada_str = entrada.strftime("%H:%M:%S")
    vencimiento_str = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
    st.session_state.señales_activas[asset] = {
        'activa': True,
        'asset': asset,
        'direccion': res['direccion'],
        'descripcion': res['descripcion'],
        'fuerza': res['fuerza'],
        'entrada': entrada_str,
        'vencimiento': vencimiento_str,
        'votos_call': res.get('votos_call', 0),
        'votos_put': res.get('votos_put', 0)
    }
    st.session_state.log.append(f"🚀 SEÑAL: {asset} - {res['direccion']} a las {entrada_str} (Fuerza: {res['fuerza']:.1f}%, votos: {res.get('votos_call',0)}C/{res.get('votos_put',0)}P)")
    st.rerun()
