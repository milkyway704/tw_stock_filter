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
        with st.spinner('正在讀取指定工作表...'):
            # 加入 gid=0 確保抓取正確分頁，如果 gid 錯誤，請將 0 替換為你在網址看到的數字
            gsheet_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E/edit?usp=sharing"
            # 修正：強制指定導出 FinTasticRS 分頁
            csv_url = gsheet_url.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
            
            try:
                # 1. 讀取數據
                df_raw = pd.read_csv(csv_url, header=None)
                
                symbol_idx = None
                rs_idx = None
                data_start_row = 0
                
                # 2. 掃描前 10 列尋找標題列
                for row_i in range(min(10, len(df_raw))):
                    row_list = [str(x).strip() for x in df_raw.iloc[row_i].tolist()]
                    
                    if 'Symbol' in row_list:
                        symbol_idx = row_list.index('Symbol')
                        # 尋找 RS Rnk (這份表裡面是 RS Rnk)
                        for col_i, col_val in enumerate(row_list):
                            if 'RS Rnk' in str(col_val):
                                rs_idx = col_i
                        data_start_row = row_i + 1
                        break

                if symbol_idx is not None and rs_idx is not None:
                    # 3. 提取並清理數據
                    df_final = df_raw.iloc[data_start_row:, [symbol_idx, rs_idx]].copy()
                    df_final.columns = ['Symbol', 'RS_Rank']
                    
                    df_final['RS_Rank'] = pd.to_numeric(df_final['RS_Rank'], errors='coerce')
                    df_final['Symbol'] = df_final['Symbol'].astype(str).str.strip().str.upper()
                    
                    # 移除無效代號
                    filtered_us = df_final[(df_final['Symbol'] != 'NAN') & (df_final['Symbol'] != '')].dropna()
                    filtered_us = filtered_us[filtered_us['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                    
                    if not filtered_us.empty:
                        # 加上交易所前綴
                        def add_tv_prefix(s):
                            return f"NASDAQ:{s}" if len(s) >= 4 else f"NYSE:{s}"
                        
                        tv_symbols = [add_tv_prefix(s) for s in filtered_us['Symbol']]
                        csv_string_us = ",".join(tv_symbols)
                        
                        st.success(f"成功找到 FinTasticRS 數據！")
                        st.code(csv_string_us)
                        st.download_button("📥 下載匯入檔", csv_string_us, f"US_RS{min_rs_us}.txt", use_container_width=True)
                        st.dataframe(filtered_us, use_container_width=True)
                    else:
                        st.warning("在此分頁中找不到符合条件的股票。")
                else:
                    st.error("❌ 抓取的分頁不正確或找不到 'Symbol' 欄位。")
                    st.write("目前抓取到的分頁前幾列內容：")
                    st.table(df_raw.head(3))
                    
            except Exception as e:
                st.error(f"執行異常: {e}")
                
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