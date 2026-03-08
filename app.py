import streamlit as st
from bot import IQBot
import time
from datetime import datetime


st.set_page_config(layout="wide")

st.title("🤖 IQ OPTION AUTO BOT")


if "logs" not in st.session_state:
    st.session_state.logs=[]

if "signals" not in st.session_state:
    st.session_state.signals=[]


def log(msg):

    now=datetime.now().strftime("%H:%M:%S")

    st.session_state.logs.append(f"[{now}] {msg}")


with st.sidebar:

    st.header("Conexión")

    email=st.text_input("Email")

    password=st.text_input("Password",type="password")

    if st.button("Conectar"):

        bot=IQBot(email,password,log)

        if bot.connect():

            st.session_state.bot=bot

            st.session_state.assets=bot.get_assets()

        else:

            st.error("No se pudo conectar")


if "bot" in st.session_state:

    bot=st.session_state.bot

    st.success(f"Saldo: {bot.get_balance()}")

    assets=st.session_state.assets

    for asset in assets[:10]:

        signal=bot.analyze(asset)

        if signal:

            st.session_state.signals.append((asset,signal))


cols=st.columns(4)

for i,signal in enumerate(st.session_state.signals[:4]):

    asset,action=signal

    if action=="CALL":

        color="#00ff00"

    else:

        color="#ff0000"

    with cols[i]:

        st.markdown(f"""
        <div style="background:#111;padding:20px;border-radius:10px;border:2px solid {color}">
        <h2 style="color:white">{asset}</h2>
        <h1 style="color:{color}">{action}</h1>
        </div>
        """,unsafe_allow_html=True)


st.subheader("Historial")

for logmsg in st.session_state.logs[-20:]:

    st.text(logmsg)


time.sleep(2)

st.rerun()
