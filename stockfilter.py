import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import yfinance as yf

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定頁面
st.set_page_config(page_title="RS Rank Filter", page_icon="📈", layout="wide")

# --- 通用工具 ---
def get_tw_time():
    return datetime.utcnow() + timedelta(hours=8)

# --- 1. 台股專用工具 ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    """抓取股票對應表"""
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", 
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    mapping = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for market, url in urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.encoding = 'ms950'
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if not cols or len(cols) < 1: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = text.split() 
                if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4:
                    code = parts[0]
                    if code not in mapping:
                        mapping[code] = {"name": parts[1], "prefix": market}
        except: continue
    return mapping

def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.encoding = 'big5'
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip().isdigit()]
    except: pass
    return []

# --- 2. CANSLIM 分析函數 ---
@st.cache_data(ttl=3600)
def get_canslim_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        eps_growth = 0
        ttm_eps_growth = 0
        q_financials = stock.quarterly_financials
        if not q_financials.empty and "Net Income" in q_financials.index:
            net_income = q_financials.loc["Net Income"]
            if len(net_income) >= 5:
                current_q = net_income.iloc[0]
                last_year_q = net_income.iloc[4]
                if pd.notna(current_q) and pd.notna(last_year_q) and last_year_q != 0:
                    eps_growth = ((current_q / last_year_q) - 1) * 100
            if len(net_income) >= 8:
                current_4q_sum = net_income.iloc[0:4].sum()
                last_year_4q_sum = net_income.iloc[4:8].sum()
                if pd.notna(current_4q_sum) and pd.notna(last_year_4q_sum) and last_year_4q_sum != 0:
                    ttm_eps_growth = ((current_4q_sum / last_year_4q_sum) - 1) * 100
        if eps_growth == 0:
            eps_growth = info.get('earningsQuarterlyGrowth', 0) * 100
        market_trend = "數據獲取中"
        try:
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="20d")
            if len(spy_hist) >= 2:
                current_spy = spy_hist['Close'].iloc[-1]
                ma20_spy = spy_hist['Close'].mean()
                market_trend = "看漲" if current_spy > ma20_spy else "回檔"
        except: market_trend = "無法取得大盤資訊"
        return {
            "name": info.get('longName', ticker), "price": info.get('currentPrice', 0),
            "eps_growth": eps_growth, "ttm_eps_growth": ttm_eps_growth,
            "hi_52w": info.get('fiftyTwoWeekHigh', 0), "float": info.get('floatShares', 0),
            "inst_pct": info.get('heldPercentInstitutions', 0) * 100, "market_trend": market_trend
        }
    except: return None
            
# --- UI 介面 ---
st.markdown(
    """<style>
    .stApp a.heading-link { display: none !important; }
    .custom-title-link { text-decoration: none !important; color: white !important; text-align: center; display: block; margin: 25px 0px; }
    .custom-title-link h1 { color: white !important; margin: 0; }
    </style>
    <a href="/" target="_self" class="custom-title-link"><h1>RS Rank Filter</h1></a>""", 
    unsafe_allow_html=True
)

tab_us, tab_tw = st.tabs(["US (美股)", "TW (台股)"])

# --- 美股分頁 ---
with tab_us:
    st.subheader("美股 RS 篩選與 CANSLIM 分析")
    tab_us_list, tab_us_analysis = st.tabs(["📋 篩選清單", "🔍 CANSLIM"])
    with tab_us_list:
        min_rs_us = st.number_input("RS Rank 最低標", 1, 100, 70, key="us_input")
        if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
            with st.spinner('正在獲取最新數據...'):
                base_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E"
                csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet=FinTasticRS"
                try:
                    df_raw = pd.read_csv(csv_url)
                    symbol_col = next((col for col in df_raw.columns if 'Symbol' in str(col)), None)
                    rs_col = next((col for col in df_raw.columns if 'RS Rnk' in str(col)), None)
                    if symbol_col and rs_col:
                        df_final = df_raw[[symbol_col, rs_col]].copy()
                        df_final.columns = ['Symbol', 'RS_Rank']
                        df_final['RS_Rank'] = pd.to_numeric(df_final['RS_Rank'], errors='coerce')
                        df_final = df_final[df_final['RS_Rank'].notna()]
                        filtered_us = df_final[df_final['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                        if not filtered_us.empty:
                            st.session_state['filtered_us_list'] = filtered_us['Symbol'].tolist()
                            csv_string_us = ",".join(st.session_state['filtered_us_list'])
                            st.code(csv_string_us)
                            st.download_button(f"📥 下載 TXT", csv_string_us, f"US_{get_tw_time().strftime('%Y_%m_%d')}.txt", use_container_width=True)
                            st.dataframe(filtered_us, use_container_width=True, hide_index=True)
                except: st.error("連線失敗")

    with tab_us_analysis:
        if 'filtered_us_list' in st.session_state:
            selected_stock = st.selectbox("🎯 選擇代號查看 CANSLIM 數據", st.session_state['filtered_us_list'])
            if selected_stock:
                data = get_canslim_info(selected_stock)
                if data: st.write(f"### {selected_stock} - {data['name']}")
        else: st.info("💡 請先執行篩選。")

# --- 台股分頁 ---
with tab_tw:
    st.subheader("台股 RS 篩選")
    col1, col2 = st.columns(2)
    with col1: weeks = st.number_input("週數", 1, 52, 2) 
    with col2: min_rank = st.number_input("RS Rank 下限", 1, 99, 80)
    max_count = st.slider("顯示上限", 50, 500, 200)

    if st.button("🚀 執行台股篩選", type="primary", use_container_width=True):
        with st.spinner('正在獲取數據...'):
            mapping = get_stock_mapping()
            codes = fetch_moneydj_rs(weeks, min_rank)
            
            if codes:
                final_codes = codes[:max_count]
                tv_list_tw = []
                display_tw = []
                
                for c in final_codes:
                    stock_code = str(c)
                    info = mapping.get(stock_code)
                    
                    if info:
                        # 如果 Mapping 抓到了，就給正確的
                        mkt = info['prefix']
                        name = info['name']
                        tv_list_tw.append(f"{mkt}:{stock_code}")
                    else:
                        # 【核心修正點】：如果抓不到，幫你接上上市+上櫃組合
                        # TradingView 遇到 TWSE:3581,TPEX:3581 會自動對應正確的那個
                        name = f"自動識別-{stock_code}"
                        mkt = "TWSE/TPEX"
                        tv_list_tw.append(f"TWSE:{stock_code},TPEX:{stock_code}")
                    
                    display_tw.append({"代號": stock_code, "名稱": name, "市場": mkt})
                
                st.success(f"找到 {len(codes)} 檔標的")
                csv_tw = ",".join(tv_list_tw)
                
                st.markdown("### 📋 TradingView 匯入清單")
                st.code(csv_tw)
                
                st.download_button(
                    "📥 下載 TW 清單 (TXT)", 
                    csv_tw, 
                    f"TW_RS_{get_tw_time().strftime('%Y_%m_%d')}.txt", 
                    use_container_width=True
                )
                
                st.markdown("### 🔍 篩選結果明細")
                st.dataframe(display_tw, use_container_width=True, hide_index=True)