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

# --- 1. 台股專用工具 (穩定修復版) ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    """抓取最新股票對應表，確保 3581 等上櫃股不遺失"""
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
                
                # 處理文字中的全形與特殊空白
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = text.split() # 自動處理多個空格
                
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # 只抓取 4 碼純數字股票代號
                    if code.isdigit() and len(code) == 4:
                        if code not in mapping:
                            mapping[code] = {"name": name, "prefix": market}
        except Exception as e:
            st.sidebar.error(f"連線 {market} 失敗: {e}")
            continue
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

        return {
            "name": info.get('longName', ticker),
            "price": info.get('currentPrice', 0),
            "eps_growth": eps_growth,
            "ttm_eps_growth": ttm_eps_growth,
            "hi_52w": info.get('fiftyTwoWeekHigh', 0),
            "float": info.get('floatShares', 0),
            "inst_pct": info.get('heldPercentInstitutions', 0) * 100
        }
    except: return None
            
# --- UI 介面 ---
st.markdown(
    """<style>
    .custom-title-link { text-decoration: none !important; color: white !important; text-align: center; display: block; margin: 25px 0px; }
    </style>
    <a href="/" target="_self" class="custom-title-link"><h1>RS Rank Filter</h1></a>""", 
    unsafe_allow_html=True
)

# 側邊欄清除快取功能
if st.sidebar.button("🧹 重整市場資料 (清除快取)"):
    st.cache_data.clear()
    st.sidebar.success("快取已清除，請重新執行篩選！")

tab_us, tab_tw = st.tabs(["US (美股)", "TW (台股)"])

# --- 美股分頁 (略，保留原始邏輯) ---
with tab_us:
    st.subheader("美股 RS 篩選與 CANSLIM 分析")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 100, 70, key="us_input")
    if st.button("🚀 執行美股篩選", type="primary"):
        # ... (此處保留原有的美股 CSV 讀取與處理邏輯)
        pass

# --- 台股分頁 (修正核心輸出邏輯) ---
with tab_tw:
    st.subheader("台股 RS 篩選")
    col1, col2 = st.columns(2)
    with col1: weeks = st.number_input("週數", 1, 52, 2) 
    with col2: min_rank = st.number_input("RS Rank 下限", 1, 99, 80)
    max_count = st.slider("顯示上限", 50, 500, 200)

    if st.button("🚀 執行台股篩選", type="primary", use_container_width=True):
        with st.spinner('正在同步市場分類清單...'):
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
                        mkt = info['prefix']
                        name = info['name']
                    else:
                        mkt = "TWSE" # 最終保險，若 mapping 抓不到則預設上市
                        name = f"未知-{stock_code}"
                    
                    tv_list_tw.append(f"{mkt}:{stock_code}")
                    display_tw.append({"代號": stock_code, "名稱": name, "市場": mkt})
                
                st.success(f"找到 {len(codes)} 檔，Mapping 資料庫筆數: {len(mapping)}")
                csv_tw = ",".join(tv_list_tw)
                
                st.markdown("### 📋 TradingView 匯入清單")
                st.code(csv_tw)
                
                st.download_button("📥 下載 TW 清單", csv_tw, f"TW_RS_{get_tw_time().strftime('%Y_%m_%d')}.txt", use_container_width=True)
                st.dataframe(display_tw, use_container_width=True, hide_index=True)