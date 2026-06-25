import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import base64
import re
import tempfile
import time
import urllib.request
import urllib.error
import json
import mimetypes

# =========================================================================
# 🔑 安全機制：Streamlit 隱私保險箱自動載入區
# =========================================================================
EMBEDDED_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# --- 🛠️ 影像處理核心：防裁切模糊填補 ---
def add_blur_padding(img, target_ratio=4/5):
    img = img.convert("RGB")
    img_w, img_h = img.size
    img_ratio = img_w / img_h
    if abs(img_ratio - target_ratio) < 0.01: return img
    if img_ratio > target_ratio:
        target_w = img_w
        target_h = int(img_w / target_ratio)
    else:
        target_h = img_h
        target_w = int(img_h * target_ratio)
    bg = ImageOps.fit(img, (target_w, target_h), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    offset_x = (target_w - img_w) // 2
    offset_y = (target_h - img_h) // 2
    bg.paste(img, (offset_x, offset_y))
    return bg

# --- 頁面設定 ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon=Image.open("logo.png"), layout="wide")
else:
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

# --- 標題與 Logo 區 ---
if os.path.exists("logo.png"):
    try:
        with open("logo.png", "rb") as f:
            encoded_img = base64.b64encode(f.read()).decode()
        header_html = f"""
        <div style="display: flex; align-items: center; gap: 15px; margin-top: 10px; margin-bottom: 20px;">
            <img src="data:image/png;base64,{encoded_img}" style="width: 60px; height: 60px; object-fit: contain; flex-shrink: 0;">
            <h2 style="margin: 0; font-weight: bold; line-height: 1.3; font-size: 22px;">小鳥幼兒園專屬：AI 社群發文系統</h2>
        </div>
        """
        st.markdown(header_html, unsafe_allow_html=True)
    except Exception:
        st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")
else:
    st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")

st.markdown("上傳活動照片或單一影片，設定風格，一鍵產出雙平台文案。")

# --- ⚙️ 步驟 1：系統驗證 ---
st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")
api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password", value=EMBEDDED_API_KEY)

if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")
else:
    if EMBEDDED_API_KEY:
        st.success("✅ 已自動由雲端安全保險箱（Secrets）載入您綁定的 API 金鑰！")

# --- 📝 步驟 2：活動資訊與貼文定調 ---
st.markdown("---")
st.subheader("📝 步驟 2：活動資訊與貼文定調")
col1, col2 = st.columns(2)

with col1:
    keywords = st.text_area("🔑 活動關鍵字 / 描述", placeholder="例如：萬聖節、不怕跌倒、中秋吃柚子...", key=f"keywords_{st.session_state.reset_counter}")
    post_type = st.radio("📌 貼文類型", ["日常紀錄", "節慶活動", "主題教學", "藝術活動", "幼兒科學", "體能/戶外", "園所公告"], horizontal=True, key=f"post_type_{st.session_state.reset_counter}")
    perspective = st.radio("👁️ 敘事視角", ["老師視角", "孩子視角", "旁觀者視角"], horizontal=True, key=f"perspective_{st.session_state.reset_counter}")
    text_length = st.radio("⚡ 文字長度", ["一句話入魂 (極度精簡)", "微故事 (輕量精簡版)", "情境對話 (還原現場童言童語)"], horizontal=True, key=f"text_length_{st.session_state.reset_counter}")

with col2:
    tone = st.multiselect("🎨 語氣與氛圍 (可複選)", ["溫馨親切", "活潑逗趣", "專業信賴", "夢幻童話", "陽光正能量"], default=["溫馨親切"], key=f"tone_{st.session_state.reset_counter}")
    edu = st.multiselect("💡 教育理念 (可複選)", ["日常生活體驗", "生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"], key=f"edu_{st.session_state.reset_counter}")
    cta = st.multiselect("🎯 互動目標 (可複選)", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"], key=f"cta_{st.session_state.reset_counter}")

# --- 📸 步驟 3：匯入素材與進階設定 ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
uploaded_files = None
enable_blur = False

enable_blur = st.toggle("✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)", value=True, key=f"blur_{st.session_state.reset_counter}")
uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片 (數量無上限)", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")

# --- 🚀 執行與操作按鈕區 ---
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])

with btn_col1:
    generate_btn = st.button("✨ 步驟 4：一鍵分析並產出社群貼文", use_container_width=True, type="primary")

with btn_col2:
    if st.button("🔄 一鍵清空 / 開始下一篇", use_container_width=True):
        st.session_state.reset_counter += 1
        st.rerun()

# --- 🧠 AI 核心運作邏輯 (2026年最新語法適配版) ---
if generate_btn:
    if not api_key:
        st.error("請先在最上方輸入 Gemini API Key！")
    elif not uploaded_files:
        st.error("請至少上傳一張照片！")
    else:
        with st.spinner("系統正在全神貫注分析素材並撰寫精美文案中，請稍候..."):
            try:
                genai.configure(api_key=api_key)
                
                prompt_text = f"""
                你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                我目前總共上傳了 {len(uploaded_files)} 張照片（第一張序號為 1，以此類推）。
                
                【核心設定】
                - 關鍵字：{keywords} | 類型：{post_type} | 敘事視角：{perspective}
                - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                【文案長度與風格限制】: 必須嚴格依據您選取的「{text_length}」模式撰寫
                - 一句話入魂 (極度精簡)：最高指導原則——「能用一個詞解決就不用一句話，能用一句話解決就絕對不寫一段話！」字數嚴格限制在 20~30 字以內，極度洗鍊、震撼、直擊人心。
                - 微故事 (輕量精簡版)：總字數嚴格控制在 100~150 字以內。
                - 情境對話 (還原現場童言童語)：以引號重現現場對話，字數控制在 150 字以內。
                
                【核心撰寫原則】
                1. 標籤規範：無論是 FB 或 IG 貼文，文末請務必「空一行」後，加入 6~8 個與照片內容相關的 hashtag（必須強制包含 #小鳥幼兒園 和 #everythingforkids 這兩個標籤）。
                2. 互動克制：貼文內容請以自然敘事為主，絕對不要刻意加入要求家長互動的文字（例如：「大家覺得呢？」、「快來留言告訴我們」等），除非上方的「互動目標」中有明確勾選相關需求。

                【任務 1：IG 智能挑圖 - 必須從中挑選最多 10 張且嚴格篩選多樣性】
                1. 如果上傳總數大於 10 張，你「必須且只能」從中精選出「剛好 10 張」最精彩的照片。
                2. 🌟防重複機制🌟：避免重複人物過多，強制畫面模式分散（必須包含遠景、中景、特寫）。
                3. 必須在回應最開頭，用此格式列出挑選的照片數字序號：
                [SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]

                【任務 2：撰寫雙平台文案】
                請嚴格遵守上方的【核心設定】與【核心撰寫原則】來撰寫，並使用以下標籤包裝您的回應，方便系統解析：
                [IG_POST]
                這裡放 IG 貼文內容（含豐富表情符號，文末空一行加上 6~8 個 hashtag）
                [/IG_POST]
                [FB_POST]
                這裡放 FB 貼文內容（如果沒有特別要求互動目標，請自然結尾，文末空一行加上 6~8 個 hashtag）
                [/FB_POST]
                [SUGGESTION]
                這裡放 IG 挑圖建議（簡述這個照片組合最亮眼、最能打動家長的是哪一個畫面或瞬間）
                [/SUGGESTION]
                """
                contents = [prompt_text] + [Image.open(file) for file in uploaded_files]
                
                fallback_models = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]
                response_text = None
                status_text = st.empty()
                
                for idx, current_model in enumerate(fallback_models):
                    try:
                        if idx > 0:
                            status_text.warning(f"🔄 正在為您自動嘗試備用模型: {current_model}...")
                        model = genai.GenerativeModel(current_model)
                        response = model.generate_content(contents)
                        response_text = response.text
                        status_text.empty()
                        break
                    except Exception as e:
                        if "503" in str(e) or "UNAVAILABLE" in str(e) or "404" in str(e) or "not found" in str(e).lower():
                            continue
                        else:
                            raise e
                            
                if not response_text:
                    raise Exception("目前所有 Google AI 伺服器皆忙碌中 (503) 或權限錯誤，系統已自動嘗試多種最新模型皆失敗，請稍後再試。")

                # --- 🎨 畫面渲染產出結果 ---
                st.success(f"🎉 文案與分析皆已順利產出！")
                
                match = re.search(r'\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]', response_text, re.DOTALL)
                if match:
                    st.markdown("### 🏆 AI 嚴選最佳照片")
                    st.info("💡 **手機存圖秘訣**：請直接「長按」下方您喜歡的照片，選擇 **「儲存影像」** 即可！")
                    
                    raw_indices = match.group(1).split(',')
                    selected_files = []
                    for idx_str in raw_indices:
                        idx_str = idx_str.strip()
                        if idx_str.isdigit():
                            idx = int(idx_str) - 1
                            if 0 <= idx < len(uploaded_files):
                                selected_files.append(uploaded_files[idx])
                    
                    if selected_files:
                        img_cols = st.columns(2)
                        for idx, s_file in enumerate(selected_files):
                            original_img = Image.open(s_file)
                            if enable_blur:
                                final_img = add_blur_padding(original_img)
                                caption_text = f"精選第 {idx+1} 張 (已防裁切處理)"
                            else:
                                final_img = original_img
                                caption_text = f"精選第 {idx+1} 張 (原圖尺寸)"
                            img_cols[idx % 2].image(final_img, use_container_width=True, caption=caption_text)
                    
                    fb_match = re.search(r'\[FB_POST\](.*?)\[/FB_POST\]', response_text, re.DOTALL)
                    ig_match = re.search(r'\[IG_POST\](.*?)\[/IG_POST\]', response_text, re.DOTALL)
                    sug_match = re.search(r'\[SUGGESTION\](.*?)\[/SUGGESTION\]', response_text, re.DOTALL)
                    
                    fb_text = fb_match.group(1).strip() if fb_match else "FB 貼文生成失敗"
                    ig_text = ig_match.group(1).strip() if ig_match else "IG 貼文生成失敗"
                    sug_text = sug_match.group(1).strip() if sug_match else "無提供建議"
                    
                    st.markdown("---")
                    st.markdown("### 📘 Facebook 貼文文案")
                    st.text_area("FB 專用格式（已加上互動目標）", value=fb_text, height=200, key="fb_area")
                    
                    st.markdown("### 📸 Instagram 貼文文案")
                    st.text_area("IG 專用格式（豐富表情與排版）", value=ig_text, height=200, key="ig_area")
                    
                    st.markdown("### 💡 AI 小編挑圖建議")
                    st.info(sug_text)
                    
                    with st.expander("🔍 檢視 AI 原始完整回應 (除錯用)"):
                        st.text(response_text)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}")
