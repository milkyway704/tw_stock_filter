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

# --- 1. 台股專用工具 (強化穩定性版) ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    """從證交所與櫃買中心抓取最新股票對應表，確保正確區分上市上櫃"""
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", 
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    mapping = {}
    # 使用完整的 User-Agent 以避免被伺服器拒絕存取
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    }
    
    for market, url in urls.items():
        try:
            # 增加 timeout 並確保不驗證 SSL (因應某些網路環境限制)
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.encoding = 'ms950'
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if not cols or len(cols) < 1: continue
                    
                    # 清洗文字，處理全形空白與換行符號
                    raw_text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                    parts = raw_text.split()
                    
                    if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4:
                        code = parts[0]
                        # 邏輯：如果該代號在任一市場出現，則記錄其名稱與對應市場前綴
                        mapping[code] = {
                            "name": parts[1], 
                            "prefix": market
                        }
        except Exception as e:
            st.sidebar.warning(f"市場資料同步異常 ({market}): {e}")
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

# --- 2. CANSLIM 分析函數 (維持原有邏輯) ---
@st.cache_data(ttl=3600)
def get_canslim_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {"name": info.get('longName', ticker), "price": info.get('currentPrice', 0)}
    except: return None
            
# --- UI 介面 (嚴格按照截圖固定) ---
st.markdown(
    """
    <style>
    .stApp a.heading-link { display: none !important; }
    .custom-title-link {
        text-decoration: none !important; color: white !important; text-align: center; display: block; margin: 25px 0px;
    }
    .custom-title-link h1 { color: white !important; margin: 0; }
    </style>
    <a href="/" target="_self" class="custom-title-link">
        <h1>RS Rank Filter</h1>
    </a>
    """, 
    unsafe_allow_html=True
)

tab_us, tab_tw = st.tabs(["US (美股)", "TW (台股)"])

# --- 美股分頁 ---
with tab_us:
    st.subheader("美股 RS 篩選與 CANSLIM 分析")
    # (此處保留原有的美股讀取邏輯)

# --- 台股分頁 ---
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
                        # 如果在 mapping 內，使用正確的市場前綴 (解決 3581 TPEX 問題)
                        mkt = info['prefix']
                        name = info['name']
                    else:
                        # 只有當 mapping 真的抓不到時，才採用 TWSE 作為最後保險
                        mkt = "TWSE"
                        name = f"未知-{stock_code}"
                    
                    tv_list_tw.append(f"{mkt}:{stock_code}")
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
            else:
                st.error("無法從 MoneyDJ 獲取數據。")