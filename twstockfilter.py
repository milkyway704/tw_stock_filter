import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

# --- 設定網頁標題與風格 ---
st.set_page_config(page_title="台股 RS 篩選器", page_icon="📈")

# --- 1. 股票地圖獲取邏輯 (快取 7 天) ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    mapping = {}
    for market, url in urls.items():
        try:
            resp = requests.get(url)
            resp.encoding = 'ms950'
            soup = BeautifulSoup(resp.text, 'lxml')
            rows = soup.find('table', class_='h4').find_all('tr')
            prefix = "TWSE" if market == "TWSE" else "TPEX"
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 2: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = [p for p in text.split(' ') if p.strip()]
                if len(parts) >= 2 and parts[0].isdigit():
                    mapping[parts[0]] = {"name": parts[1], "prefix": prefix}
        except:
            continue
    return mapping

# --- 2. MoneyDJ API 抓取邏輯 ---
def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    try:
        resp = requests.get(url)
        resp.encoding = 'big5'
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip()]
    except Exception as e:
        st.error(f"連線 MoneyDJ 發生錯誤: {e}")
    return []

# --- 3. 網頁 UI 介面 (單欄佈局) ---
st.title("🇹🇼 台股 RS Rank 篩選器")

# 將篩選條件從側邊欄移至主頁面 (單欄式設計)
st.header("1. 設定篩選條件")
col1, col2 = st.columns(2) # 在電腦端並排，手機端會自動垂直排列
with col1:
    weeks = st.slider("選擇週數", 1, 52, 1)
with col2:
    min_rank = st.number_input("RS Rank 大於等於", 1, 99, 80)

max_count = st.number_input("至多顯示幾筆", min_value=1, max_value=500, value=200)

# 動態連結
mdj_url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
st.markdown(f"🔍 [🔗 開啟 MoneyDJ 原始網頁確認]({mdj_url})")

btn = st.button("🚀 執行篩選並產出清單", type="primary", use_container_width=True)

st.divider()

if btn:
    with st.spinner('正在同步數據...'):
        mapping = get_stock_mapping()
        codes = fetch_moneydj_rs(weeks, min_rank)
        
        if codes:
            final_codes = codes[:max_count]
            tv_format_list = []
            display_data = []
            
            for c in final_codes:
                info = mapping.get(c)
                if info:
                    prefix_code = f"{info['prefix']}:{c}"
                    tv_format_list.append(prefix_code)
                    display_data.append({"代號": c, "名稱": info['name'], "市場": info['prefix']})
            
            st.success(f"找到共 {len(codes)} 檔股票，顯示前 {len(display_data)} 檔")

            # --- 產出動態檔名 ---
            current_date = datetime.now().strftime("%Y_%m_%d")
            dynamic_filename = f"TW_{current_date}.txt"
            
            # TradingView 字串
            csv_string = ",".join(tv_format_list)
            st.subheader("🔥 TradingView 匯入字串")
            st.code(csv_string, language="text") 
            
            # 下載按鈕 (寬度撐滿方便手機點擊)
            st.download_button(
                label=f"📥 下載 {dynamic_filename}",
                data=csv_string,
                file_name=dynamic_filename,
                mime="text/plain",
                use_container_width=True
            )
            
            st.subheader("📋 詳細清單")
            st.dataframe(display_data, use_container_width=True)
        else:
            st.warning("查無符合條件之股票。")