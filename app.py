import streamlit as st
from bot import IQBot
from datetime import datetime
import time

st.set_page_config(layout="wide")

st.title("🤖 IQ OPTION AUTO SCANNER")

if "logs" not in st.session_state:
    st.session_state.logs=[]

if "signals" not in st.session_state:
    st.session_state.signals={}

if "alerts" not in st.session_state:
    st.session_state.alerts=[]

if "index" not in st.session_state:
    st.session_state.index=0


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

            st.error("Error conexión")


if "bot" in st.session_state:

    bot=st.session_state.bot

    st.success(f"Saldo: {bot.get_balance()}")

    assets=st.session_state.assets

    i=st.session_state.index

    asset=assets[i % len(assets)]

    try:

        result=bot.analyze(asset)

        if result:

            name=result["asset"]

            st.session_state.signals[name]=result

            entry_time=result["entry"].strftime("%H:%M:%S")

            alert=f"ALERTA: OPERAR {name} {result['signal']} A LAS {entry_time}"

            log(alert)

            st.session_state.alerts.append(alert)

    except:
        pass

    st.session_state.index+=1


if st.session_state.alerts:

    last_alert=st.session_state.alerts[-1]

    st.markdown(f"""
    <div style="
    background:#220000;
    color:#ff4444;
    padding:20px;
    font-size:30px;
    text-align:center;
    border-radius:10px;
    ">
    ⚠️ {last_alert} – LISTO PARA ABRIR OPERACIÓN
    </div>
    """,unsafe_allow_html=True)


cols=st.columns(4)

signals=list(st.session_state.signals.values())

for i,signal in enumerate(signals[:4]):

    entry=signal["entry"]

    remaining=(entry-datetime.now()).total_seconds()

    if remaining<=0:

        del st.session_state.signals[signal["asset"]]

        continue

    minutes=int(remaining//60)
    seconds=int(remaining%60)

    countdown=f"{minutes:02}:{seconds:02}"

    if signal["signal"]=="CALL":

        color="#00ff00"
        bg="#002200"

    else:

        color="#ff0000"
        bg="#220000"

    with cols[i]:

        st.markdown(f"""

        <div style="
        background:{bg};
        border:2px solid {color};
        padding:25px;
        border-radius:15px;
        text-align:center;
        ">

        <h2>{signal["asset"]}</h2>

        <h1 style="color:{color}">{signal["signal"]}</h1>

        <h2 style="color:white">OPERAR A LAS</h2>

        <h1 style="color:{color}">{signal["entry"].strftime('%H:%M:%S')}</h1>

        <h2>⏳ {countdown}</h2>

        </div>

        """,unsafe_allow_html=True)


st.subheader("Historial del Bot")

for logmsg in st.session_state.logs[-50:]:

    st.text(logmsg)


time.sleep(1)

st.rerun()
