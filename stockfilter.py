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
def get_canslim_info(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    # 獲取年度財務數據 (用於 A 指標)
    try:
        earnings = stock.earnings
        # 這裡會得到過去四年的數據，我們計算成長率
        if not earnings.empty and len(earnings) >= 2:
            annual_eps_growth = ((earnings['Earnings'].iloc[-1] / earnings['Earnings'].iloc[-2]) - 1) * 100
        else:
            annual_eps_growth = 0
    except:
        annual_eps_growth = 0

    # L 指標：直接取 session_state 裡的 RS_Rank (稍後在主程式對應)
    # M 指標：我們可以抓標普 500 (SPY) 的近期表現作為參考
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="5d")
        market_trend = "看漲" if hist['Close'].iloc[-1] > hist['Close'].iloc[-2] else "盤整/回檔"
    except:
        market_trend = "數據獲取失敗"

    # 回傳數據封裝 (補上 A, L, M)
    return {
        "name": info.get('longName', 'N/A'),
        "price": info.get('currentPrice', 0),
        "eps_growth": info.get('earningsGrowth', 0) * 100,
        "annual_eps_growth": annual_eps_growth, # A
        "hi_52w": info.get('fiftyTwoWeekHigh', 0),
        "float": info.get('floatShares', 0),
        "inst_pct": info.get('heldPercentInstitutions', 0) * 100,
        "market_trend": market_trend # M
    }

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

# --- 美股分頁 (完整替換區塊) ---
with tab_us:
    st.subheader("美股 RS 篩選與 CANSLIM 分析")
    
    # 建立子分頁：清單與分析
    tab_us_list, tab_us_analysis = st.tabs(["📋 篩選清單", "🔍 CANSLIM 深度分析"])
    
    with tab_us_list:
        min_rs_us = st.number_input("RS Rank 最低標", 1, 100, 70, key="us_input")
        
        if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
            with st.spinner('正在從 Google Sheet 獲取最新數據...'):
                base_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E"
                csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet=FinTasticRS"
                
                try:
                    df_raw = pd.read_csv(csv_url)
                    # 尋找 Symbol 和 RS Rank 欄位
                    symbol_col = next((col for col in df_raw.columns if 'Symbol' in str(col)), None)
                    rs_col = next((col for col in df_raw.columns if 'RS Rnk' in str(col)), None)
                    
                    if symbol_col and rs_col:
                        df_final = df_raw[[symbol_col, rs_col]].copy()
                        df_final.columns = ['Symbol', 'RS_Rank']
                        df_final['RS_Rank'] = pd.to_numeric(df_final['RS_Rank'], errors='coerce')
                        df_final['Symbol'] = df_final['Symbol'].astype(str).str.strip().str.upper()
                        
                        # 過濾非法資料
                        df_final = df_final[df_final['RS_Rank'].notna() & df_final['Symbol'].str.match(r'^[A-Z]{1,5}$')]
                        filtered_us = df_final[df_final['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                        
                        if not filtered_us.empty:
                            # 儲存到 session_state 供分析分頁使用
                            st.session_state['filtered_us_list'] = filtered_us['Symbol'].tolist()
                            st.session_state['df_us_full'] = filtered_us # 存下整張表以便查 RS Rank
                            
                            csv_string_us = ",".join(st.session_state['filtered_us_list'])
                            tw_now = get_tw_time()
                            dynamic_filename = f"US_{tw_now.strftime('%Y_%m_%d')}.txt"
                            
                            st.success(f"解析成功！找到 {len(filtered_us)} 檔標的 (RS >= {min_rs_us})")
                            st.code(csv_string_us)
                            st.download_button(f"📥 下載 {dynamic_filename}", csv_string_us, dynamic_filename, use_container_width=True)
                            st.dataframe(filtered_us, use_container_width=True, hide_index=True)
                        else:
                            st.warning("查無符合條件之股票。")
                    else:
                        st.error("Google Sheet 格式不正確，找不到 Symbol 或 RS Rnk 欄位。")
                except Exception as e:
                    st.error(f"連線失敗: {e}")

    with tab_us_analysis:
        # 檢查是否有篩選結果
        if 'filtered_us_list' in st.session_state and st.session_state['filtered_us_list']:
            selected_stock = st.selectbox("🎯 選擇代號查看 CANSLIM 數據", st.session_state['filtered_us_list'])
            
            if selected_stock:
                with st.spinner(f'正在讀取 {selected_stock} 財務數據...'):
                    data = get_canslim_info(selected_stock)
                    
                    # 獲取該股的 RS Rank (L 指標)
                    current_rs = "N/A"
                    if 'df_us_full' in st.session_state:
                        rs_row = st.session_state['df_us_full'][st.session_state['df_us_full']['Symbol'] == selected_stock]
                        if not rs_row.empty:
                            current_rs = rs_row['RS_Rank'].values[0]

                    if data:
                        st.markdown(f"### 📊 {selected_stock} - {data['name']}")
                        st.divider()
                        
                        # --- 佈局：三欄呈現 CANSLIM ---
                        m1, m2, m3 = st.columns(3)
                        
                        with m1:
                            st.write("#### 🔹 當期與年度 (C&A)")
                            # C 指標
                            st.metric("C: 當季 EPS 成長", f"{data['eps_growth']:.1f}%", delta="標竿 25%")
                            # A 指標
                            st.metric("A: 年度 EPS 成長", f"{data['annual_eps_growth']:.1f}%", delta="標竿 20%")
                            
                        with m2:
                            st.write("#### 🔹 動能與領漲 (N&L)")
                            # N 指標
                            dist_from_high = ((data['hi_52w'] - data['price']) / data['hi_52w']) * 100 if data['hi_52w'] > 0 else 0
                            st.metric("N: 距 52 週高點", f"${data['price']:.2f}", f"-{dist_from_high:.1f}%", delta_color="inverse")
                            # L 指標
                            st.metric("L: 相對強度 Rank", f"{current_rs}", delta="標竿 80")
                            
                        with m3:
                            st.write("#### 🔹 籌碼與大盤 (S&I&M)")
                            # S 指標
                            st.write(f"**S: 流通股 (Float)**")
                            st.info(f"{data['float']/1e6:.1f}M Shares")
                            # I 指標
                            st.write(f"**I: 法人持股**")
                            st.info(f"{data['inst_pct']:.1f}%")
                            # M 指標
                            st.write(f"**M: 市場趨勢 (SPY)**")
                            st.warning(f"當前：{data['market_trend']}")

                        st.divider()
                        # 視覺化法人支持度
                        st.progress(min(max(data['inst_pct']/100, 0.0), 1.0), text="法人支持度 (I 指標)")
                        
                        # 簡單分析結論
                        if data['eps_growth'] > 25 and data['annual_eps_growth'] > 20 and dist_from_high < 10:
                            st.success(f"✅ {selected_stock} 符合 CANSLIM 強勢股特徵！")
                        else:
                            st.info(f"💡 {selected_stock} 在部分指標上尚待觀察。")
                    else:
                        st.warning("⚠️ 無法從 yfinance 獲取該股數據。")
        else:
            st.info("💡 請先在「📋 篩選清單」執行篩選，清單將會自動同步至此處。")

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