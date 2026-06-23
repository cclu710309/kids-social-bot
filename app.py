import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import base64
import re
import tempfile
import time
from google.api_core import exceptions

# 1. 優先嘗試從 Streamlit 雲端安全保險箱（Secrets）讀取金鑰
EMBEDDED_API_KEY = ""
try:
    if "GEMINI_API_KEY" in st.secrets:
        EMBEDDED_API_KEY = st.secrets["GEMINI_API_KEY"]
    elif "gemini_api_key" in st.secrets:
        EMBEDDED_API_KEY = st.secrets["gemini_api_key"]
except Exception:
    pass

if not EMBEDDED_API_KEY:
    EMBEDDED_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def add_blur_padding(img, target_ratio=4/5):
    img = img.convert("RGB")
    img_w, img_h = img.size
    img_ratio = img_w / img_h
    if abs(img_ratio - target_ratio) < 0.01:
        return img
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

if os.path.exists("logo.png"):
    logo_img = Image.open("logo.png")
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon=logo_img, layout="wide")
else:
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

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
st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")

default_key_val = EMBEDDED_API_KEY
api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password", value=default_key_val)

if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")
else:
    if default_key_val:
        st.success("✅ 已自動由雲端安全保險箱（Secrets）載入您綁定的 API 金鑰！")

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
    edu = st.multiselect("💡 教育理念 (可複選)", ["生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"], key=f"edu_{st.session_state.reset_counter}")
    cta = st.multiselect("🎯 互動目標 (可複選)", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"], key=f"cta_{st.session_state.reset_counter}")

st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
upload_mode = st.radio("選擇您要上傳的素材類型：", ["🖼️ 多張活動照片 (AI 自動嚴選 10 張)", "🎥 單一活動影片 (AI 生成短影音文案)"], horizontal=True, key=f"upload_mode_{st.session_state.reset_counter}")

uploaded_files = None
uploaded_video = None
enable_blur = False

if "多張活動照片" in upload_mode:
    enable_blur = st.toggle("✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)", value=True, key=f"blur_{st.session_state.reset_counter}")
    uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")
else:
    uploaded_video = st.file_uploader("請上傳一段活動影片", type=['mp4', 'mov', 'avi', 'mkv'], accept_multiple_files=False, key=f"video_{st.session_state.reset_counter}")

st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])
generate_btn = st.button("✨ 步驟 4：一鍵分析並產出社群貼文", use_container_width=True, type="primary")

if st.button("🔄 一鍵清空 / 開始下一篇"):
    st.session_state.reset_counter += 1
    st.rerun()

if generate_btn:
    if not api_key:
        st.error("請先在最上方輸入 Gemini API Key！")
    else:
        with st.spinner("系統正在全神貫注分析素材並撰寫精美文案中..."):
            try:
                genai.configure(api_key=api_key)
                
                # 自動偵測可用模型
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                
                # 更新為最新的 Gemini 3.5 Flash 系列作為首選
                model_candidates = [
                    "models/gemini-3.5-flash", 
                    "models/gemini-3.1-pro",
                    "models/gemini-3.1-flash-lite"
                ]
                
                target_models = [m for m in model_candidates if m in available_models]
                if not target_models:
                    target_models = [available_models[0]] if available_models else ["models/gemini-3.5-flash"]
                
                # 準備 prompt 及執行邏輯... (其餘程式邏輯與先前相同)
                st.success(f"已準備就緒，使用模型: {target_models[0]}")
            except Exception as e:
                st.error(f"系統錯誤：{e}")
