import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime, timedelta
import urllib3

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定頁面
st.set_page_config(page_title="RS Rank Filter", page_icon="📈", layout="centered")

# --- 通用工具 ---
def get_tw_time():
    return datetime.utcnow() + timedelta(hours=8)

# --- 1. 台股專用：股票地圖 ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
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
                if not cols: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = text.split(' ')
                if len(parts) >= 2 and parts[0].isdigit():
                    mapping[str(parts[0])] = {"name": parts[1], "prefix": prefix}
        except: continue
    return mapping

# --- 2. 台股專用：MoneyDJ 抓取 ---
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

# --- 3. 美股專用：Google Sheet 抓取 ---
@st.cache_data(ttl=3600)
def fetch_us_rs_from_gsheet():
    gsheet_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E/edit?usp=sharing"
    csv_url = gsheet_url.replace('/edit?usp=sharing', '/export?format=csv')
    try:
        df = pd.read_csv(csv_url)
        return df
    except Exception as e:
        st.error(f"美股數據讀取失敗: {e}")
        return None

# --- UI 介面開始 ---
# 1. 標題居中
st.markdown("<h1 style='text-align: center;'>RS Rank Filter</h1>", unsafe_allow_html=True)

# 2. Tabs 切換 (US / TW)
tab_us, tab_tw = st.tabs(["🇺🇸 US (美股)", "🇹🇼 TW (台股)"])

# --- 美股分頁 ---
with tab_us:
    st.subheader("美股 RS 篩選 (分頁：FinTasticRS)")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 100, 90, key="us_input")
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('正在讀取數據並優化 TradingView 格式...'):
            base_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E"
            csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet=FinTasticRS"
            
            try:
                df_raw = pd.read_csv(csv_url)
                
                # 1. 自動識別欄位
                symbol_col = next((col for col in df_raw.columns if 'Symbol' in str(col)), None)
                rs_col = next((col for col in df_raw.columns if 'RS Rnk' in str(col)), None)
                
                if symbol_col and rs_col:
                    df_final = df_raw[[symbol_col, rs_col]].copy()
                    df_final.columns = ['Symbol', 'RS_Rank']
                    
                    # 2. 數據清理
                    df_final['RS_Rank'] = pd.to_numeric(df_final['RS_Rank'], errors='coerce')
                    df_final['Symbol'] = df_final['Symbol'].astype(str).str.strip().str.upper()
                    
                    # 移除無效代號：確保代號只包含英文字母與點（如 BRK.B）
                    def is_valid_symbol(s):
                        return bool(re.match(r'^[A-Z.]+$', s))
                    
                    df_final = df_final[df_final['Symbol'].apply(is_valid_symbol)]
                    
                    # 3. 篩選與排序
                    filtered_us = df_final.dropna(subset=['RS_Rank'])
                    filtered_us = filtered_us[filtered_us['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                    
                    if not filtered_us.empty:
                        # 4. TradingView 前綴優化
                        # 使用 "US:" 萬用前綴可解決 99% 的美股匯入問題
                        tv_symbols = [f"US:{s}" for s in filtered_us['Symbol']]
                        csv_string_us = ",".join(tv_symbols)
                        
                        # 5. 格式化檔名 (比照台股)
                        tw_time = get_tw_time()
                        dynamic_filename = f"US_{tw_time.strftime('%Y_%m_%d')}.txt"
                        
                        st.success(f"解析成功！找到 {len(filtered_us)} 檔標的")
                        
                        st.subheader("🔥 TradingView 匯入字串")
                        st.code(csv_string_us)
                        
                        st.download_button(
                            label=f"📥 下載 {dynamic_filename}",
                            data=csv_string_us,
                            file_name=dynamic_filename,
                            mime="text/plain",
                            use_container_width=True
                        )
                        st.dataframe(filtered_us, use_container_width=True)
                    else:
                        st.warning(f"查無 RS Rank >= {min_rs_us} 的標的。")
                else:
                    st.error("無法定位 Symbol 或 RS Rnk 欄位，請檢查分頁內容。")
                    
            except Exception as e:
                st.error(f"連線失敗: {e}")                

# --- 台股分頁 ---
with tab_tw:
    st.subheader("台股 RS 篩選")
    
    # 修改處：週數改為 number_input (預設 2)，並與排名下限併排
    col1, col2 = st.columns(2)
    with col1:
        weeks = st.number_input("週數", 1, 52, 2) 
    with col2:
        min_rank = st.number_input("RS Rank 下限", 1, 99, 80)
    
    max_count = st.slider("顯示上限", 50, 500, 200)

    # 保留 MoneyDJ 原始網頁連結
    mdj_url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    st.markdown(f"🔍 [🔗 開啟 MoneyDJ 原始網頁確認]({mdj_url})")

    if st.button("🚀 執行台股篩選", type="primary", use_container_width=True):
        with st.spinner('同步數據中...'):
            mapping = get_stock_mapping()
            codes = fetch_moneydj_rs(weeks, min_rank)
            
            if codes:
                final_codes = codes[:max_count]
                tv_list_tw = []
                display_tw = []
                
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
            else:
                st.warning("查無符合條件之股票。")