import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageFilter, ImageOps
import os
import base64
import re
import tempfile
import time

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
    edu = st.multiselect("💡 教育理念 (可複選)", ["生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"], key=f"edu_{st.session_state.reset_counter}")
    cta = st.multiselect("🎯 互動目標 (可複選)", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"], key=f"cta_{st.session_state.reset_counter}")

# --- 📸 步驟 3：匯入素材與進階設定 ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
target_model_ui = st.selectbox("🤖 AI 模型選擇 (如遇 503 伺服器忙碌錯誤，請切換備用模型)", ["gemini-3.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"], key=f"model_select_{st.session_state.reset_counter}")
upload_mode = st.radio("選擇您要上傳的素材類型：", ["🖼️ 多張活動照片 (無上限上傳，AI 自動嚴選 10 張)", "🎥 單一活動影片 (AI 生成短影音文案)"], horizontal=True, key=f"upload_mode_{st.session_state.reset_counter}")

uploaded_files = None
uploaded_video = None
enable_blur = False

if "多張活動照片" in upload_mode:
    enable_blur = st.toggle("✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)", value=True, key=f"blur_{st.session_state.reset_counter}")
    uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇多張照片 (數量無上限)", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key=f"files_{st.session_state.reset_counter}")
else:
    uploaded_video = st.file_uploader("請上傳一段活動影片", type=['mp4', 'mov', 'avi', 'mkv'], accept_multiple_files=False, key=f"video_{st.session_state.reset_counter}")
    if uploaded_video:
        st.success("🎥 影片上傳成功！")
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

# --- 🧠 AI 核心運作邏輯 (2026年最新語法適配版) ---
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
                target_model = target_model_ui
                
                if "多張活動照片" in upload_mode:
                    genai.configure(api_key=api_key)
                    
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    我目前總共上傳了 {len(uploaded_files)} 張照片（第一張序號為 1，以此類推）。
                    
                    【核心設定】
                    - 關鍵字：{keywords} | 類型：{post_type} | 敘事視角：{perspective}
                    - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                    【文案長度與風格限制】: 「{text_length}」
                    - 一句話入魂：不超過 50 字。
                    - 微故事：總字數嚴格控制在 100~150 字以內。
                    - 情境對話：以引號重現現場對話，字數控制在 150 字以內。

                    【任務 1：IG 智能挑圖 - 必須從中挑選最多 10 張且嚴格篩選多樣性】
                    1. 如果上傳總數大於 10 張，你「必須且只能」從中精選出「剛好 10 張」最精彩的照片。
                    2. 🌟防重複機制🌟：避免重複人物過多，強制畫面模式分散（必須包含遠景、中景、特寫）。
                    3. 必須在回應最開頭，用此格式列出挑選的照片數字序號：
                    [SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]

                    【任務 2：撰寫雙平台文案】
                    === IG 挑圖建議 ===
                    === IG 貼文 ===
                    === FB 貼文 ===
                    """
                    contents = [prompt_text] + [Image.open(file) for file in uploaded_files]
                    response = model.generate_content(contents)
                    response_text = response.text
                else:
                    # 影片模式：建立暫存檔案
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_video.name)[1]) as tfile:
                        tfile.write(uploaded_video.read())
                        temp_video_path = tfile.name

                    # 🌟 採用自訂的 REST API 直接上傳，徹底避開 $discovery 阻擋問題
                    import urllib.request
                    import json
                    
                    file_size = os.path.getsize(temp_video_path)
                    url_start = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key.strip()}"
                    req_start = urllib.request.Request(url_start, method="POST")
                    req_start.add_header("X-Goog-Upload-Protocol", "resumable")
                    req_start.add_header("X-Goog-Upload-Command", "start")
                    req_start.add_header("X-Goog-Upload-Header-Content-Length", str(file_size))
                    req_start.add_header("X-Goog-Upload-Header-Content-Type", "video/mp4")
                    req_start.add_header("Content-Type", "application/json")
                    
                    data = json.dumps({"file": {"display_name": os.path.basename(temp_video_path)}}).encode("utf-8")
                    with urllib.request.urlopen(req_start, data=data) as response:
                        upload_url = response.headers.get("X-Goog-Upload-URL")
                    
                    with open(temp_video_path, "rb") as f:
                        file_bytes = f.read()
                        
                    req_up = urllib.request.Request(upload_url, method="POST")
                    req_up.add_header("X-Goog-Upload-Protocol", "resumable")
                    req_up.add_header("X-Goog-Upload-Command", "upload, finalize")
                    req_up.add_header("X-Goog-Upload-Offset", "0")
                    
                    with urllib.request.urlopen(req_up, data=file_bytes) as response:
                        res_data = json.loads(response.read().decode("utf-8"))
                        file_uri = res_data["file"]["uri"]
                        file_name = res_data["file"]["name"]

                    # 等待影片處理完成
                    url_check = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key.strip()}"
                    
                    status_text = st.empty()
                    wait_seconds = 0
                    
                    while True:
                        req_check = urllib.request.Request(url_check, method="GET")
                        with urllib.request.urlopen(req_check) as response:
                            check_data = json.loads(response.read().decode("utf-8"))
                            current_state = check_data.get("state", "UNKNOWN")
                            
                            if current_state == "ACTIVE":
                                status_text.success(f"✅ 影片於 Google 伺服器處理完成！(共等待 {wait_seconds} 秒，開始生成文案...)")
                                break
                            elif current_state == "FAILED":
                                status_text.error("❌ 影片處理失敗，這可能是影片編碼或格式不支援。")
                                raise Exception("影片處理失敗，請嘗試其他影片。")
                            else:
                                status_text.info(f"⏳ Google 伺服器正在逐格分析您的影片... 目前狀態：{current_state} (已等待 {wait_seconds} 秒)")
                                
                        time.sleep(2)
                        wait_seconds += 2
                        
                        if wait_seconds > 600: # 10分鐘超時強制中斷
                            status_text.error("❌ 伺服器處理逾時 (超過10分鐘)，系統自動中斷。")
                            raise Exception("處理逾時，請稍後重試或上傳較短的影片。")
                    
                    # 建立適用於 model.generate_content 的檔案物件
                    import google.ai.generativelanguage as glm
                    video_file_ai = glm.Part(file_data=glm.FileData(mime_type="video/mp4", file_uri=file_uri))
                    
                    prompt_text = f"""
                    你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                    請觀看並深度分析這段活動影片，並依據以下設定為雙平台撰寫吸睛的文案：

                    【核心設定】
                    - 關鍵字：{keywords} | 類型：{post_type} | 敘事視角：{perspective}
                    - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                    【📝 文案長度與風格嚴格限制】: 「{text_length}」
                    - 一句話入魂：總字數不超過 50 字。
                    - 微故事：字數嚴格控制在 100~150 字以內。
                    - 情境對話：重現現場對話，字數同樣控制在 150 字以內。

                    【任務要求】
                    1. 幫影片想 3 個吸睛的「短影音大標題」。
                    2. 撰寫【IG 貼文文案】（含豐富表情符號，並加上 #小鳥幼兒園）。
                    3. 撰寫【FB 貼文文案】（結尾帶入互動目標，並同步加上 #小鳥幼兒園 標籤）。
                    4. 附帶一個【AI 小編建議】，簡述這個影片最亮眼、最能打動家長的是哪一個畫面或瞬間。
                    """
                    
                    # 🌟 採用最新一代完全不經由代理、直接與後台直連的生成指令 (純 REST，保證不卡死)
                    import urllib.error
                    
                    max_retries = 3
                    for attempt in range(max_retries):
                        url_generate = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key.strip()}"
                        payload = {
                            "contents": [{
                                "parts": [
                                    {"text": prompt_text},
                                    {"fileData": {"mimeType": "video/mp4", "fileUri": file_uri}}
                                ]
                            }]
                        }
                        req_generate = urllib.request.Request(url_generate, method="POST")
                        req_generate.add_header("Content-Type", "application/json")
                        
                        try:
                            with urllib.request.urlopen(req_generate, data=json.dumps(payload).encode("utf-8"), timeout=180) as response:
                                gen_data = json.loads(response.read().decode("utf-8"))
                                if "candidates" in gen_data and gen_data["candidates"]:
                                    response_text = gen_data["candidates"][0]["content"]["parts"][0]["text"]
                                    break # 成功
                                else:
                                    response_text = f"生成失敗或被安全機制阻擋。API 回應內容：{gen_data}"
                                    break
                        except urllib.error.HTTPError as e:
                            if e.code == 503:
                                if "gemini-1.5-flash" != target_model:
                                    status_text.warning(f"⚠️ {target_model} 塞車中，系統自動降級至穩定版 gemini-1.5-flash 並重試...")
                                    target_model = "gemini-1.5-flash"
                                    time.sleep(2)
                                    continue
                                elif attempt < max_retries - 1:
                                    status_text.warning("⚠️ 伺服器依然忙碌中，等待 5 秒後自動重試...")
                                    time.sleep(5)
                                    continue
                                else:
                                    error_body = e.read().decode("utf-8")
                                    raise Exception(f"HTTP Error {e.code}: {e.reason} - {error_body}")
                            else:
                                error_body = e.read().decode("utf-8")
                                raise Exception(f"HTTP Error {e.code}: {e.reason} - {error_body}")
                        except Exception as e:
                            raise Exception(f"網路連線錯誤或超時：{e}")
                    else:
                        raise Exception("Google 伺服器目前過載 (多次 503 錯誤)，請稍後再試。")

                    try: os.remove(temp_video_path)
                    except: pass

                # --- 🎨 畫面渲染產出結果 ---
                st.success(f"🎉 文案與分析皆已順利產出！")
                
                if "多張活動照片" in upload_mode:
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
                    
                    clean_response = re.sub(r'\[SELECTED_IMAGES\].*?\[/SELECTED_IMAGES\]', '', response_text, flags=re.DOTALL).strip()
                    st.markdown("### 📊 文案與詳細建議")
                    st.text_area("您可以直接複製以下全部內容", value=clean_response, height=400)
                else:
                    st.markdown("### 📊 影片文案與標題建議")
                    st.text_area("您可以直接複製以下全部內容", value=response_text, height=400)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}")
