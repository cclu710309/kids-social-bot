import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import base64
import re

# --- 頁面設定 (瀏覽器分頁圖示) ---
if os.path.exists("logo.png"):
    logo_img = Image.open("logo.png")
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon=logo_img, layout="wide")
else:
    st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

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
        cols[i].image(file, use_container_width=True, caption=f"第 {i+1} 張照片")
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

                # 更改 Prompt 指令：強制 AI 用「數字數字」來回傳
                prompt_text = f"""
                你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                我目前總共上傳了 {len(uploaded_files)} 張照片。這些照片是按照順序提供給你的（第一張為 1，第二張為 2，依此類推）。
                
                請分析這些照片，並依據以下設定完成任務：

                【核心設定】
                - 關鍵字：{keywords}
                - 類型：{post_type} / 視角：{perspective} / 長度：{text_length}
                - 語氣：{', '.join(tone)} / 教育價值：{', '.join(edu)} / 互動目標：{', '.join(cta)}

                【任務 1：IG 智能挑圖與排序】
                請從這 {len(uploaded_files)} 張照片中，挑選出最適合發佈的 <=10 張照片。
                你「必須」在整段回應的「最開頭」，使用以下暗號格式列出你挑選的照片「數字序號」（以半形逗號分隔，不要加任何文字或英文字母）：
                [SELECTED_IMAGES]1,3,5,6[/SELECTED_IMAGES]

                【任務 2：撰寫雙平台文案】
                === IG 挑圖建議 ===
                (簡述為什麼挑選這幾張，以及建議的順序)
                === IG 貼文 ===
                (符合 {text_length} 限制的文案，含 #小鳥幼兒園 等 Hashtag)
                === FB 貼文 ===
                (符合 {text_length} 限制，結尾帶入 {', '.join(cta)} 的互動，不需 Hashtag)
                """

                image_parts = [Image.open(file) for file in uploaded_files]
                response = model.generate_content([prompt_text] + image_parts)
                response_text = response.text
                
                st.success("🎉 產出成功！")
                
                # 解析 AI 回傳的數字暗號
                match = re.search(r'\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]', response_text, re.DOTALL)
                
                if match:
                    st.markdown("### 🏆 AI 嚴選最佳照片")
                    st.info("💡 **手機存圖秘訣**：請直接「長按」下方您喜歡的照片，選擇 **「儲存影像」**，就能立刻存進手機相簿直接發文囉！")
                    
                    raw_indices = match.group(1).split(',')
                    selected_files = []
                    
                    # 根據數字把原圖撈出來
                    for idx_str in raw_indices:
                        idx_str = idx_str.strip()
                        if idx_str.isdigit():
                            idx = int(idx_str) - 1 # 換算成 Python 索引
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

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}\n\n💡 提示：若持續報錯，請確認您的 API 金鑰是否正確。")
