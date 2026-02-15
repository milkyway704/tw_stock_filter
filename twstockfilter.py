import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import re

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
            # 解碼 MoneyDJ 的 Unicode 逃逸字元
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip()]
    except Exception as e:
        st.error(f"連線 MoneyDJ 發生錯誤: {e}")
    return []

# --- 3. 網頁 UI 介面 ---
st.title("🇹🇼 台股 RS Rank 篩選器")
st.info("本工具會從 MoneyDJ 抓取數據，並轉換為 TradingView 匯入格式。")

with st.sidebar:
    st.header("篩選參數")
    weeks = st.slider("選擇週數", 1, 52, 1)
    min_rank = st.number_input("RS Rank 大於等於", 1, 99, 80)
    btn = st.button("執行篩選", type="primary")

if btn:
    with st.spinner('正在獲取最新數據...'):
        mapping = get_stock_mapping()
        codes = fetch_moneydj_rs(weeks, min_rank)
        
        if codes:
            tv_format_list = []
            display_data = []
            
            for c in codes:
                info = mapping.get(c)
                if info:
                    prefix_code = f"{info['prefix']}:{c}"
                    tv_format_list.append(prefix_code)
                    display_data.append({"代號": c, "名稱": info['name'], "市場": info['prefix']})
            
            st.success(f"找到 {len(tv_format_list)} 檔符合條件的股票！")
            
            # 下載與複製區
            csv_string = ",".join(tv_format_list)
            st.subheader("TradingView 匯入清單")
            st.text_area("直接複製以下文字到 TradingView", value=csv_string, height=150)
            
            st.download_button(
                label="📥 下載 .txt 檔案",
                data=csv_string,
                file_name=f"RS_Rank_{weeks}W_{min_rank}.txt",
                mime="text/plain"
            )
            
            st.subheader("詳細清單")
            st.dataframe(display_data, use_container_width=True)
        else:
            st.warning("查無符合條件之股票。")