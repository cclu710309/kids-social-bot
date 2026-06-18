import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import base64
import re
import tempfile

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

st.markdown("上傳活動照片或單一影片，設定風格，一鍵產出雙平台文案。")

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

# 透過動態 key 機制，只要計數器變更，所有欄位就會強制清空回預設值
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
st.subheader("📸 步驟 3：匯入素材")
upload_mode = st.radio("選擇您要上傳的素材類型：", ["🖼️ 多張活動照片 (AI 自動嚴選 10 張)", "🎥 單一活動影片 (AI 生成短影音文案)"], horizontal=True, key=f"upload_mode_{st.session_state.reset_counter}")

uploaded_files = None
uploaded_video = None

if "多張活動照片" in upload_mode:
    uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")
    if uploaded_files:
        st.info(f"已成功接收 {len(uploaded_files)} 張照片！")
        cols = st.columns(min(len(uploaded_files), 5))
        for i, file in enumerate(uploaded_files[:5]):
            cols[i].image(file, use_container_width=True, caption=f"第 {i+1} 張照片")
        if len(uploaded_files) > 5:
            st.write(f"...等共 {len(uploaded_files)} 張")
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
    # 點擊此按鈕，更動計數器並引發頁面刷新，達成一鍵閃電清空的效果
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
                
                # 自動偵測可用模型
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = None
                for m in ["models/gemini-2.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]:
                    if m in available_models:
                        target_model = m
                        break
                if not target_model:
                    target_model = available_models[0] if available_models else "models/gemini-1.5-flash"

                model = genai.GenerativeModel(target_model) 

                # --- 模式 1：多張照片處理邏輯 ---
                if "多張活動照片" in upload_mode:
                    # ✨ 優化重點：在 Prompt 中加入了「避免重複人、分散畫面模式」的強烈指令
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    我目前總共上傳了 {len(uploaded_files)} 張照片。這些照片是按照順序提供給你的（第一張序號為 1，第二張為 2，依此類推）。
                    
                    請嚴格遵守以下指示分析照片並完成任務：

                    【核心設定】
                    - 關鍵字：{keywords}
                    - 類型：{post_type} / 視角：{perspective} / 長度：{text_length}
                    - 语氣：{', '.join(tone)} / 教育價值：{', '.join(edu)} / 互動目標：{', '.join(cta)}

                    【任務 1：IG 智能挑圖 - 必須挑滿 10 張且嚴格篩選多樣性】
                    1. 如果上傳總數大於或等於 10 張，你「必須且只能」從中精選出「剛好 10 張」最精彩的照片。
                    2. **🌟防重複機制🌟：在挑選這 10 張時，必須嚴格遵守以下多樣性準則：**
                       - **避免重複人物過多**：請仔細辨識照片中的人物，盡量避免挑選到多張都是同一個孩子的單獨特寫，或者是好幾張非常雷同的同一組孩子的集體照。要讓更多不同的孩子出現在貼文中。
                       - **畫面模式分散**：強制挑選不同視角的照片模式。請混合挑選：遠景（呈現整體氛圍）、中景（小組互動）、特寫（孩子專注的表情或小手實作）。盡量分散挑選不同的活動位置或不同的視角。
                    3. 你「必須」在整段回應的「最開頭」，使用以下暗號格式列出你挑選的照片「數字序號」（以半形逗號分隔，不要加任何文字、空格或英文字母）：
                    [SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]

                    【任務 2：撰寫雙平台文案】
                    === IG 挑圖建議 ===
                    (簡述為什麼精選這 10 張，描述你如何挑選不同人物與不同視角的畫面，以及建議的順序)
                    === IG 貼文 ===
                    (符合 {text_length} 限制的文案，含 #小鳥幼兒園 等相關社群標籤)
                    === FB 貼文 ===
                    (符合 {text_length} 限制，結尾帶入 {', '.join(cta)} 的互動。請比照 IG 貼文，在 FB 文案結尾同步加上一模一樣的社群 Hashtag 標籤，必須包含 #小鳥幼兒園)
                    """

                    image_parts = [Image.open(file) for file in uploaded_files]
                    response = model.generate_content([prompt_text] + image_parts)
                    response_text = response.text
                    
                    st.success("🎉 照片文案與挑選皆已順利產出！")
                    
                    match = re.search(r'\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]', response_text, re.DOTALL)
                    if match:
                        st.markdown("### 🏆 AI 嚴選最佳照片")
                        st.info("💡 **手機存圖秘訣**：請直接「長按」下方您喜歡的照片，選擇 **「儲存影像」**，就能立刻存進手機相簿直接發文囉！")
                        
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
                                img_cols[idx % 2].image(s_file, use_container_width=True, caption=f"精選第 {idx+1} 張")
                        else:
                            st.warning("系統收到挑選名單，但無法正確解析圖片，請參考下方文字建議。")
                    
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
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    請觀看並深度分析這段活動影片，並依據以下設定為雙平台（IG Reels / FB 影片）撰寫吸睛的文案：

                    【核心設定】
                    - 關鍵字：{keywords}
                    - 類型：{post_type} / 視角：{perspective} / 長度：{text_length}
                    - 語氣：{', '.join(tone)} / 教育價值：{', '.join(edu)} / 互動目標：{', '.join(cta)}

                    【任務要求】
                    1. 幫影片想 3 個吸睛的「短影音標題（大標）」。
                    2. 撰寫【IG 貼文文案】，必須符合 {text_length} 限制，帶有豐富的表情符號，並加上 #小鳥幼兒園 等相關社群標籤。
                    3. 撰寫【FB 貼文文案】，必須符合 {text_length} 限制，結尾帶入 {', '.join(cta)} 的互動，並且必須比照 IG，在結尾同步加上一模一樣的社群 Hashtag（需含 #小鳥幼兒園）。
                    4. 附帶一個【AI 小編建議】，簡述這個影片最亮眼、最能打動家長的是哪一個畫面或瞬間。
                    """

                    response = model.generate_content([prompt_text, video_file_ai])
                    response_text = response.text
                    
                    os.remove(temp_video_path)
                    
                    st.success("🎉 影片短影音文案已順利產出！")
                    st.markdown("### 📊 影片文案與標題建議")
                    st.text_area("您可以直接複製以下全部內容", value=response_text, height=400)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}\n\n💡 提示：若持續報錯，請確認您的 API 金鑰是否正確。")
