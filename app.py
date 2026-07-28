import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. 網頁核心外觀配置 ---
st.set_page_config(page_title="美股雷達 V06.3", page_icon="🔮", layout="wide")
st.title("🔮 美股量化沙盒 V06.3 (法人級多因子雙向感知與四分頁戰術矩陣版)")
st.markdown("已實裝 **V06.3 四維獨立介面與七維戰術矩陣**：**動作分類看板**、**七維戰術共振矩陣**、**歷史驗證線圖** 與 **多線程平行加速引擎**")

# --- 2. 側邊欄控制台 ---
st.sidebar.header("⚙️ 全自動大掃描設定")

GSHEET_URL = "https://docs.google.com/spreadsheets/d/1491qc1Y59PwCOWaPZblpAieR0_iCI-7KKLtZUuG7Qe4/edit?usp=sharing"

GOOGLE_FORM_ID = "1FAIpQLSdpLHywd-HysLTMbGpuEByQwEaoVaqtvTW0Uwav136m-kIDfQ"
ENTRY_TICKER_ID = "entry.2146824153"
ENTRY_NAME_ID = "entry.1673006020"

@st.cache_data(ttl=60)
def get_tickers_from_sheet(url):
    try:
        if "docs.google.com" not in url:
            return "NVDA, AAPL, TSLA, MSFT, AMD", {}
        csv_url = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(csv_url, header=None)
        
        tickers = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        
        custom_names_dict = {}
        if df.shape[1] > 1:
            raw_names = df.iloc[:, 1].fillna("").astype(str).str.strip().tolist()
            for i, t in enumerate(tickers):
                if i < len(raw_names):
                    name_val = str(raw_names[i]).strip()
                    if name_val and name_val.lower() not in ["nan", "none", ""]:
                        custom_names_dict[t] = name_val
                        
        valid_tickers = [t for t in tickers if not any(c >= '\u4e00' and c <= '\u9fff' for c in t) and len(t) > 0 and t != "股票代號"]
        ticker_str = ", ".join(valid_tickers) if valid_tickers else "NVDA, AAPL, TSLA, MSFT, AMD"
        return ticker_str, custom_names_dict
    except Exception:
        return "NVDA, AAPL, TSLA, MSFT, AMD", {}

default_tickers, cloud_names_dict = get_tickers_from_sheet(GSHEET_URL)
tickers_input = st.sidebar.text_area("📡 當前雲端同步清單", default_tickers, height=100)

temp_raw_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
ticker_list = list(dict.fromkeys(temp_raw_list))

backtest_days = st.sidebar.slider("歷史回測天數設定", min_value=100, max_value=500, value=300, step=50)

enable_fcf_filter = st.sidebar.checkbox("🛡️ 啟用「自由現金流 > 0」安全過濾", value=True)
enable_earnings_shield = st.sidebar.checkbox("💣 啟用「3 天內發布財報」強制避險", value=True)

US_SECTOR_DICT = {
    "NVDA": "🤖 AI半導體", "AMD": "🤖 AI半導體", "TSM": "🤖 AI晶片代工", "AVGO": "🤖 AI網通/半導體",
    "AAPL": "📱 消費電子/科技巨頭", "MSFT": "☁️ 雲端/AI軟體巨頭", "GOOGL": "🌐 搜尋/AI巨頭", "GOOG": "🌐 搜尋/AI巨頭",
    "AMZN": "🛒 電商/AWS雲端巨頭", "META": "💬 社群/AI巨頭", "TSLA": "⚡ 電動車/AI機器人", "PLTR": "🔮 AI數據分析",
    "SMCI": "🖥️ AI伺服器", "ARM": "📐 IP矽智財", "QCOM": "📱 通訊晶片", "INTC": "💻 傳統晶片製造",
    "MU": "💾 記憶體半導體", "ASML": "🔬 半導體設備", "LRCX": "🔬 半導體設備", "AMAT": "🔬 半導體設備",
    "JPM": "🏦 金融巨頭/銀行", "BAC": "🏦 金融巨頭/銀行", "GS": "🏦 投資銀行/金融", "V": "💳 數位支付/金融", "MA": "💳 數位支付/金融",
    "LLY": "💊 生物製藥/減肥藥", "PFE": "💊 生物製藥", "JNJ": "💊 醫療保健巨頭", "MRK": "💊 生物製藥", "UNH": "🏥 醫療保險",
    "XOM": "🛢️ 石油/傳統能源", "CVX": "🛢️ 石油/傳統能源", "COST": "🛒 連鎖零售量販", "WMT": "🛒 零售超市巨頭",
    "NKE": "👟 運動消費品牌", "DIS": "🏰 娛樂媒體巨頭", "NFLX": "🎬 串流影音巨頭", "COIN": "🪙 區塊鏈/加密貨幣"
}

YF_SECTOR_MAP = {
    "Technology": "💻 資訊科技",
    "Financial Services": "🏦 金融服務",
    "Healthcare": "💊 醫療保健",
    "Consumer Cyclical": "🛍️ 週期消費",
    "Communication Services": "📡 通訊服務",
    "Industrials": "🏗️ 工業製造",
    "Energy": "🛢️ 能源石油",
    "Consumer Defensive": "🛒 日用消費",
    "Utilities": "⚡ 公用事業",
    "Real Estate": "🏢 房地產",
    "Basic Materials": "⛏️ 基礎材料"
}

# --- 3. 🌐 V06.3 大環境與總經雷達 (VIX & 大盤) ---
@st.cache_data(ttl=1800)
def fetch_macro_environment():
    try:
        vix_df = yf.download("^VIX", period="5d", progress=False)
        vix_clean = vix_df.dropna(subset=['Close'])
        vix_val = float(vix_clean['Close'].iloc[-1]) if not vix_clean.empty else 18.0
        
        spy_df = yf.download("SPY", period="1y", progress=False)
        spy_clean = spy_df.dropna(subset=['Close'])
        if not spy_clean.empty:
            spy_close = float(spy_clean['Close'].iloc[-1])
            spy_ma200 = float(spy_clean['Close'].rolling(200).mean().iloc[-1])
            spy_bull = spy_close >= spy_ma200
        else:
            spy_bull = True
            
        if vix_val >= 25 or not spy_bull:
            posture_auto = "🥶 極度謹慎型 (大盤空頭/高恐慌)"
        elif vix_val <= 15 and spy_bull:
            posture_auto = "🚀 大膽進攻型 (晴天多頭行情)"
        else:
            posture_auto = "🛡️ 標準平衡型 (常態橫盤整理)"
            
        return vix_val, spy_bull, posture_auto
    except Exception:
        return 18.0, True, "🛡️ 標準平衡型 (預設)"

vix_score, is_spy_bull, market_posture = fetch_macro_environment()

# --- 4. 🏢 V06.3 基本面、產業領域與新聞雷達 ---
@st.cache_data(ttl=3600)
def fetch_fundamental_and_news(ticker, cloud_dict):
    cloud_note = cloud_dict.get(ticker, "")
    
    f_info = {
        "sector_tag": "🇺🇸 美股企業",
        "pe": "-", "fcf": "-", "rev_growth": "-", 
        "is_fcf_positive": True, "near_earnings": False, 
        "news_alert": "🟢 無異常", "quality_tag": "一般"
    }
    
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        
        if cloud_note and cloud_note.lower() not in ["nan", "none", ""]:
            f_info["sector_tag"] = cloud_note
        elif ticker in US_SECTOR_DICT:
            f_info["sector_tag"] = US_SECTOR_DICT[ticker]
        else:
            raw_sector = info.get("sector", "")
            f_info["sector_tag"] = YF_SECTOR_MAP.get(raw_sector, f"🇺🇸 {raw_sector}" if raw_sector else "🇺🇸 美股企業")

        pe = info.get("trailingPE", None)
        fcf = info.get("freeCashflow", None)
        rev_g = info.get("revenueGrowth", None)
        
        if pe is not None: f_info["pe"] = f"{pe:.1f}倍"
        if fcf is not None:
            f_info["fcf"] = f"${fcf / 1e8:.1f}億"
            if fcf < 0: f_info["is_fcf_positive"] = False
        if rev_g is not None: f_info["rev_growth"] = f"{rev_g * 100:+.1f}%"
        
        if (fcf is not None and fcf > 0) and (rev_g is not None and rev_g > 0.15):
            f_info["quality_tag"] = "🔥 財報雙強"
            
        calendar = tk.calendar
        if calendar is not None and "Earnings Date" in calendar:
            e_dates = calendar["Earnings Date"]
            if len(e_dates) > 0:
                next_e = pd.to_datetime(e_dates[0])
                today = pd.to_datetime(datetime.now().date())
                days_diff = (next_e - today).days
                if 0 <= days_diff <= 3:
                    f_info["near_earnings"] = True
                    
        news_list = tk.news or []
        bad_keywords = ["LAWSUIT", "PROBE", "DOWNGRADE", "MISSED", "INVESTIGATION", "FRAUD", "BANKRUPT"]
        bad_count = 0
        for n in news_list[:5]:
            title = n.get("title", "").upper()
            if any(kw in title for kw in bad_keywords):
                bad_count += 1
        if bad_count >= 1:
            f_info["news_alert"] = f"⚠️ 掃描到 {bad_count} 則利空新聞"
            
    except Exception:
        pass
    return f_info

# --- 5. 技術指標核心大腦 ---
def calculate_indicators(df):
    high_low_diff = (df['High'] - df['Low']).replace(0, 0.001) 
    mf_multiplier = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / high_low_diff
    df['主力籌碼'] = (df['Volume'] * mf_multiplier / 1000000).round(2)
    
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA14'] = df['Close'].rolling(14).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA21'] = df['Close'].rolling(21).mean()
    df['MA30'] = df['Close'].rolling(30).mean()
    df['50MA'] = df['Close'].rolling(50).mean()
    df['200MA'] = df['Close'].rolling(200).mean()
    df['ROC14'] = df['Close'].pct_change(14)
    
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ema_gain = gain.ewm(com=13, adjust=False).mean()
    ema_loss = loss.ewm(com=13, adjust=False).mean()
    rs = ema_gain / ema_loss.replace(0, 0.001)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    df['主力籌碼_Q80'] = df['主力籌碼'].rolling(50).quantile(0.8)
    df['主力籌碼_Q90'] = df['主力籌碼'].rolling(50).quantile(0.9)
    df['主力籌碼_Q95'] = df['主力籌碼'].rolling(50).quantile(0.95)
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    
    macd_shrink = [0] * len(df)
    hist = df['MACD_Hist'].values
    for i in range(1, len(df)):
        if hist[i] < 0 and hist[i] > hist[i-1]:
            macd_shrink[i] = macd_shrink[i-1] + 1
        else:
            macd_shrink[i] = 0
    df['MACD_Shrink'] = macd_shrink
    return df

# --- 6. V06.3 歷史回測引擎 ---
def run_backtest_engine(df, strategy_name, days, posture, fund_info):
    valid_df = df.dropna(subset=['200MA', 'ROC14', 'MACD_Hist', 'RSI_14', 'Vol_MA20', '主力籌碼_Q80', '主力籌碼_Q90', '主力籌碼_Q95']).tail(days).copy()
    if len(valid_df) < 5:
        return "⚠️ 數據不足", 0, 0, 0, 0, "❌ 不推薦", "🛑 數據不足", "-", "-", "-", [], [], [], valid_df

    if "🚀" in posture: rsi_max, vol_mult, dip_pct, rsi_min, chip_col = 75, 1.05, -0.10, 35, '主力籌碼_Q80'
    elif "🥶" in posture: rsi_max, vol_mult, dip_pct, rsi_min, chip_col = 65, 1.50, -0.15, 25, '主力籌碼_Q95'
    else: rsi_max, vol_mult, dip_pct, rsi_min, chip_col = 70, 1.20, -0.10, 30, '主力籌碼_Q90'

    if "A:" in strategy_name: s_ma, d_ma, stop_loss_pct = valid_df['MA5'], valid_df['MA14'], 0.05
    elif "B:" in strategy_name: s_ma, d_ma, stop_loss_pct = valid_df['MA14'], valid_df['MA21'], 0.075
    elif "C:" in strategy_name: s_ma, d_ma, stop_loss_pct = valid_df['MA10'], valid_df['MA30'], 0.10
    elif "D:" in strategy_name: s_ma, d_ma, stop_loss_pct = valid_df['MA20'], valid_df['200MA'], 0.05
    else: s_ma, d_ma, stop_loss_pct = valid_df['MA5'], valid_df['MA20'], 0.06

    max_ma, min_ma = valid_df[['MA5', 'MA14', '50MA']].max(axis=1), valid_df[['MA5', 'MA14', '50MA']].min(axis=1)
    is_entangled_arr = (((max_ma - min_ma) / valid_df['50MA'].replace(0, 0.001)) < 0.025).values

    closes, highs, lows = valid_df['Close'].values, valid_df['High'].values, valid_df['Low'].values
    s_mas, m200s, r14s, rsis = s_ma.values, valid_df['200MA'].values, valid_df['ROC14'].values, valid_df['RSI_14'].values
    vols, vol_m20s = valid_df['Volume'].values, valid_df['Vol_MA20'].values
    m_shrinks, m_hists, m_flows, chip_threshs = valid_df['MACD_Shrink'].values, valid_df['MACD_Hist'].values, valid_df['主力籌碼'].values, valid_df[chip_col].values

    has_position = False
    entry_price, highest_price_since_entry = 0, 0
    total_trades, win_trades = 0, 0
    total_return, total_gross_profit, total_gross_loss = 0.0, 0.0, 0.0
    trade_logs, plot_buys, plot_sells = [], [], []

    for i in range(len(valid_df)):
        date_str = valid_df.index[i].strftime('%Y-%m-%d')
        close_p, high_p, low_p = closes[i], highs[i], lows[i]
        sma_p, m200_p, r14_p, rsi_p = s_mas[i], m200s[i], r14s[i], rsis[i]
        vol_p, vol_m20_p = vols[i], vol_m20s[i]
        m_shrink_p, m_hist_p, m_flow_p, chip_thresh_p = m_shrinks[i], m_hists[i], m_flows[i], chip_threshs[i]
        m_hist_y = m_hists[i-1] if i > 0 else 0
        is_entangled = is_entangled_arr[i]

        if not has_position:
            is_buy = False
            if "A:" in strategy_name:
                if (m_shrink_p >= 1 or (m_hist_p > m_hist_y and m_hist_p > 0)) and r14_p > 0 and rsi_p < rsi_max: is_buy = True
            elif "B:" in strategy_name or "C:" in strategy_name:
                if (not is_entangled) and close_p > sma_p and vol_p > vol_m20_p * vol_mult: is_buy = True
            elif "D:" in strategy_name:
                if m200_p > 0 and (close_p - m200_p)/m200_p <= dip_pct and m_shrink_p >= 1 and rsi_p < rsi_min: is_buy = True
            elif "E:" in strategy_name:
                if m_flow_p > chip_thresh_p and m_flow_p > 0: is_buy = True
            
            if is_buy:
                has_position, entry_price, highest_price_since_entry = True, close_p, close_p
                total_trades += 1
                trade_logs.append({"交易日期": date_str, "動作狀態": "🟢 買入進場 (BUY)", "執行價格": f"${close_p:.2f}", "單筆報酬": "-"})
                plot_buys.append((valid_df.index[i], close_p))
        else:
            highest_price_since_entry = max(highest_price_since_entry, high_p)
            is_exit, exit_price = False, close_p

            if "D:" not in strategy_name:
                if low_p <= highest_price_since_entry * (1 - stop_loss_pct):
                    is_exit, exit_price = True, highest_price_since_entry * (1 - stop_loss_pct)
                elif ("B:" in strategy_name or "C:" in strategy_name) and is_entangled:
                    is_exit, exit_price = True, close_p
            else:
                if high_p >= m200_p: is_exit, exit_price = True, m200_p
                elif low_p <= entry_price * 0.95: is_exit, exit_price = True, entry_price * 0.95

            if is_exit:
                trade_return = (exit_price - entry_price) / entry_price
                total_return += trade_return
                if trade_return > 0: win_trades += 1; total_gross_profit += trade_return
                else: total_gross_loss += abs(trade_return)
                has_position = False
                trade_logs.append({"交易日期": date_str, "動作狀態": "🔴 賣出出場 (SELL)", "執行價格": f"${exit_price:.2f}", "單筆報酬": f"{trade_return*100:+.2f}%"})
                plot_sells.append((valid_df.index[i], exit_price))

    final_win_rate = win_trades / total_trades if total_trades > 0 else 0.0
    profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else (99.9 if total_gross_profit > 0 else 0.0)
    pf_str = "無限" if profit_factor == 99.9 else f"{profit_factor:.2f}"

    stars = "❌ 不推薦"
    if total_return > 0 and total_trades > 0:
        if total_return >= 0.25 and final_win_rate >= 0.55: stars = "⭐⭐⭐⭐⭐"
        elif total_return >= 0.15 or final_win_rate >= 0.50: stars = "⭐⭐⭐⭐"
        else: stars = "⭐⭐"

    last_action = trade_logs[-1] if len(trade_logs) > 0 else None
    today_str = valid_df.index[-1].strftime('%Y-%m-%d')
    current_close = closes[-1]
    
    current_status = "💵 空手觀望 (CASH)"
    entry_price_str = "-"
    sl_price_str = "-"
    pnl_str = "-"

    if has_position:
        if last_action and last_action["交易日期"] == today_str and "BUY" in last_action["動作狀態"]:
            current_status = "🚀 今日大膽建倉 (BUY)"
            entry_price_str = f"${current_close:.2f}"
            pnl_str = "0.00%"
        else:
            current_status = "📦 獲利續抱中 (HOLD)"
            unrealized_pnl = (current_close - entry_price) / entry_price
            pnl_str = f"${unrealized_pnl*100:+.2f}%"
            entry_price_str = f"${entry_price:.2f}"

        sl_price_str = f"${highest_price_since_entry * (1 - stop_loss_pct):.2f}" if "D:" not in strategy_name else f"${max(entry_price * 0.95, m200s[-1]):.2f}"
    else:
        if last_action and last_action["交易日期"] == today_str and "SELL" in last_action["動作狀態"]:
            current_status = "🔴 今日觸發防守賣出 (SELL)"
        else:
            current_status = "💵 空手觀望 (CASH)"

    if enable_earnings_shield and fund_info["near_earnings"] and "BUY" in current_status:
        current_status = "💣 財報前夕/強制避險 (CASH)"
        
    if enable_fcf_filter and not fund_info["is_fcf_positive"] and "BUY" in current_status:
        current_status = "⚠️ 現金流不良/阻擋建倉 (CASH)"

    return "📡 運算完畢", total_return, final_win_rate, total_trades, pf_str, stars, current_status, entry_price_str, sl_price_str, pnl_str, trade_logs, plot_buys, plot_sells, valid_df

# ⚡ 多線程 Worker 函數
def process_single_stock_us(ticker, cloud_dict, backtest_days, posture, strategies):
    try:
        df_stock = yf.download(ticker, period="2y", progress=False)
        if df_stock.empty:
            return [], {}
        df_stock.columns = [col[0] if isinstance(col, tuple) else col for col in df_stock.columns]
        df_stock = calculate_indicators(df_stock)
        
        df_temp_clean = df_stock.dropna(subset=['Close'])
        current_close = float(df_temp_clean['Close'].iloc[-1]) if not df_temp_clean.empty else 0.0
        
        fund_info = fetch_fundamental_and_news(ticker, cloud_dict)
        
        stock_reports = []
        stock_details = {}
        
        for strat in strategies:
            radar, ret, win, trades, pf, stars, cur_status, entry_price_val, sl_price, pnl, t_logs, p_buys, p_sells, v_df = run_backtest_engine(df_stock, strat, backtest_days, posture, fund_info)
            stock_details[(ticker, strat)] = {"logs": pd.DataFrame(t_logs), "buys": p_buys, "sells": p_sells, "v_df": v_df}
            stock_reports.append({
                "股票代號": ticker, "當前市價": f"${current_close:.2f}", "產業領域": fund_info["sector_tag"], "策略手法": strat,
                "倉位狀態": cur_status,
                "基本面評價": fund_info["quality_tag"],
                "本益比 (PE)": fund_info["pe"],
                "自由現金流": fund_info["fcf"],
                "新聞警告": fund_info["news_alert"],
                "建議進場價(持股成本)": entry_price_val,
                "未實現損益": pnl, "嚴格防守價": sl_price,
                "總報酬率": f"{ret * 100:+.2f}%", "歷史勝率": f"{win * 100:.1f}%",
                "交易次數": trades, "獲利因子": pf, "推薦指數": stars
            })
        return stock_reports, stock_details
    except Exception:
        return [], {}

# --- 7. Session State 記憶庫 ---
if "calculated" not in st.session_state:
    st.session_state.calculated = False
    st.session_state.final_df = None
    st.session_state.detail_db = {}

# --- 8. 頂部總經抬頭控制卡 ---
col_v1, col_v2, col_v3 = st.columns(3)
col_v1.metric("VIX 恐慌指數", f"{vix_score:.2f}", delta="避險戒備" if vix_score >= 25 else "市場平穩", delta_color="inverse")
col_v2.metric("S&P 500 大盤位階", "年線之上 (多頭)" if is_spy_bull else "跌破年線 (空頭)")
col_v3.metric("系統自動環境姿態", market_posture)
st.divider()

if st.button("🚀 啟動 V06.3 美股全自動多因子掃描引擎 (⚡ 多線程平行加速)", use_container_width=True):
    with st.spinner("正在啟動 ThreadPoolExecutor 多線程引擎進行全維度平行運算..."):
        master_report, strategies = [], ["A: 激進動能型", "B: 穩健波段型", "C: 槓桿防守型", "D: 均值回歸抄底型", "E: 籌碼主力跟隨型"]
        
        futures = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for ticker in ticker_list:
                f = executor.submit(process_single_stock_us, ticker, cloud_names_dict, backtest_days, market_posture, strategies)
                futures.append(f)
                
        for f in futures:
            s_reports, s_details = f.result()
            if s_reports:
                master_report.extend(s_reports)
                st.session_state.detail_db.update(s_details)
                
        st.session_state.final_df = pd.DataFrame(master_report)
        st.session_state.calculated = True
        st.success("📊 V06.3 美股多因子矩陣計算完成！請至下方各分頁切換檢視。")

# --- 9. 網頁四獨立分頁系統 ---
tab_v062, tab_matrix, tab_debug, tab_manage = st.tabs([
    "📊 倉位動作與多因子總表", 
    "🎯 七維量化戰術矩陣", 
    "🔍 歷史回測與線圖驗證", 
    "➕ 雲端自選清單管理"
])

# --- 分頁 1: 與原本 V06.2 100% 相同 (動作快選 + 完整總表) ---
with tab_v062:
    if st.session_state.calculated:
        df_res = st.session_state.final_df
        
        st.subheader("🎯 倉位狀態分類看板 (動作快選)")
        
        buy_df = df_res[df_res['倉位狀態'].str.contains("BUY", na=False)]
        sell_df = df_res[df_res['倉位狀態'].str.contains("SELL", na=False)]
        hold_df = df_res[df_res['倉位狀態'].str.contains("HOLD", na=False)]
        risk_df = df_res[df_res['倉位狀態'].str.contains("現金流不良|財報前夕", na=False)]
        cash_df = df_res[df_res['倉位狀態'].str.contains("空手觀望", na=False)]
        
        col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
        col_c1.metric("🚀 今日建議建倉", f"{len(buy_df)} 筆")
        col_c2.metric("🔴 觸發防守賣出", f"{len(sel
