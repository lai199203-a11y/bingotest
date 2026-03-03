import streamlit as st
import pandas as pd
import re, random, time
from datetime import datetime, timedelta
from collections import Counter
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from linebot import LineBotApi
from linebot.models import TextSendMessage

# --- [1. 讀取 Secrets] ---
try:
    LINE_TOKEN = st.secrets["LINE_TOKEN"]
    USER_IDS = st.secrets["USER_IDS"]
except:
    st.error("❌ Secrets 設定錯誤")
    st.stop()

def get_taipei_time():
    return datetime.utcnow() + timedelta(hours=8)

TARGET_URL = "https://www.pilio.idv.tw/bingo/list.asp"

st.set_page_config(page_title="BINGO AI 期號精準版", layout="wide")
st.title("🛡️ BINGO 賓果 AI 智能進化 (期號校驗版)")

if 'history' not in st.session_state: st.session_state.history = []

# --- [2. 核心分析邏輯] ---
def get_prediction_by_logic(all_nums, star, limit, logic_type="hot"):
    target_nums = all_nums[:(limit * 20)]
    counts = Counter(target_nums)
    scores = {i: 0 for i in range(1, 81)}
    max_count = max(counts.values()) if counts else 1
    
    for num in range(1, 81):
        freq = counts[num] / max_count
        if logic_type == "hot": scores[num] += freq * 60
        elif logic_type == "cold": scores[num] += (1 - freq) * 60
        else: scores[num] += 30
            
    for num in all_nums[:20]: scores[num] += 20
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_candidates = [item[0] for item in sorted_scores[:12]]
    return sorted(random.sample(top_candidates, star))

def run_strategy_sim(all_raw, star, limit):
    logics = ["hot", "cold", "trend"]
    logic_results = []
    for l in logics:
        total_hits = 0
        for i in range(1, 6): # 縮小模擬範圍加快速度
            past = all_raw[i*20 : i*20 + (limit*20)]
            ans = all_raw[(i-1)*20 : i*20]
            pred = get_prediction_by_logic(past, star, limit, l)
            total_hits += len([n for n in pred if n in ans])
        logic_results.append({"type": l, "hits": total_hits})
    sorted_res = sorted(logic_results, key=lambda x: x['hits'], reverse=True)
    return sorted_res[0]['type'], sorted_res[1]['type']

# --- [3. 增強版抓取：含期號提取] ---
def fetch_draw_data():
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
        
        # 提取期號 (通常是 9 或 10 位數)
        issue_match = re.search(r'\b\d{9,10}\b', page_text)
        current_issue = int(issue_match.group()) if issue_match else 0
        
        # 提取號碼
        matches = re.findall(r'\b\d{2}\b', page_text)
        nums = [int(n) for n in matches if 1 <= int(n) <= 80]
        
        driver.quit()
        return current_issue, nums
    except: return 0, []

# --- [4. UI 介面設定] ---
st.sidebar.header("⚙️ AI 參數設定")
star_count = st.sidebar.slider("預測星數", 1, 10, 2)
analysis_range = st.sidebar.slider("分析樣本數", 100, 2000, 300, 100)

if st.sidebar.button("🗑️ 清空歷史紀錄"):
    st.session_state.history = []
    st.rerun()

# --- [5. 主執行邏輯] ---
col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 啟動雙重預測 (鎖定期號)"):
        with st.spinner('同步最新期號與分析中...'):
            curr_issue, all_raw = fetch_draw_data()
            if curr_issue > 0:
                next_issue = curr_issue + 1
                best, second = run_strategy_sim(all_raw, star_count, analysis_range)
                pred_1 = get_prediction_by_logic(all_raw, star_count, analysis_range, best)
                pred_2 = get_prediction_by_logic(all_raw, star_count, analysis_range, second)
                
                now_t = get_taipei_time().strftime("%H:%M:%S")
                st.session_state.history.insert(0, {
                    "預測期號": next_issue,
                    "時間": now_t,
                    "主推(🥇)": f"{best}: {pred_1}",
                    "副推(🥈)": f"{second}: {pred_2}",
                    "狀態": f"等待 {next_issue} 期開獎",
                    "raw_p1": pred_1, "raw_p2": pred_2,
                    "checked": False
                })
                st.success(f"✅ 已鎖定下一期：{next_issue}")
                
                # LINE 推播
                try:
                    line_bot_api = LineBotApi(LINE_TOKEN)
                    msg = f"\n🎯 預測期號：{next_issue}\n🥇 主({best})：{pred_1}\n🥈 副({second})：{pred_2}"
                    for uid in USER_IDS: line_bot_api.push_message(uid, TextSendMessage(text=msg))
                except: pass

with col2:
    if st.button("🔄 精準對獎 (核對期號)"):
        with st.spinner('核對期號中...'):
            web_issue, current_20 = fetch_draw_data()
            if web_issue > 0:
                updated = False
                for record in st.session_state.history:
                    # 只有當網頁期號 >= 紀錄中的預測期號，且尚未對獎過
                    if not record["checked"] and web_issue >= record["預測期號"]:
                        h1 = [n for n in record["raw_p1"] if n in current_20]
                        h2 = [n for n in record["raw_p2"] if n in current_20]
                        record["狀態"] = f"🥇中{len(h1)} | 🥈中{len(h2)}"
                        record["checked"] = True
                        updated = True
                
                if updated: st.success(f"✅ 期號 {web_issue} 已更新對獎結果！")
                else: st.info(f"⌛ 目前最新期號為 {web_issue}，預測期號尚未開出。")
                st.rerun()

# --- [6. 顯示結果] ---
st.markdown("---")
if st.session_state.history:
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df[["預測期號", "時間", "主推(🥇)", "副推(🥈)", "狀態"]], use_container_width=True)
else:
    st.info("💡 請點擊左側按鈕開始預測下一期。")
