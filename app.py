import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import base64
import re
import tempfile
import time
from google.api_core import exceptions

# --- 1. 🔑 安全機制：隱私保險箱自動載入 ---
EMBEDDED_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# --- 2. 🛠️ 影像處理核心：防裁切模糊填補 ---
def add_blur_padding(img, target_ratio=4/5):
    img = img.convert("RGB")
    img_w, img_h = img.size
    img_ratio = img_w / img_h
    if abs(img_ratio - target_ratio) < 0.01: return img
    if img_ratio > target_ratio:
        target_w, target_h = img_w, int(img_w / target_ratio)
    else:
        target_h, target_w = img_h, int(img_h * target_ratio)
    bg = ImageOps.fit(img, (target_w, target_h), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    offset_x, offset_y = (target_w - img_w) // 2, (target_h - img_h) // 2
    bg.paste(img, (offset_x, offset_y))
    return bg

# --- 3. 頁面配置與 UI ---
st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

# 🌟 一鍵重置機制 (核心)
if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")
st.markdown("上傳活動照片或單一影片，設定風格，一鍵產出雙平台文案。")

st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")
api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password", value=EMBEDDED_API_KEY)
if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")
elif EMBEDDED_API_KEY:
    st.success("✅ 已自動由雲端安全保險箱（Secrets）載入您綁定的 API 金鑰！")

# --- 4. 參數設定區 (綁定 reset_counter 以支援一鍵清除) ---
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

# --- 5. 模式切換與素材上傳區 ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
upload_mode = st.radio("選擇您要上傳的素材類型：", ["🖼️ 多張活動照片 (無上限上傳，AI 自動嚴選 10 張)", "🎥 單一活動影片 (AI 生成短影音文案)"], horizontal=True, key=f"upload_mode_{st.session_state.reset_counter}")

uploaded_files = None
uploaded_video = None
enable_blur = False

if "多張活動照片" in upload_mode:
    enable_blur = st.toggle("✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)", value=True, key=f"blur_{st.session_state.reset_counter}")
    uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")
    if uploaded_files:
        st.info(f"已成功接收 {len(uploaded_files)} 張照片！交給 AI 為您挑選最佳畫面。")
else:
    uploaded_video = st.file_uploader("請上傳一段活動影片", type=['mp4', 'mov', 'avi', 'mkv'], accept_multiple_files=False, key=f"video_{st.session_state.reset_counter}")
    if uploaded_video:
        st.success("🎥 影片上傳成功！")

# --- 6. 執行與操作按鈕區 ---
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])

with btn_col1:
    generate_btn = st.button("✨ 步驟 4：一鍵分析並產出社群貼文", use_container_width=True, type="primary")

with btn_col2:
    if st.button("🔄 一鍵清空 / 開始下一篇", use_container_width=True):
        st.session_state.reset_counter += 1
        st.rerun()

# --- 7. AI 執行邏輯 ---
if generate_btn:
    if not api_key:
        st.error("請先在最上方輸入 Gemini API Key！")
    elif "多張活動照片" in upload_mode and not uploaded_files:
        st.error("請至少上傳一張照片！")
    elif "單一活動影片" in upload_mode and not uploaded_video:
        st.error("請先上傳影片檔案！")
    else:
        with st.spinner("系統正在全神貫注分析素材並撰寫精美文案中，請稍候..."):
            try:
                genai.configure(api_key=api_key)
                
                # 自動偵測最佳可用模型 (防卡死機制)
                models = genai.list_models()
                available = [m.name for m in models if "generateContent" in m.supported_generation_methods]
                target_model = next((m for m in ["models/gemini-3.5-flash", "models/gemini-1.5-pro", "models/gemini-1.5-flash"] if any(preferred in m for preferred in ["gemini-3.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"] for m in available)), available[0])
                
                model = genai.GenerativeModel(target_model)
                
                if "多張活動照片" in upload_mode:
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    我目前總共上傳了 {len(uploaded_files)} 張照片（第一張序號為 1，以此類推）。
                    
                    【核心設定】
                    - 關鍵字：{keywords} | 類型：{post_type} | 視角：{perspective} | 語氣：{', '.join(tone)}
                    - 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                    【長度與風格】: {text_length}
                    - 一句話入魂：不超過 50 字。
                    - 微故事：100~150 字內，極短段落。
                    - 情境對話：150 字以內，用引號重現現場童言童語。

                    【任務 1：IG 智能挑圖 - 必須挑滿 10 張】
                    如果上傳大於等於 10 張，請嚴格精選剛好 10 張。
                    🌟多樣性準則：避免重複人物過多，畫面模式強制分散（遠景/中景/特寫）。
                    必須在回應最開頭，用此格式列出挑選的數字序號（半形逗號分隔）：
                    [SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]

                    【任務 2：雙平台文案】
                    === IG 挑圖建議 ===
                    (說明挑選原因)
                    === IG 貼文 ===
                    (含豐富表情與 #小鳥幼兒園)
                    === FB 貼文 ===
                    (結尾帶入互動目標與 Hashtag)
                    """
                    contents = [prompt_text] + [Image.open(file) for file in uploaded_files]
                else:
                    # 影片模式：暫存並上傳
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_video.name)[1]) as tfile:
                        tfile.write(uploaded_video.read())
                        temp_video_path = tfile.name
                    video_file_ai = genai.upload_file(path=temp_video_path)
                    
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編。請深度分析這段影片並撰寫文案：
                    【核心設定】
                    - 關鍵字：{keywords} | 類型：{post_type} | 視角：{perspective} | 語氣：{', '.join(tone)}
                    - 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}
                    
                    【長度與風格】: {text_length} (嚴格控制字數)

                    【任務要求】
                    1. 提供 3 個吸睛的短影音標題。
                    2. 撰寫 IG 與 FB 雙平台文案（符合字數限制，含 #小鳥幼兒園）。
                    3. 提供【AI 小編建議】，簡述影片中最打動家長的瞬間。
                    """
                    contents = [prompt_text, video_file_ai]

                # 呼叫模型
                response = model.generate_content(contents)
                
                if "單一活動影片" in upload_mode and 'temp_video_path' in locals():
                    os.remove(temp_video_path)

                # --- 8. 渲染產出結果 ---
                st.success(f"🎉 產出成功！(使用模型: {target_model})")
                
                if "多張活動照片" in upload_mode:
                    match = re.search(r'\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]', response.text, re.DOTALL)
                    if match:
                        st.markdown("### 🏆 AI 嚴選最佳照片")
                        st.info("💡 **手機存圖秘訣**：請直接「長按」下方照片，選擇 **「儲存影像」** 即可發文！")
                        
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
                        else:
                            st.warning("系統收到挑選名單，但無法正確解析圖片。")
                    
                    clean_response = re.sub(r'\[SELECTED_IMAGES\].*?\[/SELECTED_IMAGES\]', '', response.text, flags=re.DOTALL).strip()
                    st.markdown("### 📊 文案與詳細建議")
                    st.text_area("您可以直接複製以下全部內容", value=clean_response, height=400)
                else:
                    st.markdown("### 📊 影片文案與標題建議")
                    st.text_area("您可以直接複製以下全部內容", value=response.text, height=400)

            except Exception as e:
                st.error(f"系統發生錯誤：{e}")
                st.write("💡 提示：若卡住或連線失敗，請確認 AI Studio 帳單狀態是否正常。")
