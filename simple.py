# ================= FINAL ALGO – CE & PE SEPARATE STRATEGY BAR =================

import time, datetime, os, contextlib, threading, random
import pyotp, requests
from SmartApi import SmartConnect
import logging, subprocess, re, tkinter as tk, msvcrt
# ---------------- LOGGING SETUP ----------------

import os, logging, datetime

log_folder = f"logs/{datetime.date.today()}"
os.makedirs(log_folder, exist_ok=True)

log_file = f"{log_folder}/app.log"

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

logging.info("===== PROGRAM STARTED =====")

logging.disable(logging.CRITICAL)

API_KEY="n8YDfDhr"
CLIENT_CODE="B91329"
PASSWORD="7080"
TOTP_SECRET="MN2E75NXCFTASLBRPRR4HGLTSM"

INDEX_EXCHANGE="NSE"
INDEX_SYMBOL="NIFTY"
INDEX_TOKEN="26000"

QTY=75
FIXED_TARGET=25
MAX_CANDLES=5
MAX_TRADES_PER_DAY=4
LTP_SCROLL_LEN=6




# ---------------- EXPIRY ----------------

def read_expiry():
    try:
        with open("expiry.txt") as f:
            x=f.read().strip().upper()
        if len(x)!=7:
            raise
        return x
    except:
        print("expiry.txt error | example 10FEB26")
        exit()

EXPIRY_STR=read_expiry()

# ---------------- TELEGRAM ----------------

TG_BOT_TOKEN="7870835105:AAGPu6Wq9qkyvEvThYDo9OL-PQbSvJ2IQH0"
TG_CHAT_ID="8245258691"

def tg_send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            data={"chat_id":TG_CHAT_ID,"text":msg}
        )
    except:
        pass

# ---------------- INTERNET CHECK ----------------

def get_internet_status_and_latency():
    try:
        lat=[]
        for _ in range(2):
            p=subprocess.run(
                ["ping","-n","1","-w","1000","1.1.1.1"],
                capture_output=True,text=True
            )
            if p.returncode!=0:
                return False,None
            m=re.search(r'time[=<]\s*(\d+)\s*ms',p.stdout.lower())
            if m:
                lat.append(int(m.group(1)))
        if not lat:
            return True,None
        return True,(sum(lat)/len(lat),max(lat)-min(lat))
    except:
        return False,None

def internet_bar(lat_info, width=18):
    green="\033[92m"; reset="\033[0m"

    if lat_info is None:
        base=width//2; quality="OK"
    else:
        avg,_=lat_info
        if avg<=40: base=width-2; quality="FAST"
        elif avg<=80: base=int(width*0.7); quality="GOOD"
        elif avg<=150: base=int(width*0.45); quality="SLOW"
        else: base=int(width*0.25); quality="VERY SLOW"

    move=random.choice([-1,0,1])
    filled=max(1,min(width,base+move))
    bar="█"*filled+"░"*(width-filled)

    return f"{green}{bar}{reset}  {quality}"

def red_disconnect_bar(w=18):
    return f"\033[91m{'█'*w}\033[0m  NO INTERNET"


# ---------------- LOGIN ----------------

def auto_login():
    totp=pyotp.TOTP(TOTP_SECRET).now()
    obj=SmartConnect(api_key=API_KEY)
    d=obj.generateSession(CLIENT_CODE,PASSWORD,totp)
    if d and d.get("status"):
        return obj,d["data"].get("name","UNKNOWN")
    return None,None

# ---------------- UTIL ----------------

def get_ltp(obj,ex,sym,tk):
    try:
        r=obj.ltpData(ex,sym,tk)
        return float(r["data"]["ltp"])
    except:
        return None

def get_funds(obj):
    try:
        d=obj.rmsLimit()["data"]
        return (
            round(float(d.get("availablecash",0)),2),
            round(float(d.get("utiliseddebits",0)),2),
            round(float(d.get("net",0)),2)
        )
    except:
        return (0,0,0)

def get_option(obj,strike,ot):
    try:
        q=f"NIFTY{EXPIRY_STR}{strike}{ot}"
        with open(os.devnull,"w") as f,contextlib.redirect_stdout(f):
            d=obj.searchScrip("NFO",q)
        return d["data"][0]
    except:
        return None

# ---------------- STRATEGY ----------------

def candle_type(o,h,l,c):
    body=abs(c-o)
    wick=(h-l)-body
    if body==0 or wick>=body:
        return "INDECISION"
    return "GREEN STRONG" if c>o else "RED STRONG"

def get_chart_candles(obj,tk,maxc):
    try:
        to=datetime.datetime.now()
        fr=to-datetime.timedelta(days=3)

        params={
            "exchange":"NFO",
            "symboltoken":tk,
            "interval":"FIVE_MINUTE",
            "fromdate":fr.strftime("%Y-%m-%d 09:15"),
            "todate":to.strftime("%Y-%m-%d %H:%M")
        }

        r=obj.getCandleData(params)

        if not r or not r.get("data"):
            return []

        out=[]

        for c in r["data"][-maxc:]:
            ts,o,h,l,cl,v=c

            # SAFE timestamp parsing
            try:
                t=datetime.datetime.strptime(ts,"%Y-%m-%dT%H:%M:%S%z")
            except:
                try:
                    t=datetime.datetime.strptime(ts,"%Y-%m-%d %H:%M:%S")
                except:
                    continue

            out.append({
                "ot":t.strftime("%H:%M"),
                "ct":(t+datetime.timedelta(minutes=5)).strftime("%H:%M"),
                "o":float(o),
                "h":float(h),
                "l":float(l),
                "c":float(cl),
                "type":candle_type(float(o),float(h),float(l),float(cl))
            })

        return out

    except Exception as e:
        return []


def is_strong(c):
    b=abs(c["c"]-c["o"])
    w=(c["h"]-c["l"])-b
    return w<b

def is_indecision(c):
    b=abs(c["c"]-c["o"])
    w=(c["h"]-c["l"])-b
    return w>=b

def strategy_3(x):
    if len(x)<3: return False
    c1,c2,c3=x[-3],x[-2],x[-1]
    if not(c1["c"]<c1["o"] and is_strong(c1)): return False
    if not is_indecision(c2): return False
    if not(c3["c"]>c3["o"] and is_strong(c3) and c3["c"]>c2["h"]): return False
    return True

def strategy_4(x):
    if len(x)<4: return False
    c1,c2,c3,c4=x[-4],x[-3],x[-2],x[-1]
    if not(c1["c"]<c1["o"] and is_strong(c1)): return False
    if not is_indecision(c2): return False
    if not is_indecision(c3): return False
    if not(c4["c"]>c4["o"] and is_strong(c4) and c4["c"]>max(c2["h"],c3["h"])): return False
    return True

def strategy_match(x):
    return strategy_3(x) or strategy_4(x)

# ---------------- DASHBOARD ----------------

def draw_dashboard(login,name,funds,ce_sym,pe_sym,
                   scroll,ce_c,pe_c,
                   ce_st,pe_st,
                   ce_signal_active,pe_signal_active,
                   trade,last_trade_pnl,day_pnl,
                   total,wins,losses,
                   net_ok,net_bar):

    os.system("cls" if os.name=="nt" else "clear")

    print("="*110)
    print(f"LOGIN : {login} | NAME : {name}")
    print(f"FUNDS → AVAILABLE ₹{funds[0]} | USED ₹{funds[1]} | NET ₹{funds[2]}")
    print(f"CE : {ce_sym} | PE : {pe_sym} | EXPIRY : {EXPIRY_STR}")
    print(f"INTERNET : {'CONNECTED ✅' if net_ok else 'DISCONNECTED ❌'}  {net_bar}")
    print("="*110)

    print("TIME     | NIFTY     | ATM   | CE LTP | PE LTP")
    print("-"*110)
    for r in scroll:
        print(f"{r[0]} | {r[1]:9.2f} | {r[2]} | {r[3]:>6} | {r[4]:>6}")
    print("-"*110)

    def show(t,cs):
        print(t)
        print("OT    CT    OPEN   HIGH   LOW    CLOSE  TYPE")
        print("-"*110)
        for c in cs:
            print(f"{c['ot']} {c['ct']} {c['o']:7.2f} {c['h']:7.2f} {c['l']:7.2f} {c['c']:7.2f} {c['type']}")
        print("-"*110)

    show("🕯 CE 5-MIN CANDLES",ce_c)
    show("🕯 PE 5-MIN CANDLES",pe_c)

    green="\033[92m"; red="\033[91m"; reset="\033[0m"
    ce_bar=green+"█"*20+reset if ce_signal_active else red+"█"*20+reset
    pe_bar=green+"█"*20+reset if pe_signal_active else red+"█"*20+reset

    print(f"CE STRATEGY : {ce_st}  {ce_bar}")
    print(" " * 14 + "-" * 22)
    print(f"PE STRATEGY : {pe_st}  {pe_bar}")

    print("-"*110)

    # -------- SIDE BY SIDE BLOCK --------

    left=[
        "📌 VIRTUAL TRADE",
        f"STATUS : {trade['STATUS']}",
        f"SIDE   : {trade['SIDE']}",
        f"ENTRY  : {trade['ENTRY']}",
        f"SL     : {trade['SL']}",
        f"TARGET : {trade['TARGET']}",
        f"LTP    : {trade['LTP']}",
        f"P/L    : {trade['P/L']}"
    ]

    right=[
        "📊 PNL SUMMARY",
        f"CURRENT RUNNING P/L : {trade['P/L']}",
        f"LAST TRADE P/L     : {last_trade_pnl}",
        f"TODAY TOTAL P/L    : {day_pnl}",
        "",
        f"TRADES : {total}/{MAX_TRADES_PER_DAY}",
        f"WINS   : {wins}",
        f"LOSSES : {losses}"
    ]

    w=48
    for i in range(max(len(left),len(right))):
        l=left[i] if i<len(left) else ""
        r=right[i] if i<len(right) else ""
        print(f"{l:<{w}} | {r}")

    print("="*110)
    print("PRESS 'Q' TO EXIT PROGRAM (RUNNING TRADE WILL BE SQUARED OFF)")

# ---------------- MAIN ----------------

def main():

    global disconnect_start_time,popup_seconds

    obj,user=auto_login()
    if not obj:
        print("LOGIN FAILED"); return

    ce_c,pe_c=[],[]
    scroll=[]

    trade={"STATUS":"WAITING","SIDE":"-","ENTRY":0,"SL":0,"TARGET":0,"LTP":0,"P/L":0}

    total=wins=losses=0
    day_pnl=0.0
    last_trade_pnl=0.0

    today=datetime.date.today()
    last_slot=None

    last_ce=None
    last_pe=None

    ce_signal_active=False
    pe_signal_active=False
    force_net_squareoff=False

    while True:

        start=time.time()
        now=datetime.datetime.now()

        if now.date()!=today:
            today=now.date()
            day_pnl=0.0
            last_trade_pnl=0.0
            ce_signal_active=False
            pe_signal_active=False

        net_ok,lat=get_internet_status_and_latency()

        if net_ok:
            logging.info("INTERNET OK")
        else:
            logging.warning("INTERNET DISCONNECTED")
        
        nifty=get_ltp(obj,INDEX_EXCHANGE,INDEX_SYMBOL,INDEX_TOKEN) or 0
        atm=round(nifty/50)*50 if nifty else 0

        ce_ltp=pe_ltp=None
        ce=pe=None

        if atm:
            nce=get_option(obj,atm,"CE")
            npe=get_option(obj,atm,"PE")

            if nce: last_ce=nce
            if npe: last_pe=npe

            ce=last_ce
            pe=last_pe

            if ce: ce_ltp=get_ltp(obj,"NFO","",ce["symboltoken"])
            if pe: pe_ltp=get_ltp(obj,"NFO","",pe["symboltoken"])

        scroll.append((now.strftime("%H:%M:%S"),nifty,atm,
                       round(ce_ltp,2) if ce_ltp else "--",
                       round(pe_ltp,2) if pe_ltp else "--"))
        if len(scroll)>LTP_SCROLL_LEN:
            scroll.pop(0)

        if ce and pe:
            slot=now.replace(minute=(now.minute//5)*5,second=0,microsecond=0)
            if slot!=last_slot:
                x=get_chart_candles(obj,ce["symboltoken"],MAX_CANDLES)
                y=get_chart_candles(obj,pe["symboltoken"],MAX_CANDLES)
                if x: ce_c=x
                if y: pe_c=y
                last_slot=slot

        ce_match=strategy_match(ce_c)
        pe_match=strategy_match(pe_c)
        if ce_match:
            logging.info("CE STRATEGY MATCH")

        if pe_match:
            logging.info("PE STRATEGY MATCH")

        ce_st="MATCH ✅" if ce_match else "NO MATCH ❌"
        pe_st="MATCH ✅" if pe_match else "NO MATCH ❌"

        if ce_match: ce_signal_active=True
        if pe_match: pe_signal_active=True

        if ce and pe and trade["STATUS"]=="WAITING" and total<MAX_TRADES_PER_DAY:

            if ce_match and len(ce_c)>=3:
                e=ce_c[-1]["c"]

                logging.info(f"TRADE ENTER | CE | ENTRY {e}")

                trade={"STATUS":"IN","SIDE":"CE","ENTRY":e,"SL":ce_c[-1]["o"],
                       "TARGET":e+FIXED_TARGET,"LTP":0,"P/L":0}
                tg_send(f"📈 CE BUY @ {e}")

            elif pe_match and len(pe_c)>=3:
                e=pe_c[-1]["c"]
                trade={"STATUS":"IN","SIDE":"PE","ENTRY":e,"SL":pe_c[-1]["o"],
                       "TARGET":e+FIXED_TARGET,"LTP":0,"P/L":0}
                tg_send(f"📉 PE BUY @ {e}")

        if trade["STATUS"]=="IN":

            ltp=ce_ltp if trade["SIDE"]=="CE" else pe_ltp

            if ltp:

                trade["LTP"]=ltp
                trade["P/L"]=round((ltp-trade["ENTRY"])*QTY,2)

                if force_net_squareoff:

                    if trade["SIDE"]=="CE": ce_signal_active=False
                    else: pe_signal_active=False

                    last_trade_pnl=trade["P/L"]
                    day_pnl+=trade["P/L"]

                    total+=1
                    wins+=1 if trade["P/L"]>=0 else 0
                    losses+=1 if trade["P/L"]<0 else 0
              
                    logging.warning(f"AUTO SQUAREOFF | {trade['SIDE']} | P/L {trade['P/L']}")
                    tg_send(f"⚠ AUTO SQUAREOFF (INTERNET DISCONNECTED 30s) | {trade['SIDE']} | P/L {trade['P/L']}")

                    trade={"STATUS":"WAITING","SIDE":"-","ENTRY":0,"SL":0,"TARGET":0,"LTP":0,"P/L":0}
                    force_net_squareoff=False
                    continue

                if ltp>=trade["TARGET"] or ltp<=trade["SL"]:

                    if trade["SIDE"]=="CE": ce_signal_active=False
                    else: pe_signal_active=False

                    last_trade_pnl=trade["P/L"]
                    day_pnl+=trade["P/L"]

                    total+=1
                    wins+=1 if trade["P/L"]>=0 else 0
                    losses+=1 if trade["P/L"]<0 else 0
                    
                    logging.info(f"TRADE EXIT | {trade['SIDE']} | P/L {trade['P/L']}")
                    
                    tg_send(f"❌ EXIT {trade['SIDE']} | P/L {trade['P/L']}")
                    

                    logging.info(f"TRADE EXIT | {trade['SIDE']} | P/L {trade['P/L']}")

                    save_trade_to_csv(
                        trade["SIDE"],
                        trade["ENTRY"],
                        ltp,
                        trade["P/L"]
                    )
                    generate_report()

                    trade={"STATUS":"WAITING","SIDE":"-","ENTRY":0,"SL":0,"TARGET":0,"LTP":0,"P/L":0}

        funds=get_funds(obj)
        net_bar=internet_bar(lat) if net_ok else red_disconnect_bar()

        draw_dashboard(
            CLIENT_CODE,user,funds,
            ce["tradingsymbol"] if ce else "-",
            pe["tradingsymbol"] if pe else "-",
            scroll,ce_c,pe_c,
            ce_st,pe_st,
            ce_signal_active,pe_signal_active,
            trade,last_trade_pnl,day_pnl,
            total,wins,losses,
            net_ok,net_bar
        )

        if msvcrt.kbhit():
            if msvcrt.getwch().lower()=="q":
                print("\nDo you really want to exit the program ? (Y/N) : ",end="")
                a=input().strip().lower()
                if a=="y":

                    if trade["STATUS"]=="IN":

                        ltp=ce_ltp if trade["SIDE"]=="CE" else pe_ltp
                        if ltp:

                            trade["P/L"]=round((ltp-trade["ENTRY"])*QTY,2)

                            if trade["SIDE"]=="CE": ce_signal_active=False
                            else: pe_signal_active=False


                            last_trade_pnl=trade["P/L"]
                            day_pnl+=trade["P/L"]

                            total+=1
                            wins+=1 if trade["P/L"]>=0 else 0
                            losses+=1 if trade["P/L"]<0 else 0

                            tg_send(f"⚠ AUTO EXIT ON PROGRAM CLOSE | {trade['SIDE']} | P/L {trade['P/L']}")

                    generate_report()

                    print("\nProgram closed safely.")
                    time.sleep(1)
                    os._exit(0)

        time.sleep(max(0,1-(time.time()-start)))
def generate_report():

    total = 0
    wins = 0
    losses = 0
    profit = 0.0

    try:
        log_path = "logs/" + str(datetime.date.today()) + "/app.log"

        with open(log_path, "r") as f:
            lines = f.readlines()

        for line in lines:

            if "TRADE EXIT" in line:

                total += 1

                try:
                    pl = float(line.split("P/L")[1].strip())
                except:
                    continue

                profit += pl

                if pl >= 0:
                    wins += 1
                else:
                    losses += 1

        if total > 0:
            win_rate = (wins / total) * 100
        else:
            win_rate = 0

        # -------- CMD OUTPUT --------
        print("\n📊 ===== DAILY REPORT =====")
        print(f"Total Trades : {total}")
        print(f"Wins         : {wins}")
        print(f"Losses       : {losses}")
        print(f"Win Rate     : {round(win_rate,2)} %")
        print(f"Total Profit : ₹{round(profit,2)}")
        print("==========================")

        # -------- LOG FILE OUTPUT --------
        logging.info("===== DAILY REPORT =====")
        logging.info(f"Total Trades : {total}")
        logging.info(f"Wins         : {wins}")
        logging.info(f"Losses       : {losses}")
        logging.info(f"Win Rate     : {round(win_rate,2)} %")
        logging.info(f"Total Profit : ₹{round(profit,2)}")
        logging.info("=========================")
        logging.shutdown()

    except Exception as e:
        logging.error(f"REPORT ERROR: {e}")
def save_trade_to_csv(side, entry, exit_price, pnl):

    import os, csv, datetime

    folder = "reports"
    os.makedirs(folder, exist_ok=True)

    file = folder + "/" + str(datetime.date.today()) + ".csv"

    file_exists = os.path.isfile(file)

    with open(file, "a", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["Time", "Side", "Entry", "Exit", "PnL"])

        writer.writerow([
            datetime.datetime.now().strftime("%H:%M:%S"),
            side,
            entry,
            exit_price,
            pnl
        ])
if __name__=="__main__":
    
    main()
