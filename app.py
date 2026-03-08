import streamlit as st
from bot import IQBot
from datetime import datetime
import pytz
import time

ecuador=pytz.timezone("America/Guayaquil")

st.set_page_config(layout="wide")

st.title("🤖 IQ OPTION AUTO SCANNER PRO")

if "logs" not in st.session_state:
    st.session_state.logs=[]

if "signals" not in st.session_state:
    st.session_state.signals={}

if "assets" not in st.session_state:
    st.session_state.assets=[]

if "index" not in st.session_state:
    st.session_state.index=0

def log(msg):

    now=datetime.now(ecuador).strftime("%H:%M:%S")

    st.session_state.logs.insert(0,f"[{now}] {msg}")

with st.sidebar:

    st.header("Conexión")

    email=st.text_input("Email")

    password=st.text_input("Password",type="password")

    if st.button("Conectar"):

        bot=IQBot(email,password,log)

        if bot.connect():

            st.session_state.bot=bot

            st.session_state.assets=bot.get_assets()

            log("Escáner iniciado")

        else:

            st.error("Error conexión")

if "bot" in st.session_state:

    bot=st.session_state.bot

    assets=st.session_state.assets

    if len(assets)>0:

        asset=assets[st.session_state.index%len(assets)]

        log(f"Analizando {asset}")

        result=bot.analyze(asset)

        if result:

            name=result["asset"]

            if name not in st.session_state.signals:

                st.session_state.signals[name]=result

                log(f"SEÑAL {name} {result['signal']} operar {result['entry'].strftime('%H:%M:%S')}")

        st.session_state.index+=1


signals=list(st.session_state.signals.values())

cols=st.columns(4)

remove=[]

for i,signal in enumerate(signals[:4]):

    entry=signal["entry"]

    expiry=signal["expiry"]

    now=datetime.now(ecuador)

    remaining=(entry-now).total_seconds()

    if remaining<=0:
        remove.append(signal["asset"])
        continue

    minutes=int(remaining//60)
    seconds=int(remaining%60)

    countdown=f"{minutes:02}:{seconds:02}"

    if signal["signal"]=="CALL":
        color="#00ff88"
        bg="#002b22"
    else:
        color="#ff4b4b"
        bg="#2b0000"

    with cols[i]:

        st.markdown(f"""
        <div style="
        background:{bg};
        border-radius:15px;
        padding:25px;
        text-align:center;
        border:3px solid {color};
        ">

        <h2>{signal["asset"]}</h2>

        <h1 style="color:{color}">
        {signal["signal"]}
        </h1>

        <h3>OPERAR A LAS</h3>

        <h2>
        {entry.strftime('%H:%M:%S')}
        </h2>

        <h3>EXPIRA</h3>

        <h2>
        {expiry.strftime('%H:%M:%S')}
        </h2>

        <h2>⏳ {countdown}</h2>

        </div>
        """,unsafe_allow_html=True)


for r in remove:
    del st.session_state.signals[r]

st.subheader("Historial del Scanner")

for l in st.session_state.logs[:30]:
    st.text(l)

time.sleep(1)

st.rerun()
