import streamlit as st
import pandas as pd
import re, random, time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from collections import Counter
from linebot import LineBotApi
from linebot.models import TextSendMessage

# --- [1. 設定區] ---
try:
    LINE_TOKEN = st.secrets["LINE_TOKEN"]
    USER_IDS = st.secrets["USER_IDS"]
except:
    st.error("❌ Secrets 設定錯誤")
    st.stop()

def get_taipei_time():
    return datetime.utcnow() + timedelta(hours=8)

TARGET_URL = "https://www.pilio.idv.tw/bingo/list.asp"

st.set_page_config(page_title="BINGO 每日實戰模擬器", layout="wide")
st.title("🏹 BINGO 賓果每日實戰模擬 (07:05 首期啟動)")

# 初始化 Session State
if 'daily_sim' not in st.session_state:
    st.session_state.daily_sim = [] # 儲存明天的模擬投注單
if 'last_draw_data' not in st.session_state:
    st.session_state.last_draw_data = []

# --- [2. 側邊欄參數] ---
st.sidebar.header("⚙️ 模擬設定")
star_count = st.sidebar.slider("預測星數", 1, 10, 2)
analysis_range = st.sidebar.slider("分析樣本數", 100, 2000, 500, 100)

if st.sidebar.button("🧹 重設所有數據"):
    st.session_state.daily_sim = []
    st.rerun()

# --- [3. 核心抓取與分析] ---
def fetch_data():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver") 
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(TARGET_URL)
        time.sleep(3)
        page_text = driver.find_element("tag name", "body").text
        matches = re.findall(r'\b\d{2}\b', page_text)
        final_nums = [int(n) for n in matches if 1 <= int(n) <= 80]
        driver.quit()
        return final_nums
    except: return []

def advanced_analysis(all_nums, star, limit):
    target_nums = all_nums[:(limit * 20)]
    counts = Counter(target_nums)
    scores = {i: 0 for i in range(1, 81)}
    max_count = max(counts.values()) if counts else 1
    for num, count in counts.items():
        scores[num] += (count / max_count) * 50
    for num in all_nums[:20]:
        scores[num] += 15
    for num in range(1, 81):
        scores[num] += random.randint(0, 10)
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_candidates = [item[0] for item in sorted_scores[:15]]
    return sorted(random.sample(top_candidates, star))

# --- [4. 實戰模擬邏輯] ---
st.subheader("📅 明日實戰預演區")
st.write("設定完成後，AI 會根據明早 07:05 起的每一期進行連續預測模擬。")

if st.button("📝 生成明早首期預測單"):
    with st.spinner('計算中...'):
        all_raw = fetch_data()
        if all_raw:
            # 取得明天的日期
            tomorrow = (get_taipei_time() + timedelta(days=1)).strftime("%Y-%m-%d")
            # 產生第一期的預測
            pred = advanced_analysis(all_raw, star_count, analysis_range)
            
            new_entry = {
                "期數時間": f"{tomorrow} 07:05",
                "預測號碼": pred,
                "開獎結果": "等待明日開獎...",
                "中獎狀態": "-"
            }
            st.session_state.daily_sim.insert(0, new_entry)
            st.success(f"✅ 已成功預約！明早 07:05 第一期預測號碼為：{pred}")
            
            # LINE 推播通知
            try:
                line_bot_api = LineBotApi(LINE_TOKEN)
                msg = f"\n📢 預約明日首期(07:05)\n🎯 推薦：{pred}\n💰 設定：{star_count}星 / {analysis_range}樣本"
                for uid in USER_IDS: line_bot_api.push_message(uid, TextSendMessage(text=msg))
            except: pass

# --- [5. 自動對獎顯示] ---
if st.session_state.daily_sim:
    st.write("---")
    st.info("💡 明天早上 07:10 後，回到本網頁按下「更新對獎狀態」，AI 將自動比對開獎結果。")
    
    if st.button("🔄 更新對獎狀態"):
        all_raw = fetch_data()
        current_20 = sorted(all_raw[:20]) if all_raw else []
        if current_20:
            for entry in st.session_state.daily_sim:
                if entry["開獎結果"] == "等待明日開獎...":
                    # 這裡可以加入更精確的期數比對邏輯，目前先以最新一期嘗試對獎
                    hits = [n for n in entry["預測號碼"] if n in current_20]
                    entry["開獎結果"] = str(current_20)
                    entry["中獎狀態"] = f"中 {len(hits)} 顆"
            st.rerun()

    st.table(pd.DataFrame(st.session_state.daily_sim))