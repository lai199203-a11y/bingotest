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
    st.error("❌ 讀取 Secrets 失敗，請檢查 Streamlit 後台。")
    st.stop()

def get_taipei_time():
    return datetime.utcnow() + timedelta(hours=8)

TARGET_URL = "https://www.pilio.idv.tw/bingo/list.asp"

st.set_page_config(page_title="BINGO AI 雙重智能進化版", layout="wide")
st.title("🛡️ BINGO 賓果 AI 雙重智能進化版")

# 初始化紀錄
if 'history' not in st.session_state:
    st.session_state.history = []
if 'last_draw_data' not in st.session_state:
    st.session_state.last_draw_data = []

# --- [2. 核心 AI 策略大腦] ---

def get_prediction_by_logic(all_nums, star, limit, logic_type="hot"):
    """
    三種算牌邏輯：
    1. hot: 順勢抓熱門
    2. cold: 逆勢抓冷門(回歸)
    3. trend: 均值回歸與震盪加權
    """
    target_nums = all_nums[:(limit * 20)]
    counts = Counter(target_nums)
    scores = {i: 0 for i in range(1, 81)}
    max_count = max(counts.values()) if counts else 1
    
    for num in range(1, 81):
        freq = counts[num] / max_count
        if logic_type == "hot":
            scores[num] += freq * 60
        elif logic_type == "cold":
            scores[num] += (1 - freq) * 60
        else: # trend
            scores[num] += 30
            
    # 近 20 期『手感』加權 (算牌的核心：近況)
    for num in all_nums[:20]:
        scores[num] += 20 # 提高近況權重
        
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # 從前 12 名最強候選中隨機選出指定星數，增加擾動避免死板
    top_candidates = [item[0] for item in sorted_scores[:12]]
    return sorted(random.sample(top_candidates, star))

def run_strategy_sim(all_raw, star, limit):
    """【模擬考模式】回測最近 10 期，排列出最強策略順序"""
    logics = ["hot", "cold", "trend"]
    logic_results = []
    
    for l in logics:
        total_hits = 0
        for i in range(1, 11): # 往回模擬 10 期
            past = all_raw[i*20 : i*20 + (limit*20)]
            ans = all_raw[(i-1)*20 : i*20]
            pred = get_prediction_by_logic(past, star, limit, l)
            total_hits += len([n for n in pred if n in ans])
        logic_results.append({"type": l, "hits": total_hits})
    
    # 按命中數排序：第 1 名為冠軍，第 2 名為亞軍
    sorted_res = sorted(logic_results, key=lambda x: x['hits'], reverse=True)
    return sorted_res[0]['type'], sorted_res[1]['type']

# --- [3. 網頁抓取功能] ---
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
        driver.quit()
        return [int(n) for n in matches if 1 <= int(n) <= 80]
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return []

# --- [4. 側邊欄設定] ---
st.sidebar.header("⚙️ AI 參數設定")
star_count = st.sidebar.slider("預測星數", 1, 10, 2)
analysis_range = st.sidebar.slider("分析樣本數", 100, 2000, 300, 100) # 預設改 300 較穩

if st.sidebar.button("🗑️ 清空歷史紀錄"):
    st.session_state.history = []
    st.session_state.last_draw_data = []
    st.rerun()

# --- [5. 主執行區] ---
col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 啟動雙重預測 (針對下一期)"):
        with st.spinner('AI 正在進行多策略模擬考...'):
            all_raw = fetch_data()
            if all_raw:
                # A. 自動進化：找出冠亞軍策略
                best, second = run_strategy_sim(all_raw, star_count, analysis_range)
                
                # B. 產出號碼
                pred_1 = get_prediction_by_logic(all_raw, star_count, analysis_range, best)
                pred_2 = get_prediction_by_logic(all_raw, star_count, analysis_range, second)
                
                now_t = get_taipei_time().strftime("%H:%M:%S")
                
                # C. 存入紀錄
                st.session_state.history.insert(0, {
                    "時間": now_t,
                    "主推(🥇)": f"{best}: {pred_1}",
                    "副推(🥈)": f"{second}: {pred_2}",
                    "中獎結果": "等待開獎...",
                    "raw_pred1": pred_1, # 隱藏欄位供自動對獎
                    "raw_pred2": pred_2
                })
                
                st.success(f"✅ AI 策略評估完成！當前強勢策略：{best}")
                
                # D. LINE 推播
                try:
                    line_bot_api = LineBotApi(LINE_TOKEN)
                    msg = f"\n🎯 AI 雙重推薦\n🥇 主({best})：{pred_1}\n🥈 副({second})：{pred_2}\n⏰：{now_t}"
                    for uid in USER_IDS: line_bot_api.push_message(uid, TextSendMessage(text=msg))
                except: pass

with col2:
    if st.button("🔄 更新對獎狀態"):
        all_raw = fetch_data()
        current_20 = sorted(all_raw[:20]) if all_raw else []
        if current_20:
            st.session_state.last_draw_data = current_20
            for record in st.session_state.history:
                if record["中獎結果"] == "等待開獎...":
                    h1 = [n for n in record["raw_pred1"] if n in current_20]
                    h2 = [n for n in record["raw_pred2"] if n in current_20]
                    record["中獎結果"] = f"🥇中{len(h1)} | 🥈中{len(h2)}"
            st.rerun()

# --- [6. 數據顯示區] ---
st.markdown("---")
if st.session_state.last_draw_data:
    st.subheader(f"📟 最新開獎：{st.session_state.last_draw_data}")

if st.session_state.history:
    df = pd.DataFrame(st.session_state.history)
    # 只顯示使用者需要看的欄位
    display_cols = ["時間", "主推(🥇)", "副推(🥈)", "中獎結果"]
    st.dataframe(df[display_cols], use_container_width=True)
else:
    st.info("💡 尚未有預測紀錄。請按下『啟動雙重預測』。")
