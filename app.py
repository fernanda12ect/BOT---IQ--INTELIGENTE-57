import streamlit as st
from bot import IQBot
from datetime import datetime, timedelta
import time

st.set_page_config(layout="wide")

st.title("🤖 IQ OPTION AUTO SCANNER PRO")

# -------------------
# SESSION
# -------------------

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


# -------------------
# LOG
# -------------------

def log(msg):

    now=datetime.now().strftime("%H:%M:%S")

    st.session_state.logs.insert(0,f"[{now}] {msg}")


# -------------------
# LOGIN
# -------------------

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

            st.error("Error conexión")


# -------------------
# BOT
# -------------------

if "bot" in st.session_state:

    bot=st.session_state.bot

    st.success(f"Saldo: {bot.get_balance()}")

    assets=st.session_state.assets


    if not assets:

        st.warning("⏳ Esperando activos disponibles...")

        log("Esperando activos...")

        time.sleep(3)

        st.rerun()


    i=st.session_state.index

    asset=assets[i % len(assets)]


    try:

        result=bot.analyze(asset)

        if result:

            name=result["asset"]

            if name not in st.session_state.signals:

                entry=result["entry"]

                expiry=entry+timedelta(minutes=5)

                st.session_state.signals[name]={

                    "asset":name,
                    "signal":result["signal"],
                    "entry":entry,
                    "expiry":expiry,
                    "detected":result["detected"]

                }

                alert=f"ALERTA: OPERAR {name} {result['signal']} A LAS {entry.strftime('%H:%M:%S')}"

                st.session_state.alerts.append(alert)

                log(alert)

    except:
        pass


    st.session_state.index+=1


# -------------------
# ALERTA GRANDE
# -------------------

if st.session_state.alerts:

    last=st.session_state.alerts[-1]

    st.markdown(f"""
    <div style="
    background:#300000;
    color:#ff4444;
    padding:25px;
    font-size:32px;
    text-align:center;
    border-radius:10px;
    ">
    ⚠️ {last}
    </div>
    """,unsafe_allow_html=True)


# -------------------
# TARJETAS
# -------------------

cols=st.columns(4)

remove_list=[]

signals=list(st.session_state.signals.values())

for i,signal in enumerate(signals[:4]):

    entry=signal["entry"]

    remaining=(entry-datetime.now()).total_seconds()

    if remaining<=0:

        remove_list.append(signal["asset"])

        continue


    minutes=int(remaining//60)

    seconds=int(remaining%60)

    countdown=f"{minutes:02}:{seconds:02}"


    if signal["signal"]=="CALL":

        color="#00ff00"
        bg="#002200"

    else:

        color="#ff4444"
        bg="#220000"


    with cols[i]:

        st.markdown(f"""

        <div style="
        background:{bg};
        border:3px solid {color};
        padding:30px;
        border-radius:15px;
        text-align:center;
        ">

        <h2>{signal["asset"]}</h2>

        <h1 style="color:{color}">{signal["signal"]}</h1>

        <h2>OPERAR A LAS</h2>

        <h1 style="color:{color}">
        {signal["entry"].strftime('%H:%M:%S')}
        </h1>

        <h3>⏳ {countdown}</h3>

        <p>Detectado: {signal["detected"].strftime('%H:%M:%S')}</p>

        <p>Cierre: {signal["expiry"].strftime('%H:%M:%S')}</p>

        </div>

        """,unsafe_allow_html=True)


for r in remove_list:

    del st.session_state.signals[r]


# -------------------
# HISTORIAL
# -------------------

st.subheader("Historial")

for logmsg in st.session_state.logs[:50]:

    st.text(logmsg)


time.sleep(1)

st.rerun()
