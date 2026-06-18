import streamlit as st
import google.generativeai as genai
from PIL import Image
import os

# --- 頁面設定 (瀏覽器分頁圖示) ---
if os.path.exists("logo.png"):
    logo_img = Image.open("logo.png")
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon=logo_img, layout="wide")
else:
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

# --- 標題與 Logo 區 (左右並排美化版) ---
if os.path.exists("logo.png"):
    # 建立兩欄：左邊放 Logo，右邊放系統標題
    col_logo, col_title = st.columns([1, 6])
    with col_logo:
        st.image("logo.png", use_container_width=True)
    with col_title:
        # 使用 HTML 語法讓標題文字稍微向下對齊，與圓形 Logo 完美並排
        st.markdown("<h2 style='margin-top: 25px; font-weight: bold;'>小鳥幼兒園專屬：AI 社群發文系統</h2>", unsafe_allow_html=True)
else:
    st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")

st.markdown("上傳活動照片，設定風格，一鍵產出雙平台文案與 IG 挑圖建議。")

# --- 系統設定區 ---
st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")
api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password")
if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")

# --- 參數設定區 ---
st.markdown("---")
st.subheader("📝 步驟 2：活動資訊與貼文定調")
col1, col2 = st.columns(2)

with col1:
    keywords = st.text_area("🔑 活動關鍵字 / 描述", placeholder="例如：萬聖節、不怕跌倒、中秋吃柚子...")
    post_type = st.radio("📌 貼文類型", ["日常紀錄", "節慶活動", "體能/戶外", "園所公告"], horizontal=True)
    perspective = st.radio("👁️ 敘事視角", ["老師視角", "孩子視角", "旁觀者視角"], horizontal=True)
    text_length = st.radio("⚡ 文字長度", ["一句話入魂 (極度精簡)", "單詞標籤 (僅詞彙堆疊)", "微故事 (簡短敘述)"], horizontal=True)

with col2:
    tone = st.multiselect("🎨 語氣與氛圍 (可複選)", ["溫馨親切", "活潑逗趣", "專業信賴", "夢幻童話", "陽光正能量"], default=["溫馨親切"])
    edu = st.multiselect("💡 教育理念 (可複選)", ["生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"])
    cta = st.multiselect("🎯 互動目標 (可複選)", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"])

# --- 照片上傳區 ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入照片 (支援多張上傳)")
uploaded_files = st.file_uploader("請拖曳或從手機相簿選擇照片", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)

if uploaded_files:
    st.info(f"已成功接收 {len(uploaded_files)} 張照片！")
    cols = st.columns(min(len(uploaded_files), 5))
    for i, file in enumerate(uploaded_files[:5]):
        cols[i].image(file, use_container_width=True, caption=file.name)
    if len(uploaded_files) > 5:
        st.write(f"...等共 {len(uploaded_files)} 張")

# --- 執行生成 ---
st.markdown("---")
if st.button("✨ 步驟 4：一鍵分析照片並產出貼文", use_container_width=True, type="primary"):
    if not api_key:
        st.error("請先在最上方輸入 Gemini API Key！")
    elif not uploaded_files:
        st.error("請至少上傳一張照片！")
    else:
        with st.spinner("系統正在深度分析照片並撰寫精美文案中，請稍候..."):
            try:
                # 核心修正：配置 API 金鑰
                genai.configure(api_key=api_key)
                
                # 核心修正：直接指定最穩定、支援圖片分析的標準模型，解決 404 錯誤
                model = genai.GenerativeModel('gemini-1.5-flash') 

                prompt_text = f"""
                你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。請分析隨附的 {len(uploaded_files)} 張照片，並依據以下設定完成任務：

                【核心設定】
                - 關鍵字：{keywords}
                - 類型：{post_type} / 視角：{perspective} / 長度：{text_length}
                - 語氣：{', '.join(tone)} / 教育價值：{', '.join(edu)} / 互動目標：{', '.join(cta)}

                【任務 1：IG 智能挑圖】
                目前共 {len(uploaded_files)} 張照片。IG 最多只能放 10 張。
                請從中挑選出最精華、最適合 IG 的 <=10 張照片，並列出它們的「檔案名稱」。

                【任務 2：撰寫雙平台文案】
                請嚴格按照以下格式輸出：
                === IG 挑圖建議 ===
                (列出挑選出的檔案名稱清單，並簡述挑選原因)
                === IG 貼文 ===
                (符合 {text_length} 限制的文案，含 #小鳥幼兒園 等 Hashtag)
                === FB 貼文 ===
                (符合 {text_length} 限制，結尾帶入 {', '.join(cta)} 的互動，不需 Hashtag)
                """

                # 讀取所有上傳的照片檔案
                image_parts = [Image.open(file) for file in uploaded_files]
                
                # 呼叫 AI 送出請求
                response = model.generate_content([prompt_text] + image_parts)
                
                st.success("🎉 文案與挑圖建議皆已順利產出！")
                st.markdown("### 📊 AI 處理結果")
                st.text_area("您可以直接複製以下全部內容", value=response.text, height=400)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}\n\n💡 提示：請確認您的 API 金鑰是否複製完整。若依然報錯，可能需要重新建立一把新的 API Key 再試試看。")
