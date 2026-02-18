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
    st.subheader("美股 RS 篩選")
    st.caption("數據定位：B 欄(代號) / Z 欄(RS Rank) | 避開前兩列公式與標題")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 99, 90, key="us_input")
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('讀取 Google Sheet 數據中...'):
            gsheet_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E/edit?usp=sharing"
            csv_url = gsheet_url.replace('/edit?usp=sharing', '/export?format=csv')
            
            try:
                # 讀取完整表格，不設標題
                df_raw = pd.read_csv(csv_url, header=None)
                
                # 關鍵修正：根據截圖，資料從第三列開始，所以 iloc 索引從 2 開始
                # 抓取 B 欄 (index 1) 和 Z 欄 (index 25)
                df_us = df_raw.iloc[2:, [1, 25]].copy()
                df_us.columns = ['Symbol', 'RS_Rank']
                
                # 數值轉換：將 Z 欄轉為數字，無法轉換的內容(如公式殘留)會變 NaN
                df_us['RS_Rank'] = pd.to_numeric(df_us['RS_Rank'], errors='coerce')
                
                # 清理並篩選
                filtered_us = df_us.dropna(subset=['Symbol', 'RS_Rank'])
                filtered_us = filtered_us[filtered_us['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                
                if not filtered_us.empty:
                    # 格式化代號：轉大寫並去除可能的空格
                    symbols = filtered_us['Symbol'].astype(str).str.strip().str.upper().tolist()
                    csv_string_us = ",".join(symbols)
                    
                    st.success(f"找到 {len(filtered_us)} 檔標的")
                    
                    st.subheader("🔥 TradingView 匯入字串")
                    st.code(csv_string_us)
                    
                    # 下載按鈕使用 stretch 寬度
                    st.download_button(
                        label="📥 下載 US 清單 (.txt)",
                        data=csv_string_us,
                        file_name=f"US_RS{min_rs_us}_{get_tw_time().strftime('%Y%m%d')}.txt",
                        use_container_width=True
                    )
                    
                    st.subheader("📋 詳細數據表")
                    st.dataframe(filtered_us, use_container_width=True)
                else:
                    st.warning(f"篩選後無結果，請確認 Z 欄是否有數值。")
            
            except Exception as e:
                st.error(f"解析失敗: {e}")
                st.info("提示：請確認該 Google Sheet 連結是否仍然有效且公開。")
    st.subheader("美股 RS 篩選")
    st.caption("自動抓取 B 欄(代號) 與 Z 欄(RS Rank)，並從第二列開始解析")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 99, 90, key="us_input")
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('讀取數據中...'):
            # 獲取 CSV 連結
            gsheet_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E/edit?usp=sharing"
            csv_url = gsheet_url.replace('/edit?usp=sharing', '/export?format=csv')
            
            try:
                # 讀取時不設標題 (header=None)，確保所有列都被讀入
                df_raw = pd.read_csv(csv_url, header=None)
                
                # 做法：從第二列(index 1)開始抓取，並定位 B 欄(1)與 Z 欄(25)
                # iloc[1:, [1, 25]] 表示：列從 1 往後拿，欄只拿 index 1 和 25
                df_us = df_raw.iloc[1:, [1, 25]].copy()
                df_us.columns = ['Symbol', 'RS_Rank']
                
                # 數值轉換：將 Z 欄轉為數字，非數字者變 NaN
                df_us['RS_Rank'] = pd.to_numeric(df_us['RS_Rank'], errors='coerce')
                
                # 篩選：移除無效值，並過濾出符合分數的股票
                filtered_us = df_us.dropna(subset=['Symbol', 'RS_Rank'])
                filtered_us = filtered_us[filtered_us['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                
                if not filtered_us.empty:
                    # 清理代號格式：去空格、轉大寫
                    symbols = filtered_us['Symbol'].astype(str).str.strip().str.upper().tolist()
                    csv_string_us = ",".join(symbols)
                    
                    st.success(f"找到 {len(filtered_us)} 檔標的")
                    
                    st.subheader("🔥 TradingView 匯入字串")
                    st.code(csv_string_us)
                    
                    st.download_button(
                        label="📥 下載 US 清單 (.txt)",
                        data=csv_string_us,
                        file_name=f"US_RS{min_rs_us}_{get_tw_time().strftime('%Y%m%d')}.txt",
                        use_container_width=True
                    )
                    
                    st.subheader("📋 詳細數據")
                    st.dataframe(filtered_us, use_container_width=True)
                else:
                    st.warning(f"篩選後無結果。請檢查 Z 欄是否有大於 {min_rs_us} 的數值。")
            
            except Exception as e:
                st.error(f"解析失敗: {e}")
                st.info("提示：請確認該 Google Sheet 是否為公開分享狀態。")
    st.subheader("美股 RS 篩選 (指定 Z 欄 RS / B 欄代號)")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 99, 90, key="us_input")
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('讀取數據中...'):
            df_us = fetch_us_rs_from_gsheet()
            if df_us is not None:
                try:
                    # 做法：直接使用欄位索引位置（B 欄是 index 1, Z 欄是 index 25）
                    # 我們先取前 26 欄確保能抓到 Z
                    df_subset = df_us.iloc[:, [1, 25]].copy()
                    df_subset.columns = ['Symbol', 'RS_Rank']
                    
                    # 轉換 RS 欄位為數字，無法轉換的會變 NaN
                    df_subset['RS_Rank'] = pd.to_numeric(df_subset['RS_Rank'], errors='coerce')
                    
                    # 移除代號或 RS 為空的資料，並執行篩選
                    filtered_us = df_subset.dropna(subset=['Symbol', 'RS_Rank'])
                    filtered_us = filtered_us[filtered_us['RS_Rank'] >= min_rs_us].sort_values(by='RS_Rank', ascending=False)
                    
                    if not filtered_us.empty:
                        tv_list_us = filtered_us['Symbol'].astype(str).str.strip().tolist()
                        csv_us = ",".join(tv_list_us)
                        
                        st.success(f"找到 {len(filtered_us)} 檔標的")
                        st.subheader("🔥 TradingView 匯入字串")
                        st.code(csv_us)
                        
                        st.download_button(
                            "📥 下載 US 清單", 
                            csv_us, 
                            f"US_{get_tw_time().strftime('%Y_%m_%d')}.txt", 
                            use_container_width=True
                        )
                        st.dataframe(filtered_us, use_container_width=True)
                    else:
                        st.warning(f"在 Z 欄中找不到大於等於 {min_rs_us} 的數據。")
                        
                except Exception as e:
                    st.error(f"解析欄位時出錯: {e}")
                    st.info("提示：請確認該 Google Sheet 的 B 欄與 Z 欄是否有資料。")    st.subheader("美股 RS 篩選")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 99, 90, key="us_input")
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('讀取數據中...'):
            df_us = fetch_us_rs_from_gsheet()
            if df_us is not None:
                rs_col = next((c for c in df_us.columns if 'RS' in c.upper()), None)
                sym_col = next((c for c in df_us.columns if 'SYMBOL' in c.upper() or 'TICKER' in c.upper()), None)
                
                if rs_col and sym_col:
                    filtered_us = df_us[df_us[rs_col] >= min_rs_us].sort_values(by=rs_col, ascending=False)
                    tv_list_us = filtered_us[sym_col].astype(str).tolist()
                    csv_us = ",".join(tv_list_us)
                    
                    st.success(f"找到 {len(filtered_us)} 檔標的")
                    st.code(csv_us)
                    st.download_button("📥 下載 US 清單", csv_us, f"US_{get_tw_time().strftime('%Y_%m_%d')}.txt", use_container_width=True)
                    st.dataframe(filtered_us, use_container_width=True)
                else:
                    st.error("Sheet 格式不符，找不到 RS 或 Symbol 欄位。")

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