import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import yfinance as yf  # 新增：用於抓取 CANSLIM 財務數據

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定頁面
st.set_page_config(page_title="RS Rank Filter", page_icon="📈", layout="wide")

# --- 通用工具 ---
def get_tw_time():
    return datetime.utcnow() + timedelta(hours=8)

# --- 1. 台股專用工具 (省略重複代碼，保持原本 logic) ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    urls = {"TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"}
    mapping = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for market, url in urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
            resp.encoding = 'ms950'
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('tr')
            prefix = "TWSE" if market == "TWSE" else "TPEX"
            for row in rows:
                cols = row.find_all('td')
                if not cols or len(cols) < 1: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = text.split(' ')
                if len(parts) >= 2 and parts[0].isdigit():
                    mapping[str(parts[0])] = {"name": parts[1], "prefix": prefix}
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

# --- 2. CANSLIM 分析函數 (新功能) ---
def get_canslim_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # 抓取季報數據
        earnings = ticker.quarterly_earnings if hasattr(ticker, 'quarterly_earnings') else None
        
        data = {
            "name": info.get("longName", "Unknown"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "price": info.get("currentPrice", 0),
            "float": info.get("floatShares", 0),
            "inst_pct": info.get("heldPercentInstitutions", 0) * 100,
            "hi_52w": info.get("fiftyTwoWeekHigh", 1),
            "eps_growth": info.get("earningsQuarterlyGrowth", 0) * 100 if info.get("earningsQuarterlyGrowth") else 0
        }
        return data
    except:
        return None

# --- UI 介面開始 ---
# --- 強制標題樣式：原分頁跳轉（類 F5 效果） ---
st.markdown(
    """
    <style>
    /* 1. 隱藏 Streamlit 標題連結小圖示 */
    .stApp a.heading-link {
        display: none !important;
    }
    
    /* 2. 強制樣式：永遠白色、無底線 */
    .custom-title-link, .custom-title-link:link, .custom-title-link:visited, 
    .custom-title-link:hover, .custom-title-link:active {
        text-decoration: none !important;
        color: white !important;
        cursor: pointer;
        text-align: center;
        display: block;
        margin: 25px 0px;
    }

    .custom-title-link h1 {
        color: white !important;
        margin: 0;
    }
    </style>
    
    <a href="https://your-app-name.streamlit.app/" target="_self" class="custom-title-link">
        <h1>RS Rank Filter</h1>
    </a>
    """, 
    unsafe_allow_html=True
)
tab_us, tab_tw = st.tabs(["US (美股)", "TW (台股)"])

# --- 美股分頁 ---
with tab_us:
    st.subheader("美股 RS 篩選與分析")
    
    # 在美股分頁內建立子分頁
    tab_us_list, tab_us_analysis = st.tabs(["📋 篩選清單", "🔍 CANSLIM 深度分析"])
    
    with tab_us_list:
        min_rs_us = st.number_input("RS Rank 最低標", 1, 100, 70, key="us_input")
        
        if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
            with st.spinner('正在分析數據...'):
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
                        df_final['Symbol'] = df_final['Symbol'].astype(str).str.strip().str.upper()
                        
                        df_final = df_final[df_final['RS_Rank'].notna() & df_final['Symbol'].str.match(r'^[A-Z]{1,5}$')]
                        filtered_us = df_final[df_final['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                        
                        if not filtered_us.empty:
                            # 儲存到 session_state
                            st.session_state['filtered_us_list'] = filtered_us['Symbol'].tolist()
                            
                            csv_string_us = ",".join(st.session_state['filtered_us_list'])
                            tw_now = get_tw_time()
                            dynamic_filename = f"US_{tw_now.strftime('%Y_%m_%d')}.txt"
                            
                            st.success(f"解析成功！找到 {len(filtered_us)} 檔標的")
                            st.code(csv_string_us)
                            st.download_button(f"📥 下載 {dynamic_filename}", csv_string_us, dynamic_filename, use_container_width=True)
                            st.dataframe(filtered_us, use_container_width=True)
                        else:
                            st.warning("查無符合條件之股票。")
                except Exception as e:
                    st.error(f"連線失敗: {e}")

    with tab_us_analysis:
        if 'filtered_us_list' in st.session_state and st.session_state['filtered_us_list']:
            selected_stock = st.selectbox("🎯 選擇代號進行深度診斷", st.session_state['filtered_us_list'])
            
            if selected_stock:
                with st.spinner(f'正在讀取 {selected_stock} 的財務數據...'):
                    data = get_canslim_info(selected_stock)
                    
                    if data:
                        st.markdown(f"### 📊 {selected_stock} - {data['name']}")
                        st.markdown(f"**產業：** {data['sector']} | {data['industry']}")
                        st.divider()
                        
                        # 使用 columns 佈局讓資訊更美觀
                        m1, m2 = st.columns(2)
                        with m1:
                            # C 指標
                            st.metric("C: 當季 EPS 成長率", f"{data['eps_growth']:.1f}%", delta=f"{data['eps_growth']-25:.1f}%", delta_color="normal")
                            # S 指標
                            st.write(f"**S: 流通股數 (Float):** {data['float']/1e6:.1f}M")
                            
                        with m2:
                            # N 指標
                            dist_from_high = ((data['hi_52w'] - data['price']) / data['hi_52w']) * 100 if data['hi_52w'] > 0 else 0
                            st.metric("N: 距 52 週高點", f"${data['price']:.2f}", f"-{dist_from_high:.1f}%", delta_color="inverse")
                            # I 指標
                            st.write(f"**I: 法人持股比例:** {data['inst_pct']:.1f}%")
                        
                        st.progress(min(max(data['inst_pct']/100, 0.0), 1.0), text="法人支持度 (I)")
                        
                        # 補充說明
                        st.info(f"💡 分析結論：{selected_stock} 目前價格為 ${data['price']:.2f}。根據 CANSLIM，{'EPS 成長優於標竿' if data['eps_growth'] > 25 else 'EPS 成長尚待加強'}，且距離 52 週高點 {'極近，具突破潛力' if dist_from_high < 5 else '仍有一段距離'}。")
                    else:
                        st.warning("⚠️ 無法獲取該股財務數據，可能是 yfinance 暫時限制存取。")
        else:
            st.info("💡 請先在「篩選清單」分頁執行篩選，產生的名單將會顯示在這裡。")

# --- 台股分頁 (保持原本 Logic) ---
with tab_tw:
    st.subheader("台股 RS 篩選")
    col1, col2 = st.columns(2)
    with col1: weeks = st.number_input("週數", 1, 52, 2) 
    with col2: min_rank = st.number_input("RS Rank 下限", 1, 99, 80)
    
    max_count = st.slider("顯示上限", 50, 500, 200)

    if st.button("🚀 執行台股篩選", type="primary", use_container_width=True):
        with st.spinner('同步數據中...'):
            mapping = get_stock_mapping()
            codes = fetch_moneydj_rs(weeks, min_rank)
            if codes:
                final_codes = codes[:max_count]
                tv_list_tw = []; display_tw = []
                for c in final_codes:
                    info = mapping.get(str(c))
                    mkt = info['prefix'] if info else "TWSE"
                    name = info['name'] if info else f"代號 {c}"
                    tv_list_tw.append(f"{mkt}:{c}")
                    display_tw.append({"代號": c, "名稱": name, "市場": mkt})
                st.success(f"找到 {len(codes)} 檔標的")
                csv_tw = ",".join(tv_list_tw)
                st.code(csv_tw)
                st.download_button("📥 下載 TW 清單", csv_tw, f"TW_{get_tw_time().strftime('%Y_%m_%d')}.txt", use_container_width=True)
                st.dataframe(display_tw, use_container_width=True)