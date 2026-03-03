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

st.set_page_config(page_title="BINGO AI 終極穩定版", layout="wide")
st.title("🛡️ BINGO 賓果 AI 策略進化 (雷達對位修復版)")

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
            
    # 近 20 期『手感』加權
    for num in all_nums[:20]: scores[num] += 25 
    
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

# --- [3. 強化版抓取：期號模糊定位技術] ---
def fetch_raw_page_data():
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
        
        # 找出當前最新期號 (9-10位數)
        issue_match = re.search(r'\b\d{9,10}\b', page_text)
        current_issue = int(issue_match.group()) if issue_match else 0
        
        # 找出所有數字供分析使用
        all_matches = re.findall(r'\b\d{2}\b', page_text)
        all_nums = [int(n) for n in all_matches if 1 <= int(n) <= 80]
        
        driver.quit()
        return current_issue, all_nums, page_text
    except: return 0, [], ""

def find_exact_draw_nums(target_issue, page_text):
    """
    錨點追蹤法：
    1. 找到期號文字位置
    2. 往後抓取 400 個字元範圍
    3. 提取前 20 個兩位數數字
    """
    try:
        issue_str = str(target_issue)
        if issue_str not in page_text:
            return None 
        
        # 定位期號錨點
        start_idx = page_text.find(issue_str)
        # 截取期號後方的數據區 (約 400 字元足以包含 20 顆球)
        data_block = page_text[start_idx + len(issue_str) : start_idx + 450]
        
        # 提取該區塊內所有的兩位數
        found_nums = re.findall(r'\b\d{2}\b', data_block)
        
        if len(found_nums) >= 20:
            return [int(n) for n in found_nums[:20]]
        return None
    except:
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
        with st.spinner('AI 正在計算最強路徑...'):
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
                    "結果狀態": f"⏳ 等待 {next_issue} 期",
                    "raw_p1": p1, "raw_p2": p2, "checked": False
                })
                st.success(f"✅ 已預約期號：{next_issue}")
                
                try:
                    line_bot_api = LineBotApi(LINE_TOKEN)
                    msg = f"\n🎯 預測期號：{next_issue}\n🥇 主({best})：{p1}\n🥈 副({second})：{p2}"
                    for uid in USER_IDS: line_bot_api.push_message(uid, TextSendMessage(text=msg))
                except: pass

with col2:
    if st.button("🔄 精準對獎 (雷達掃描)"):
        with st.spinner('正在掃描網頁期號...'):
            _, _, page_text = fetch_raw_page_data()
            updated = False
            for record in st.session_state.history:
                if not record["checked"]:
                    # 使用錨點追蹤法找獎號
                    exact_nums = find_exact_draw_nums(record["預測期號"], page_text)
                    if exact_nums:
                        h1 = [n for n in record["raw_p1"] if n in exact_nums]
                        h2 = [n for n in record["raw_p2"] if n in exact_nums]
                        record["結果狀態"] = f"🥇中{len(h1)} | 🥈中{len(h2)}"
                        record["checked"] = True
                        updated = True
            
            if updated: st.success("✅ 對獎成功！已比對正確期號。")
            else: st.warning("⌛ 網頁尚未看到該期號，請稍候。")
            st.rerun()

# --- [6. 顯示區] ---
st.markdown("---")
if st.session_state.history:
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df[["預測期號", "時間", "主推(🥇)", "副推(🥈)", "結果狀態"]], use_container_width=True)
else:
    st.info("💡 尚未開始，請點擊左側啟動預測。")
