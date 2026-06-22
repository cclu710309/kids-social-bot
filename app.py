import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import base64
import re
import tempfile

# --- 🛠️ 影像處理核心：防裁切模糊填補 ---
def add_blur_padding(img, target_ratio=4/5):
    """
    將照片填補為目標比例 (預設 4:5)，使用原圖模糊作為背景
    """
    img = img.convert("RGB") # 確保色彩模式正確
    img_w, img_h = img.size
    img_ratio = img_w / img_h

    # 如果比例已經非常接近 4:5，就不做任何處理
    if abs(img_ratio - target_ratio) < 0.01:
        return img

    # 計算目標畫布大小
    if img_ratio > target_ratio:
        # 照片比較寬 -> 需補上下邊 (寬度不變，增加高度)
        target_w = img_w
        target_h = int(img_w / target_ratio)
    else:
        # 照片比較高 -> 需補左右邊 (高度不變，增加寬度)
        target_h = img_h
        target_w = int(img_h * target_ratio)

    # 1. 製作背景：將原圖放大並裁切至填滿目標畫布
    bg = ImageOps.fit(img, (target_w, target_h), method=Image.Resampling.LANCZOS)
    # 2. 加上高斯模糊效果 (數值越大越模糊)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    
    # 3. 將原圖貼回正中央
    offset_x = (target_w - img_w) // 2
    offset_y = (target_h - img_h) // 2
    bg.paste(img, (offset_x, offset_y))
    
    return bg

# --- 頁面設定 (瀏覽器分頁圖示) ---
if os.path.exists("logo.png"):
    logo_img = Image.open("logo.png")
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon=logo_img, layout="wide")
else:
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

# --- 🚀 核心優化：一鍵重置機制 ---
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

st.markdown("上傳活動照片或單一影片，設定風格，一鍵產出雙平台文案與完美排版照片。")

# --- 系統設定區 (獨立出來，不參與重置) ---
st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")
api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password")
if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")

# --- 參數設定區 (綁定重置計數器) ---
st.markdown("---")
st.subheader("📝 步驟 2：活動資訊與貼文定調")
col1, col2 = st.columns(2)

with col1:
    keywords = st.text_area("🔑 活動關鍵字 / 描述", placeholder="例如：萬聖節、不怕跌倒、中秋吃柚子...", key=f"keywords_{st.session_state.reset_counter}")
    post_type = st.radio("📌 貼文類型", ["日常紀錄", "節慶活動", "體能/戶外", "園所公告"], horizontal=True, key=f"post_type_{st.session_state.reset_counter}")
    perspective = st.radio("👁️ 敘事視角", ["老師視角", "孩子視角", "旁觀者視角"], horizontal=True, key=f"perspective_{st.session_state.reset_counter}")
    text_length = st.radio("⚡ 文字長度", ["一句話入魂 (極度精簡)", "單詞標籤 (僅詞彙堆疊)", "微故事 (簡短敘述)"], horizontal=True, key=f"text_length_{st.session_state.reset_counter}")

with col2:
    tone = st.multiselect("🎨 語氣與氛圍 (可複選)", ["溫馨親切", "活潑逗趣", "專業信賴", "夢幻童話", "陽光正能量"], default=["溫馨親切"], key=f"tone_{st.session_state.reset_counter}")
    edu = st.multiselect("💡 教育理念 (可複選)", ["生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"], key=f"edu_{st.session_state.reset_counter}")
    cta = st.multiselect("🎯 互動目標 (可複選)", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"], key=f"cta_{st.session_state.reset_counter}")

# --- 模式與檔案上傳區 (綁定重置計數器) ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
upload_mode = st.radio("選擇您要上傳的素材類型：", ["🖼️ 多張活動照片 (AI 自動嚴選 10 張)", "🎥 單一活動影片 (AI 生成短影音文案)"], horizontal=True, key=f"upload_mode_{st.session_state.reset_counter}")

uploaded_files = None
uploaded_video = None
enable_blur = False

if "多張活動照片" in upload_mode:
    # ✨ 新增防裁切開關 (預設開啟)
    enable_blur = st.toggle("✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)", value=True, key=f"blur_{st.session_state.reset_counter}")
    if enable_blur:
        st.info("💡 提示：開啟此功能後，照片存進手機丟到 Meta Business Suite 時，保證不會被裁掉任何畫面！(若關閉則維持原圖比例)")

    uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")
    if uploaded_files:
        st.success(f"已成功接收 {len(uploaded_files)} 張照片！")
else:
    uploaded_video = st.file_uploader("請上傳一段活動影片", type=['mp4', 'mov', 'avi', 'mkv'], accept_multiple_files=False, key=f"video_{st.session_state.reset_counter}")
    if uploaded_video:
        st.success("🎥 影片上傳成功！網頁端僅做預覽與 AI 分析，不需要重複下載。")
        st.video(uploaded_video)

# --- 執行與操作按鈕區 ---
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])

with btn_col1:
    generate_btn = st.button("✨ 步驟 4：一鍵分析並產出社群貼文", use_container_width=True, type="primary")

with btn_col2:
    if st.button("🔄 一鍵清空 / 開始下一篇", use_container_width=True):
        st.session_state.reset_counter += 1
        st.rerun()

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
                
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in ["models/gemini-2.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-1.5-flash"] if m in available_models), available_models[0])
                model = genai.GenerativeModel(target_model) 

                # --- 模式 1：多張照片處理邏輯 ---
                if "多張活動照片" in upload_mode:
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編。我上傳了 {len(uploaded_files)} 張照片。
                    請嚴格遵守以下指示分析照片並完成任務：
                    - 關鍵字：{keywords} / 類型：{post_type} / 語氣：{', '.join(tone)}
                    【任務 1：IG 智能挑圖 - 嚴格篩選多樣性】
                    1. 如果大於等於 10 張，請精選出「剛好 10 張」。避免重複人物過多，混合不同視角。
                    2. 必須在最開頭使用暗號格式：[SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]
                    【任務 2：撰寫雙平台文案】
                    === IG 挑圖建議 ===
                    === IG 貼文 ===
                    (符合 {text_length} 限制，含 #小鳥幼兒園 標籤)
                    === FB 貼文 ===
                    (包含 {', '.join(cta)}，結尾同步 IG 標籤)
                    """

                    image_parts = [Image.open(file) for file in uploaded_files]
                    response = model.generate_content([prompt_text] + image_parts)
                    response_text = response.text
                    
                    st.success("🎉 照片文案與挑選皆已順利產出！")
                    
                    match = re.search(r'\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]', response_text, re.DOTALL)
                    if match:
                        st.markdown("### 🏆 AI 嚴選最佳照片")
                        st.info("💡 **手機存圖秘訣**：請直接「長按」下方照片，選擇 **「儲存影像」**。存入手機後，即可直接上傳 Meta Business Suite 排程！")
                        
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
                                # 讀取圖片
                                original_img = Image.open(s_file)
                                
                                # ✨ 判斷是否需要進行「模糊防裁切處理」
                                if enable_blur:
                                    final_img = add_blur_padding(original_img)
                                    caption_text = f"精選第 {idx+1} 張 (已防裁切處理)"
                                else:
                                    final_img = original_img
                                    caption_text = f"精選第 {idx+1} 張 (原圖尺寸)"

                                # 顯示處理後的圖片，供使用者長按下載
                                img_cols[idx % 2].image(final_img, use_container_width=True, caption=caption_text)
                        else:
                            st.warning("系統收到挑選名單，但無法正確解析圖片。")
                    
                    clean_response = re.sub(r'\[SELECTED_IMAGES\].*?\[/SELECTED_IMAGES\]', '', response_text, flags=re.DOTALL).strip()
                    st.markdown("### 📊 文案與詳細建議")
                    st.text_area("您可以直接複製以下全部內容", value=clean_response, height=400)

                # --- 模式 2：單一影片處理邏輯 ---
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_video.name)[1]) as tfile:
                        tfile.write(uploaded_video.read())
                        temp_video_path = tfile.name

                    video_file_ai = genai.upload_file(path=temp_video_path)
                    
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編。請分析影片並依據以下設定撰寫：
                    關鍵字：{keywords} / 語氣：{', '.join(tone)}
                    1. 3 個短影音標題。
                    2. IG 貼文 (含 #小鳥幼兒園)。
                    3. FB 貼文 (含 {', '.join(cta)}，同步 IG 標籤)。
                    4. AI 小編建議 (哪裡最打動家長)。
                    """

                    response = model.generate_content([prompt_text, video_file_ai])
                    response_text = response.text
                    os.remove(temp_video_path)
                    
                    st.success("🎉 影片短影音文案已順利產出！")
                    st.markdown("### 📊 影片文案與標題建議")
                    st.text_area("您可以直接複製以下全部內容", value=response_text, height=400)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}\n\n💡 提示：若持續報錯，請確認您的 API 金鑰是否正確。")
