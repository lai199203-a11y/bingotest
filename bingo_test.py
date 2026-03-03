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
    st.error("❌ Secrets 設定錯誤，請確認 Streamlit 管理介面。")
    st.stop()

def get_taipei_time():
    return datetime.utcnow() + timedelta(hours=8)

TARGET_URL = "https://www.pilio.idv.tw/bingo/list.asp"

st.set_page_config(page_title="BINGO AI 策略進化版", layout="wide")
st.title("🛡️ BINGO 賓果 AI 策略進化 (期號精準對位)")

if 'history' not in st.session_state: st.session_state.history = []

# --- [2. 核心 AI 策略大腦] ---
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
        for i in range(1, 6): # 模擬最近 5 期
            past = all_raw[i*20 : i*20 + (limit*20)]
            ans = all_raw[(i-1)*20 : i*20]
            pred = get_prediction_by_logic(past, star, limit, l)
            total_hits += len([n for n in pred if n in ans])
        logic_results.append({"type": l, "hits": total_hits})
    sorted_res = sorted(logic_results, key=lambda x: x['hits'], reverse=True)
    return sorted_res[0]['type'], sorted_res[1]['type']

# --- [3. 強化版抓取：期號對一對一掃描] ---
def fetch_raw_page_data():
    """抓取整個網頁文字與最新期號"""
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
        # 找出當前最新期號
        issue_match = re.search(r'\b\d{9,10}\b', page_text)
        current_issue = int(issue_match.group()) if issue_match else 0
        # 找出所有數字供分析使用
        all_matches = re.findall(r'\b\d{2}\b', page_text)
        all_nums = [int(n) for n in all_matches if 1 <= int(n) <= 80]
        driver.quit()
        return current_issue, all_nums, page_text
    except: return 0, [], ""

def find_exact_draw_nums(target_issue, page_text):
    """在網頁文字中定位特定期號的 20 個號碼"""
    # 尋找 target_issue 後面緊跟著的 20 組兩位數
    pattern = str(target_issue) + r"[\s\S]*?((?:\b\d{2}\b\s*){20})"
    match = re.search(pattern, page_text)
    if match:
        nums = re.findall(r'\b\d{2}\b', match.group(1))
        return [int(n) for n in nums]
    return None

# --- [4. UI 介面] ---
st.sidebar.header("⚙️ AI 參數設定")
star_count = st.sidebar.slider("預測星數", 1, 10, 2)
analysis_range = st.sidebar.slider("分析樣本數", 100, 2000, 300, 100)

if st.sidebar.button("🗑️ 清空歷史紀錄"):
    st.session_state.history = []
    st.rerun()

# --- [5. 主執行區] ---
col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 啟動雙重預測 (鎖定期號)"):
        with st.spinner('AI 正在進化策略中...'):
            curr_issue, all_raw, _ = fetch_raw_page_data()
            if curr_issue > 0:
                next_issue = curr_issue + 1
                best, second = run_strategy_sim(all_raw, star_count, analysis_range)
                p1 = get_prediction_by_logic(all_raw, star_count, analysis_range, best)
                p2 = get_prediction_by_logic(all_raw, star_count, analysis_range, second)
                
                now_t = get_taipei_time().strftime("%H:%M:%S")
                st.session_state.history.insert(0, {
                    "預測期號": next_issue,
                    "時間": now_t,
                    "主推(🥇)": f"{best}: {p1}",
                    "副推(🥈)": f"{second}: {p2}",
                    "結果狀態": f"⏳ 等待 {next_issue} 期開獎",
                    "raw_p1": p1, "raw_p2": p2, "checked": False
                })
                st.success(f"✅ 已鎖定下一期：{next_issue}")
                
                try:
                    line_bot_api = LineBotApi(LINE_TOKEN)
                    msg = f"\n🎯 預測期號：{next_issue}\n🥇 主({best})：{p1}\n🥈 副({second})：{p2}"
                    for uid in USER_IDS: line_bot_api.push_message(uid, TextSendMessage(text=msg))
                except: pass

with col2:
    if st.button("🔄 精準對獎 (期號對位)"):
        with st.spinner('正在核對期號資料...'):
            _, _, page_text = fetch_raw_page_data()
            updated = False
            for record in st.session_state.history:
                if not record["checked"]:
                    # 關鍵：只找該紀錄專屬的期號
                    exact_nums = find_exact_draw_nums(record["預測期號"], page_text)
                    if exact_nums:
                        h1 = [n for n in record["raw_p1"] if n in exact_nums]
                        h2 = [n for n in record["raw_p2"] if n in exact_nums]
                        record["結果狀態"] = f"🥇中{len(h1)} | 🥈中{len(h2)}"
                        record["checked"] = True
                        updated = True
            
            if updated: st.success("✅ 找到對應期號，對獎完成！")
            else: st.warning("⌛ 網頁尚未出現預測期號，請稍後再按。")
            st.rerun()

# --- [6. 數據顯示區] ---
st.markdown("---")
if st.session_state.history:
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df[["預測期號", "時間", "主推(🥇)", "副推(🥈)", "結果狀態"]], use_container_width=True)
else:
    st.info("💡 請點擊按鈕開始預測。")
