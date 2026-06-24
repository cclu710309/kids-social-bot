import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import base64
import re
import tempfile
import time
from google.api_core import exceptions

# =========================================================================
# 🔑 安全機制：Streamlit 隱私保險箱自動載入區
# =========================================================================
EMBEDDED_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# --- 🛠️ 影像處理核心：防裁切模糊填補 ---
def add_blur_padding(img, target_ratio=4/5):
    """
    將照片填補為目標比例 (預設 4:5)，使用原圖模糊作為背景，防範手機丟 IG 被裁切
    """
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

    # 製作高級高斯模糊背景
    bg = ImageOps.fit(img, (target_w, target_h), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    
    # 將原圖貼回正中央
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

# --- 🚀 核心一鍵重置機制變數 ---
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
        st.title("🐦 小鳥幼兒園專專屬：AI 社群發文系統")
else:
    st.title("🐦 小鳥幼兒園專專屬：AI 社群發文系統")

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

# --- 📝 步驟 2：活動資訊與貼文定調 (綁定重置計數器) ---
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

# --- 📸 步驟 3：匯入素材與進階設定 (功能完整回歸) ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
upload_mode = st.radio("選擇您要上傳的素材類型：", ["🖼️ 多張活動照片 (無上限上傳，AI 自動嚴選 10 張)", "🎥 單一活動影片 (AI 生成短影音文案)"], horizontal=True, key=f"upload_mode_{st.session_state.reset_counter}")

uploaded_files = None
uploaded_video = None
enable_blur = False

if "多張活動照片" in upload_mode:
    enable_blur = st.toggle("✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)", value=True, key=f"blur_{st.session_state.reset_counter}")
    if enable_blur:
        st.info("💡 提示：開啟此功能後，挑中的照片會自動轉為 4:5 比例背景模糊，長按即可儲存發文！")

    uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片 (數量無上限)", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")
    if uploaded_files:
        st.info(f"已成功接收 {len(uploaded_files)} 張照片！交給 AI 為您依據多樣性原則精選最佳畫面。")
else:
    uploaded_video = st.file_uploader("請上傳一段活動影片", type=['mp4', 'mov', 'avi', 'mkv'], accept_multiple_files=False, key=f"video_{st.session_state.reset_counter}")
    if uploaded_video:
        st.success("🎥 影片上傳成功！網頁端會將影片傳輸給 Google AI 進行畫面分析。")
        st.video(uploaded_video)

# --- 🚀 執行與操作按鈕區 ---
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])

with btn_col1:
    generate_btn = st.button("✨ 步驟 4：一鍵分析並產出社群貼文", use_container_width=True, type="primary")

with btn_col2:
    if st.button("🔄 一鍵清空 / 開始下一篇", use_container_width=True):
        st.session_state.reset_counter += 1
        st.rerun()

# --- 🧠 AI 核心運作邏輯（整合穩定性與所有挑圖暗號機制） ---
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
                
                # ⚙️ 核心防卡死機制：動態列出當前對接成功的模型群
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                
                # 依序匹配最優模型名稱（解決 3.5 名稱對接問題）
                model_candidates = [
                    "models/gemini-2.5-flash", 
                    "models/gemini-1.5-flash-latest",
                    "models/gemini-1.5-flash", 
                    "models/gemini-1.5-pro"
                ]
                
                target_models = [m for m in model_candidates if m in available_models]
                if not target_models:
                    target_models = [available_models[0]] if available_models else ["models/gemini-1.5-flash"]
                
                response_text = None
                success_model = None
                
                # 建立傳遞物件
                if "多張活動照片" in upload_mode:
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    我目前總共上傳了 {len(uploaded_files)} 張照片。這些照片是按照順序提供給你的（第一張序號為 1，第二張為 2，依此類推）。
                    
                    請嚴格遵守以下指示分析照片並完成任務：

                    【核心設定】
                    - 關鍵字：{keywords} | 類型：{post_type} | 敘事視角：{perspective}
                    - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                    【📝 文案長度與風格嚴格限制】
                    目前的長度設定為：「{text_length}」。請你「務必」遵守以下對應的排版與字數規則：
                    - 如果是「一句話入魂 (極度精簡)」：用最溫馨或有重點的一兩句話帶出，總字數不超過 50 字。
                    - 如果是「微故事 (輕量精簡版)」：內容必須非常精簡，最多拆成 2 到 3 個極短段落，總字數嚴格控制在 100~150 字以內。
                    - 如果是「情境對話 (還原現場童言童語)」：直接以引號重現現場對話（例如：👦孩子：「...」 👩老師：「...」），字數控制在 150 字以內。

                    【任務 1：IG 智能挑圖 - 必須從中挑選最多 10 張且嚴格篩選多樣性】
                    1. 如果上傳總數大於 10 張，你「必須且只能」從中精選出「剛好 10 張」最精彩的照片。如果小於 10 張，請將上傳的所有序號全部列出。
                    2. 🌟防重複機制🌟：在挑選照片時，必須嚴格遵守多樣性準則：避免重複人物過多（不要都是同一個孩子的特寫），強制畫面模式分散（必須包含遠景呈現場景、中景呈現互動、特寫呈現專注表情）。
                    3. 你「必須」在整段回應的「最開頭」，使用以下暗號格式列出你挑選的照片「數字序號」（以半形逗號分隔，不要加任何文字、空格或英文字母）：
                    [SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]

                    【任務 2：撰寫雙平台文案】
                    === IG 挑圖建議 ===
                    (簡述為什麼精選這些照片，描述你如何挑選不同人物與不同視角的畫面，以及建議的順序)
                    === IG 貼文 ===
                    (符合設定長度限制的文案，含豐富 Emoji 表情與 #小鳥幼兒園 等相關社群標籤)
                    === FB 貼文 ===
                    (符合設定長度限制，結尾帶入設定的互動目標，並同步加上一模一樣的 Hashtag，包含 #小鳥幼兒園)
                    """
                    contents = [prompt_text] + [Image.open(file) for file in uploaded_files]
                else:
                    # 影片模式：暫存並上傳分析
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_video.name)[1]) as tfile:
                        tfile.write(uploaded_video.read())
                        temp_video_path = tfile.name

                    video_file_ai = genai.upload_file(path=temp_video_path)
                    
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    請觀看並深度分析這段活動影片，並依據以下設定為雙平台撰寫吸睛的文案：

                    【核心設定】
                    - 關鍵字：{keywords} | 類型：{post_type} | 敘事視角：{perspective}
                    - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                    【📝 文案長度與風格嚴格限制】
                    目前的長度設定為：「{text_length}」。請你「務必」遵守字數規則：
                    - 一句話入魂：總字數不超過 50 字。
                    - 微故事：內容非常精簡，拆成 2 到 3 個極短段落，字數嚴格控制在 100~150 字以內。
                    - 情境對話：重現現場對話，字數同樣控制在 150 字以內。

                    【任務要求】
                    1. 幫影片想 3 個吸睛的「短影音標題（大標）」。
                    2. 撰寫【IG 貼文文案】，必須符合上述設定長度限制，帶有豐富表情符號，並加上 #小鳥幼兒園。
                    3. 撰寫【FB 貼文文案】，必須符合上述設定長度限制，結尾帶入互動目標，並同步加上 #小鳥幼兒園 標籤。
                    4. 附帶一個【AI 小編建議】，簡述這個影片最亮眼、最能打動家長的是哪一個畫面或瞬間。
                    """
                    contents = [prompt_text, video_file_ai]

                # 🏎️ 彈性多模型多階層自動重試調度
                for attempt_model in target_models:
                    model = genai.GenerativeModel(attempt_model)
                    retries = 2
                    for r in range(retries):
                        try:
                            response = model.generate_content(contents)
                            response_text = response.text
                            success_model = attempt_model
                            break
                        except exceptions.ResourceExhausted:
                            if r == retries - 1: break
                            time.sleep(2)
                        except Exception as e:
                            if "not found" in str(e).lower() or "not valid" in str(e).lower():
                                break # 模型不支援或錯誤則跳過換下一個
                            raise e
                    if response_text: break

                if not response_text:
                    raise exceptions.ResourceExhausted("當前調度模型忙碌，請重新點擊一次產出按鈕。")

                # 清理暫存影片
                if "單一活動影片" in upload_mode and 'temp_video_path' in locals():
                    os.remove(temp_video_path)

                # --- 🎨 畫面渲染產出結果 (完美保留暗號解析與網頁長按儲存) ---
                st.success(f"🎉 文案與挑選皆已順利產出！ (本次為您調度的運算模型為: {success_model})")
                
                if "多張活動照片" in upload_mode:
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
                    
                    clean_response = re.sub(r'\[SELECTED_IMAGES\].*?\[/SELECTED_IMAGES\]', '', response_text, flags=re.DOTALL).strip()
                    st.markdown("### 📊 文案與詳細建議")
                    st.text_area("您可以直接複製以下全部內容", value=clean_response, height=400)
                else:
                    st.markdown("### 📊 影片文案與標題建議")
                    st.text_area("您可以直接複製以下全部內容", value=response_text, height=400)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}")
                st.write("💡 提示：請確認您的 API 金鑰已成功至 Streamlit Secrets 後台更新。")
