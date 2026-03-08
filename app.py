import streamlit as st
from bot import escanear_activos
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")

st.title("BOT SEÑALES IQ OPTION")

email = st.text_input("Email")
password = st.text_input("Password", type="password")

if st.button("Conectar"):

    API = IQ_Option(email,password)
    API.connect()

    st.success("Conectado")

    while True:

        signal = escanear_activos(API)

        if signal:

            st.markdown(f"""
            <div style="
            background:#111;
            padding:30px;
            border-radius:20px;
            font-size:24px;
            display:flex;
            justify-content:space-between">

            <div>

            <h2>{signal['activo']}</h2>

            <p>OPERAR</p>
            <h1>{signal['operar']}</h1>

            <p>EXPIRA</p>
            <h2>{signal['expira']}</h2>

            </div>

            <div>

            <h1>{signal['direccion']}</h1>

            <p>PROBABILIDAD</p>
            <h1>{signal['prob']}%</h1>

            </div>

            </div>
            """, unsafe_allow_html=True)
