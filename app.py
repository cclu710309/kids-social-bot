import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import re
from google.api_core import exceptions

# --- 初始化安全金鑰 ---
EMBEDDED_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")
st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")

api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password", value=EMBEDDED_API_KEY)

# --- 參數設定區 ---
col1, col2 = st.columns(2)
with col1:
    keywords = st.text_area("🔑 活動關鍵字 / 描述")
    post_type = st.radio("📌 貼文類型", ["日常紀錄", "節慶活動", "主題教學", "藝術活動", "幼兒科學", "體能/戶外", "園所公告"], horizontal=True)
    perspective = st.radio("👁️ 敘事視角", ["老師視角", "孩子視角", "旁觀者視角"], horizontal=True)
    text_length = st.radio("⚡ 文字長度", ["一句話入魂", "微故事", "情境對話"], horizontal=True)
with col2:
    tone = st.multiselect("🎨 語氣與氛圍", ["溫馨親切", "活潑逗趣", "專業信賴", "夢幻童話", "陽光正能量"], default=["溫馨親切"])
    edu = st.multiselect("💡 教育理念", ["生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"])
    cta = st.multiselect("🎯 互動目標", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"])

uploaded_files = st.file_uploader("請上傳活動照片", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
enable_blur = st.toggle("✨ 啟用 IG 防裁切模式", value=True)

# --- 執行邏輯 ---
if st.button("✨ 一鍵分析並產出社群貼文", type="primary"):
    if not api_key:
        st.error("請輸入 API Key")
    else:
        with st.spinner("系統正在分析素材並撰寫文案..."):
            try:
                genai.configure(api_key=api_key)
                
                # 自動搜尋可用模型
                models = genai.list_models()
                available = [m.name for m in models if "generateContent" in m.supported_generation_methods]
                target_model = next((m for m in ["models/gemini-3.5-flash", "models/gemini-1.5-pro", "models/gemini-1.5-flash"] if any(m in available_m for available_m in available)), available[0])
                
                model = genai.GenerativeModel(target_model)
                
                prompt = f"""你是幼兒園小編。關鍵字：{keywords}，類型：{post_type}，視角：{perspective}，語氣：{tone}，長度：{text_length}。請產出 IG 與 FB 文案。"""
                contents = [prompt]
                if uploaded_files:
                    for f in uploaded_files: contents.append(Image.open(f))
                
                response = model.generate_content(contents)
                st.success(f"產出成功 (模型: {target_model})")
                st.markdown(response.text)
                
            except Exception as e:
                st.error(f"連線錯誤：{e}")
                st.write("💡 提示：請確認您的 API Key 已綁定信用卡。")
