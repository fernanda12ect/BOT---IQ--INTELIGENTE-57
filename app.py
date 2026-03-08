import streamlit as st
from bot import IQBot
import time

st.set_page_config(page_title="IQ BOT PRO",layout="wide")

st.title("🤖 IQ OPTION BOT PRO")

if "bot" not in st.session_state:
    st.session_state.bot=None


with st.sidebar:

    st.header("🔐 Conexión")

    email=st.text_input("Correo")

    password=st.text_input("Contraseña",type="password")

    market=st.selectbox("Mercado",["REAL","OTC"])

    if st.button("Conectar"):

        bot=IQBot(email,password)

        if bot.connect():

            st.success("Conectado")

            st.session_state.bot=bot

        else:

            st.error("Error conectando")


if st.session_state.bot:

    bot=st.session_state.bot

    st.success(f"Saldo: {bot.get_balance()}")

    col1,col2=st.columns(2)

    with col1:

        if st.button("Escanear mercado"):

            st.write("🔎 Escaneando activos...")

            signals=bot.scan_market()

            activos=signals[:4]

            st.session_state.activos=activos


    if "activos" in st.session_state:

        st.subheader("📊 Activos detectados")

        cols=st.columns(4)

        for i,(asset,signal) in enumerate(st.session_state.activos):

            with cols[i]:

                if signal=="CALL":

                    st.success(f"{asset}\n\n📈 CALL")

                else:

                    st.error(f"{asset}\n\n📉 PUT")


    st.subheader("📜 Historial")

    log=st.empty()

    while False:

        log.write("Bot monitoreando mercado...")
        time.sleep(5)
