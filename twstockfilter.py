import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import urllib3

# [cite_start]禁用 SSL 安全警告 [cite: 1]
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台股 RS 篩選器", page_icon="📈")

# --- 1. 股票地圖 (SSL 忽略版) ---
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
            # [cite_start]關鍵：verify=False 解決雲端 SSL 報錯 [cite: 1]
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
        except:
            continue
    return mapping

# --- 2. MoneyDJ 抓取 ---
def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.encoding = 'big5'
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip().isdigit()]
    except:
        pass
    return []

# --- 3. 介面佈局 ---
st.title("🇹🇼 台股 RS Rank 篩選器")

# 設定區
weeks = st.slider("選擇週數", 1, 52, 1)
min_rank = st.number_input("RS Rank 大於等於", 1, 99, 80)
max_count = st.number_input("至多顯示幾筆", 1, 500, 200)

# 重新放回 MoneyDJ 連結 (會隨參數變動)
mdj_url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
st.markdown(f"🔍 [🔗 開啟 MoneyDJ 原始網頁確認]({mdj_url})")

btn = st.button("🚀 執行篩選", type="primary", use_container_width=True)

st.divider()

if btn:
    with st.spinner('正在同步數據...'):
        mapping = get_stock_mapping()
        codes = fetch_moneydj_rs(weeks, min_rank)
        
        if codes:
            final_codes = codes[:max_count]
            tv_list = []
            display_data = []
            
            for c in final_codes:
                info = mapping.get(str(c))
                mkt = info['prefix'] if info else "TWSE"
                name = info['name'] if info else "名稱待查"
                tv_list.append(f"{mkt}:{c}")
                display_data.append({"代號": c, "名稱": name, "市場": mkt})
            
            st.success(f"找到共 {len(codes)} 檔股票")
            
            # TradingView 區塊
            current_date = datetime.now().strftime("%Y_%m_%d")
            csv_string = ",".join(tv_list)
            st.subheader("🔥 TradingView 匯入字串")
            st.code(csv_string)
            
            st.download_button(
                label=f"📥 下載 TW_{current_date}.txt",
                data=csv_string,
                file_name=f"TW_{current_date}.txt",
                mime="text/plain",
                use_container_width=True
            )
            
            st.subheader("📋 詳細清單")
            st.dataframe(display_data, use_container_width=True)
        else:
            st.warning("查無符合條件之股票。")
            st.info(f"建議點擊上方連結至 MoneyDJ 網頁確認是否有資料。")