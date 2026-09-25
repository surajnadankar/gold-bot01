import ccxt
import time
import pandas as pd
import threading
import requests
from flask import Flask

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

app = Flask(__name__)

@app.route('/')
def home():
    return "XAUUSD Spot Gold True Swing Bot is Live!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

exchange = ccxt.kraken({'enableRateLimit': True})
SYMBOL = 'PAXG/USD'
RR_RATIO = 5.0
SL_BUFFER = 1.5

KEY_LEVELS = [4264.0, 4280.0, 4300.0, 4305.6, 4311.0, 4325.0, 4338.0, 4344.0]

stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_r': 0.0}
active_trade = None

def get_candles(timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 5:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Gold fetch error: {e}", flush=True)
        return None

def get_true_swing_levels(df, window=2):
    if df is None or len(df) < (window * 2 + 5):
        return None, None
    
    swing_highs = []
    swing_lows = []
    
    for i in range(window, len(df) - 1):
        is_high = True
        for k in range(1, window + 1):
            if df['high'].iloc[i] <= df['high'].iloc[i - k] or df['high'].iloc[i] <= df['high'].iloc[i + k]:
                is_high = False
                break
        if is_high:
            swing_highs.append(df['high'].iloc[i])

        is_low = True
        for k in range(1, window + 1):
            if df['low'].iloc[i] >= df['low'].iloc[i - k] or df['low'].iloc[i] >= df['low'].iloc[i + k]:
                is_low = False
                break
        if is_low:
            swing_lows.append(df['low'].iloc[i])

    major_swing_high = swing_highs[-1] if swing_highs else df['high'].max()
    major_swing_low = swing_lows[-1] if swing_lows else df['low'].min()

    return major_swing_low, major_swing_high

def run_trading_bot():
    global active_trade, stats
    print("Gold True Swing Bot running...", flush=True)
    send_telegram_msg("🟡 *GOLD (XAU/USD SPOT) Bot Online*\n• Live Tracking Active.")

    level_states = {}
    buy_sweep_active = False
    buy_sweep_lowest = 0.0
    sell_sweep_active = False
    sell_sweep_highest = 0.0

    while True:
        try:
            df_4h = get_candles('4h', limit=60)
            df_15m = get_candles('15m', limit=20)
            
            if df_4h is None or df_15m is None or len(df_15m) < 3:
                time.sleep(10)
                continue

            swing_low_4h, swing_high_4h = get_true_swing_levels(df_4h, window=2)
            if swing_low_4h is None or swing_high_4h is None:
                time.sleep(10)
                continue

            last_closed = df_15m.iloc[-2]
            current_price = df_15m['close'].iloc[-1]

            print(f"[STATUS] XAU/USD Spot: ${current_price:.2f} | Swings: [${swing_low_4h:.2f} - ${swing_high_4h:.2f}]", flush=True)

            # A. ACTIVE TRADE SL/TP
            if active_trade is not None:
                side = active_trade['side']
                entry = active_trade['entry']
                sl = active_trade['sl']
                tp = active_trade['tp']

                if side == 'BUY':
                    if current_price >= tp:
                        stats['wins'] += 1
                        stats['total_trades'] += 1
                        send_telegram_msg(f"🎯 *[GOLD TP HIT]* BUY\nEntry: ${entry:.2f} | Exit: ${current_price:.2f} | +{int(RR_RATIO*100)}%")
                        active_trade = None
                    elif current_price <= sl:
                        stats['losses'] += 1
                        stats['total_trades'] += 1
                        send_telegram_msg(f"🛑 *[GOLD SL HIT]* BUY\nEntry: ${entry:.2f} | Exit: ${current_price:.2f} | -100%")
                        active_trade = None

                elif side == 'SELL':
                    if current_price <= tp:
                        stats['wins'] += 1
                        stats['total_trades'] += 1
                        send_telegram_msg(f"🎯 *[GOLD TP HIT]* SELL\nEntry: ${entry:.2f} | Exit: ${current_price:.2f} | +{int(RR_RATIO*100)}%")
                        active_trade = None
                    elif current_price >= sl:
                        stats['losses'] += 1
                        stats['total_trades'] += 1
                        send_telegram_msg(f"🛑 *[GOLD SL HIT]* SELL\nEntry: ${entry:.2f} | Exit: ${current_price:.2f} | -100%")
                        active_trade = None

            # B. KEY LEVELS
            for lvl in KEY_LEVELS:
                prev_rel = level_states.get(lvl)
                current_rel = "ABOVE" if current_price >= lvl else "BELOW"
                if prev_rel is not None and prev_rel != current_rel:
                    if prev_rel == "BELOW" and current_rel == "ABOVE":
                        send_telegram_msg(f"⚡ *[GOLD BREAKOUT]* Price ने ${lvl:.2f} पार किया!")
                    elif prev_rel == "ABOVE" and current_rel == "BELOW":
                        send_telegram_msg(f"⚡ *[GOLD BREAKDOWN]* Price ने ${lvl:.2f} तोड़ा!")
                if abs(current_price - lvl) <= 0.8 and not level_states.get(f"{lvl}_touched"):
                    send_telegram_msg(f"🔔 *[GOLD KEY LEVEL REACHED]* ${lvl:.2f}")
                    level_states[f"{lvl}_touched"] = True
                elif abs(current_price - lvl) > 2.0:
                    level_states[f"{lvl}_touched"] = False
                level_states[lvl] = current_rel

            # C. SWEEP LOGIC
            c_open = last_closed['open']
            c_low = last_closed['low']
            c_high = last_closed['high']
            c_close = last_closed['close']

            if c_low < swing_low_4h and not buy_sweep_active:
                buy_sweep_active = True
                buy_sweep_lowest = c_low
                send_telegram_msg(f"⚠️ *GOLD SWING SWEEP (LOW)*\n4H Low (${swing_low_4h:.2f}) sweep!")

            if buy_sweep_active:
                if c_low < buy_sweep_lowest:
                    buy_sweep_lowest = c_low
                if c_close > c_open:
                    entry = c_close
                    sl = buy_sweep_lowest - SL_BUFFER
                    risk = entry - sl
                    if risk > 0 and active_trade is None:
                        tp = entry + (risk * RR_RATIO)
                        active_trade = {'side': 'BUY', 'entry': entry, 'sl': sl, 'tp': tp}
                        send_telegram_msg(f"🚀 *GOLD BUY ENTRY (1:5 RR)*\nEntry: ${entry:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")
                        buy_sweep_active = False

            if c_high > swing_high_4h and not sell_sweep_active:
                sell_sweep_active = True
                sell_sweep_highest = c_high
                send_telegram_msg(f"⚠️ *GOLD SWING SWEEP (HIGH)*\n4H High (${swing_high_4h:.2f}) sweep!")

            if sell_sweep_active:
                if c_high > sell_sweep_highest:
                    sell_sweep_highest = c_high
                if c_close < c_open:
                    entry = c_close
                    sl = sell_sweep_highest + SL_BUFFER
                    risk = sl - entry
                    if risk > 0 and active_trade is None:
                        tp = entry - (risk * RR_RATIO)
                        active_trade = {'side': 'SELL', 'entry': entry, 'sl': sl, 'tp': tp}
                        send_telegram_msg(f"🔻 *GOLD SELL ENTRY (1:5 RR)*\nEntry: ${entry:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")
                        sell_sweep_active = False

            time.sleep(25)
        except Exception as e:
            print(f"Gold error: {e}", flush=True)
            time.sleep(10)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()
                        
