import streamlit as st
from bot import IQBot
from datetime import datetime, timedelta
import time

st.set_page_config(layout="wide")

st.title("🤖 IQ OPTION AUTO SCANNER PRO")

# ----------------------------
# SESSION STATE
# ----------------------------

if "logs" not in st.session_state:
    st.session_state.logs=[]

if "signals" not in st.session_state:
    st.session_state.signals={}

if "alerts" not in st.session_state:
    st.session_state.alerts=[]

if "index" not in st.session_state:
    st.session_state.index=0

if "assets" not in st.session_state:
    st.session_state.assets=[]


# ----------------------------
# LOG FUNCION
# ----------------------------

def log(msg):

    now=datetime.now().strftime("%H:%M:%S")

    st.session_state.logs.insert(0,f"[{now}] {msg}")


# ----------------------------
# SIDEBAR LOGIN
# ----------------------------

with st.sidebar:

    st.header("Conexión")

    email=st.text_input("Email")

    password=st.text_input("Password",type="password")

    if st.button("Conectar"):

        bot=IQBot(email,password,log)

        if bot.connect():

            st.session_state.bot=bot

            assets=bot.get_assets()

            st.session_state.assets=assets

            log("Bot conectado correctamente")

            log(f"{len(assets)} activos encontrados")

        else:

            st.error("Error de conexión")


# ----------------------------
# BOT ACTIVO
# ----------------------------

if "bot" in st.session_state:

    bot=st.session_state.bot

    saldo=bot.get_balance()

    st.success(f"Saldo: {saldo}")

    assets=st.session_state.assets


    # PROTECCION SI NO HAY ACTIVOS
    if not assets:

        st.warning("⏳ Esperando activos disponibles...")

        log("Esperando lista de activos...
