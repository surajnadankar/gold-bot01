import ccxt
import time
import pandas as pd
import threading
import requests
from flask import Flask

# ----------------- 1. TELEGRAM CONFIG -----------------
TELEGRAM_BOT_TOKEN = "8895341894:AAEE-p0_Ylj6RFmqr06nx5xNT7vzyBaBTqI"
TELEGRAM_CHAT_ID = "998154896"

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

# ----------------- 2. WEB SERVER (RENDER KEEP-ALIVE) -----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "XAUUSD Spot Gold Active Trade & Key Level Bot is Running!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

# ----------------- 3. EXCHANGE & SPOT GOLD CONFIG -----------------
# Kraken US सर्वर पर 100% अनुमत है (कोई 451 ब्लॉक नहीं)
exchange = ccxt.kraken({
    'enableRateLimit': True
})
SYMBOL = 'PAXG/USD'     # 1 PAXG = 1 Troy Ounce Spot Gold (XAUUSD)
RR_RATIO = 5.0          # 1:5 Risk-to-Reward
SL_BUFFER = 1.5         # $1.50 Stop Loss buffer

# आपके स्पॉट चार्ट के मुख्य स्तर
KEY_LEVELS = [4264.0, 4280.0, 4300.0, 4305.6, 4311.0, 4325.0, 4338.0, 4344.0]

# ----------------- 4. PERFORMANCE TRACKER -----------------
stats = {
    'total_trades': 0,
    'wins': 0,
    'losses': 0,
    'total_r': 0.0
}

active_trade = None

# ----------------- 5. DATA FUNCTIONS -----------------
def get_candles(timeframe, limit=50):
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Kraken fetch error: {e}", flush=True)
        return None

def get_4h_key_levels():
    df_4h = get_candles('4h', limit=25)
    if df_4h is None or len(df_4h) < 15:
        return None, None
    key_low = df_4h['low'].iloc[-11:-1].min()
    key_high = df_4h['high'].iloc[-11:-1].max()
    return key_low, key_high

# ----------------- 6. MAIN TRADING & TRACKING LOOP -----------------
def run_trading_bot():
    global active_trade, stats
    print("XAU/USD Spot Bot active on Kraken...", flush=True)
    send_telegram_msg("🟡 *GOLD (XAU/USD SPOT) Bot Online!*\n• Data: Live Spot Gold (Kraken)\n• Strategy: 4H/15M Liquidity Sweep (1:5 RR)\n• Live SL/TP Tracker & Key Levels Active.")

    level_states = {}
    buy_sweep_active = False
    buy_sweep_lowest = 0.0
    sell_sweep_active = False
    sell_sweep_highest = 0.0

    while True:
        try:
            df_15m = get_candles('15m', limit=15)
            if df_15m is None or len(df_15m) < 3:
                time.sleep(10)
                continue

            last_closed = df_15m.iloc[-2]
            current_bar = df_15m.iloc[-1]
            current_price = current_bar['close']

            key_low_4h, key_high_4h = get_4h_key_levels()
            if key_low_4h is None:
                time.sleep(10)
                continue

            print(f"[STATUS] XAU/USD Spot: ${current_price:.2f} | Range: [${key_low_4h:.2f} - ${key_high_4h:.2f}]", flush=True)

            # === A. ACTIVE TRADE SL / TP MONITORING ===
            if active_trade is not None:
                side = active_trade['side']
                entry = active_trade['entry']
                sl = active_trade['sl']
                tp = active_trade['tp']

                # BUY TRADE EXIT CHECK
                if side == 'BUY':
                    if current_price >= tp:
                        stats['wins'] += 1
                        stats['total_trades'] += 1
                        stats['total_r'] += RR_RATIO
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        msg = (
                            f"🎯 *[GOLD TAKE PROFIT HIT]* 🏆\n"
                            f"-----------------------------\n"
                            f"📈 *Direction:* BUY (Long)\n"
                            f"💵 *Entry:* ${entry:.2f} | *Exit:* ${current_price:.2f}\n"
                            f"💰 *ROI:* *+{int(RR_RATIO * 100)}% (+{int(RR_RATIO)}R Profit)*\n"
                            f"📊 *Win Rate:* {win_rate:.1f}% ({stats['wins']}W / {stats['losses']}L)\n"
                            f"-----------------------------"
                        )
                        send_telegram_msg(msg)
                        active_trade = None
                    elif current_price <= sl:
                        stats['losses'] += 1
                        stats['total_trades'] += 1
                        stats['total_r'] -= 1.0
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        msg = (
                            f"🛑 *[GOLD STOP LOSS HIT]* ❌\n"
                            f"-----------------------------\n"
                            f"📉 *Direction:* BUY (Long)\n"
                            f"💵 *Entry:* ${entry:.2f} | *Exit:* ${current_price:.2f}\n"
                            f"🔻 *ROI:* *-100% (-1R Loss)*\n"
                            f"📊 *Win Rate:* {win_rate:.1f}% ({stats['wins']}W / {stats['losses']}L)\n"
                            f"-----------------------------"
                        )
                        send_telegram_msg(msg)
                        active_trade = None

                # SELL TRADE EXIT CHECK
                elif side == 'SELL':
                    if current_price <= tp:
                        stats['wins'] += 1
                        stats['total_trades'] += 1
                        stats['total_r'] += RR_RATIO
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        msg = (
                            f"🎯 *[GOLD TAKE PROFIT HIT]* 🏆\n"
                            f"-----------------------------\n"
                            f"📉 *Direction:* SELL (Short)\n"
                            f"💵 *Entry:* ${entry:.2f} | *Exit:* ${current_price:.2f}\n"
                            f"💰 *ROI:* *+{int(RR_RATIO * 100)}% (+{int(RR_RATIO)}R Profit)*\n"
                            f"📊 *Win Rate:* {win_rate:.1f}% ({stats['wins']}W / {stats['losses']}L)\n"
                            f"-----------------------------"
                        )
                        send_telegram_msg(msg)
                        active_trade = None
                    elif current_price >= sl:
                        stats['losses'] += 1
                        stats['total_trades'] += 1
                        stats['total_r'] -= 1.0
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        msg = (
                            f"🛑 *[GOLD STOP LOSS HIT]* ❌\n"
                            f"-----------------------------\n"
                            f"📈 *Direction:* SELL (Short)\n"
                            f"💵 *Entry:* ${entry:.2f} | *Exit:* ${current_price:.2f}\n"
                            f"🔻 *ROI:* *-100% (-1R Loss)*\n"
                            f"📊 *Win Rate:* {win_rate:.1f}% ({stats['wins']}W / {stats['losses']}L)\n"
                            f"-----------------------------"
                        )
                        send_telegram_msg(msg)
                        active_trade = None

            # === B. KEY LEVEL ALERTS ===
            for lvl in KEY_LEVELS:
                prev_rel = level_states.get(lvl)
                current_rel = "ABOVE" if current_price >= lvl else "BELOW"

                if prev_rel is not None and prev_rel != current_rel:
                    if prev_rel == "BELOW" and current_rel == "ABOVE":
                        send_telegram_msg(f"⚡ *[GOLD LEVEL BREAKOUT UP]*\nPrice ने ${lvl:.2f} का रेजिस्टेंस पार कर लिया!\nLive Spot: ${current_price:.2f}")
                    elif prev_rel == "ABOVE" and current_rel == "BELOW":
                        send_telegram_msg(f"⚡ *[GOLD LEVEL BREAKDOWN]*\nPrice ने ${lvl:.2f} का सपोर्ट नीचे तोड़ दिया!\nLive Spot: ${current_price:.2f}")

                # Level Touch (दूरी $0.80 के भीतर होने पर)
                if abs(current_price - lvl) <= 0.8 and level_states.get(f"{lvl}_touched") is not True:
                    send_telegram_msg(f"🔔 *[GOLD KEY LEVEL REACHED]*\nPrice Key Level ${lvl:.2f} के पास पहुँच गया है!\nLive Spot: ${current_price:.2f}")
                    level_states[f"{lvl}_touched"] = True
                elif abs(current_price - lvl) > 2.0:
                    level_states[f"{lvl}_touched"] = False

                level_states[lvl] = current_rel

            # === C. 4H/15M LIQUIDITY SWEEP ENTRY STRATEGY ===
            c_open = last_closed['open']
            c_high = last_closed['high']
            c_low = last_closed['low']
            c_close = last_closed['close']

            if c_low < key_low_4h and not buy_sweep_active:
                buy_sweep_active = True
                buy_sweep_lowest = c_low
                send_telegram_msg(f"⚠️ *GOLD LIQUIDITY SWEEP (LOW)*\n4H Low (${key_low_4h:.2f}) sweep हुआ!\nLowest: ${buy_sweep_lowest:.2f}")

            if buy_sweep_active:
                if c_low < buy_sweep_lowest:
                    buy_sweep_lowest = c_low
                if c_close > c_open:
                    entry = c_close
                    sl = buy_sweep_lowest - SL_BUFFER
                    risk = entry - sl
                    if risk > 0 and active_trade is None:
                        tp = entry + (risk * RR_RATIO)
                        active_trade = {'side': 'BUY', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk}
                        send_telegram_msg(
                            f"🚀 *GOLD BUY ENTRY SIGNAL (1:5 RR)*\n"
                            f"-----------------------------\n"
                            f"📈 *Entry:* ${entry:.2f}\n"
                            f"🛑 *Stop Loss:* ${sl:.2f}\n"
                            f"🎯 *Take Profit:* ${tp:.2f}\n"
                            f"📦 *Risk/Reward:* 1:{int(RR_RATIO)}\n"
                            f"👀 *Tracking:* Live Trade Monitored\n"
                            f"-----------------------------"
                        )
                        buy_sweep_active = False

            if c_high > key_high_4h and not sell_sweep_active:
                sell_sweep_active = True
                sell_sweep_highest = c_high
                send_telegram_msg(f"⚠️ *GOLD LIQUIDITY SWEEP (HIGH)*\n4H High (${key_high_4h:.2f}) sweep हुआ!\nHighest: ${sell_sweep_highest:.2f}")

            if sell_sweep_active:
                if c_high > sell_sweep_highest:
                    sell_sweep_highest = c_high
                if c_close < c_open:
                    entry = c_close
                    sl = sell_sweep_highest + SL_BUFFER
                    risk = sl - entry
                    if risk > 0 and active_trade is None:
                        tp = entry - (risk * RR_RATIO)
                        active_trade = {'side': 'SELL', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk}
                        send_telegram_msg(
                            f"🔻 *GOLD SELL ENTRY SIGNAL (1:5 RR)*\n"
                            f"-----------------------------\n"
                            f"📉 *Entry:* ${entry:.2f}\n"
                            f"🛑 *Stop Loss:* ${sl:.2f}\n"
                            f"🎯 *Take Profit:* ${tp:.2f}\n"
                            f"📦 *Risk/Reward:* 1:{int(RR_RATIO)}\n"
                            f"👀 *Tracking:* Live Trade Monitored\n"
                            f"-----------------------------"
                        )
                        sell_sweep_active = False

            time.sleep(25)

        except Exception as e:
            print(f"Gold loop error: {e}", flush=True)
            time.sleep(15)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()
