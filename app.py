# =========================================================================
# 🐦 小鳥幼兒園貼文神器
# Current Version: v3.3.0 (2026.11.17 Build)｜🟣 Claude 協作版
#
# 🧬 開發歷程 (AI 協作夥伴):
#   ├─ v3.0.0 ~ v3.2.0 ── 🔵 Google Gemini 協作開發
#   └─ v3.3.0 起 ──────── 🟣 Anthropic Claude 協作開發 (程式全面健檢後接手)
#
# 📄 變更日誌 (Changelog):
# [2026.11.17] v3.3.0 🟣Claude - 穩定性修復版（健檢後首次進版）：
#                      1. 修正致命 Bug：小於 1024px 的照片（LINE 轉存圖、截圖）會在送出前被關閉，
#                         導致整次產文失敗並誤報「所有備用模型均失敗」。
#                      2. 更新模型防禦鏈：移除已關閉的 gemini-1.5 / 2.0 系列，改為 Gemini 3.x 世代；
#                         並可由 Secrets 的 GEMINI_MODELS 自行調整，未來換模型不必改程式。
#                      3. 遷移 SDK：google-generativeai（已於 2025.11.30 終止支援）→ google-genai。
#                      4. 金鑰防外洩：Secrets 已綁定金鑰時不再放入網頁輸入框（舊版可被開發者工具看到）。
#                      5. 新增「園所通行密碼」入口：在 Secrets 設定 APP_PASSWORD 後，外人無法使用。
#                      6. 智慧錯誤判斷：金鑰錯誤直接提示，不再白白輪詢所有模型。
#                      7. 手機照片自動轉正 (EXIF)，並以 JPEG 草稿解碼降低記憶體高峰（延續 OOM 優化）。
#                      8. AI 挑圖結果自動去重複、上限 10 張。
# [2026.11.05] v3.2.0 🔵Gemini - 記憶體效能大優化 (Linux OOM)：延遲加載、gc 回收、渲染圖上限 1600px。
# [2026.08.18] v3.1.0 🔵Gemini - 主力 AI 引擎升級為 gemini-2.5-flash / gemini-2.0-flash。
# [2026.07.02] v3.0.0 🔵Gemini - 移出影片模式、多樣性挑圖原則、10 張上限、排序直顯。
# =========================================================================

import base64
import gc
import hmac
import os
import re

import streamlit as st
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from PIL import Image, ImageFilter, ImageOps

APP_VERSION = "v3.3.0"
MAX_SELECTED = 10

# 模型防禦鏈（由上而下依序嘗試）。可在 Streamlit Secrets 以 GEMINI_MODELS="a,b,c" 覆寫。
DEFAULT_MODELS = [
    "gemini-3.5-flash",       # 主力：穩定版 (GA)
    "gemini-3.6-flash",       # 次選：較新世代
    "gemini-3.1-flash-lite",  # 省錢備援：速度快、費用低
    "gemini-2.5-flash",       # 舊主力：已排入退役，仍可用時作為最後防線
]


# =========================================================================
# 🔑 安全機制：Streamlit 隱私保險箱自動載入區
# =========================================================================
def get_secret(name, default=""):
  """安全讀取 Secrets；本機沒有 secrets.toml 時不會當機。"""
  try:
    value = st.secrets.get(name, None)
  except Exception:
    value = None
  if value is None:
    value = os.environ.get(name, default)
  return str(value).strip() if value else default


EMBEDDED_API_KEY = get_secret("GEMINI_API_KEY")
APP_PASSWORD = get_secret("APP_PASSWORD")
_custom_models = get_secret("GEMINI_MODELS")
FALLBACK_MODELS = (
    [m.strip() for m in _custom_models.split(",") if m.strip()]
    if _custom_models
    else DEFAULT_MODELS
)


# --- 🛠️ 影像讀取核心：轉正 + 低記憶體解碼 + 完整載入 ---
def load_image(file, max_size):
  """讀取上傳照片並縮到 max_size 以內。

  v3.3.0 修正：舊版小圖會直接回傳「已關閉」的圖片物件而導致失敗。
  這裡一律在 with 區塊內產生一份完整載入的新圖片再回傳。
  """
  file.seek(0)
  with Image.open(file) as im:
    # JPEG 專用：解碼時直接以較小尺寸讀入，大幅降低記憶體高峰
    try:
      im.draft("RGB", (max_size, max_size))
    except Exception:
      pass
    # 依手機 EXIF 方向資訊自動轉正（回傳的是已載入的新圖片）
    img = ImageOps.exif_transpose(im)
  if img.mode != "RGB":
    img = img.convert("RGB")
  img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
  return img


# --- 🛠️ 影像處理核心：防裁切模糊填補 ---
def add_blur_padding(img, target_ratio=4 / 5):
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


# --- 🧠 AI 錯誤分類：哪些錯誤不必再試下一個模型 ---
def is_fatal_error(e):
  """金鑰錯誤 / 權限問題：換模型也沒用，直接停止。"""
  code = getattr(e, "code", None)
  msg = str(e).lower()
  if code in (401, 403):
    return True
  if code == 400 and ("api key" in msg or "api_key" in msg):
    return True
  return False


def parse_selected_indices(raw, total):
  """解析 AI 回傳的序號：去重複、去越界、最多 10 張。"""
  result = []
  for part in re.split(r"[,，\s]+", raw):
    if part.isdigit():
      idx = int(part) - 1
      if 0 <= idx < total and idx not in result:
        result.append(idx)
    if len(result) >= MAX_SELECTED:
      break
  return result


# --- 頁面設定 ---
if os.path.exists("logo.png"):
  st.set_page_config(
      page_title="小鳥幼兒園貼文神器",
      page_icon=Image.open("logo.png"),
      layout="wide",
  )
else:
  st.set_page_config(
      page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide"
  )

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

st.caption(f"版本 {APP_VERSION}｜🟣 Claude 協作版（v3.2.0 以前為 🔵 Gemini 協作）")

# =========================================================================
# 🔒 園所通行密碼（Secrets 有設定 APP_PASSWORD 才會啟用）
# =========================================================================
if APP_PASSWORD and not st.session_state.get("authed", False):
  st.markdown("---")
  st.subheader("🔒 園所內部專用")
  pwd = st.text_input("請輸入園所通行密碼", type="password")
  if pwd:
    if hmac.compare_digest(pwd, APP_PASSWORD):
      st.session_state.authed = True
      st.rerun()
    else:
      st.error("密碼不正確，請再試一次。")
  st.stop()

st.markdown(
    "上傳活動照片，設定風格，一鍵智能嚴選並產出雙平台精美文案。"
)

# --- ⚙️ 步驟 1：系統驗證 ---
st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")

if EMBEDDED_API_KEY:
  # v3.3.0：金鑰只留在伺服器端，不再放進網頁輸入框（避免被開發者工具看到）
  api_key = EMBEDDED_API_KEY
  st.success("✅ 已自動由雲端安全保險箱（Secrets）載入您綁定的 API 金鑰！")
else:
  api_key = st.text_input(
      "🔑 請貼上您的 Google Gemini API Key", type="password"
  )
  if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")

# --- 📝 步驟 2：活動資訊與貼文定調 ---
st.markdown("---")
st.subheader("📝 步驟 2：活動資訊與貼文定調")
col1, col2 = st.columns(2)

with col1:
  keywords = st.text_area(
      "🔑 活動關鍵字 / 描述",
      placeholder="例如：萬聖節、不怕跌倒、中秋吃柚子...",
      key=f"keywords_{st.session_state.reset_counter}",
  )
  post_type = st.radio(
      "📌 貼文類型",
      [
          "日常紀錄",
          "節慶活動",
          "主題教學",
          "藝術活動",
          "幼兒科學",
          "體能/戶外",
          "園所公告",
      ],
      horizontal=True,
      key=f"post_type_{st.session_state.reset_counter}",
  )
  perspective = st.radio(
      "👁️ 敘事視角",
      ["老師視角", "孩子視角", "旁觀者視角"],
      horizontal=True,
      key=f"perspective_{st.session_state.reset_counter}",
  )
  text_length = st.radio(
      "⚡ 文字長度",
      [
          "一句話入魂 (極度精簡)",
          "微故事 (輕量精簡版)",
          "情境對話 (還原現場童言童語)",
      ],
      horizontal=True,
      key=f"text_length_{st.session_state.reset_counter}",
  )

with col2:
  tone = st.multiselect(
      "🎨 語氣與氛圍 (可複選)",
      ["溫馨親切", "活潑逗趣", "專業信賴", "夢幻童話", "陽光正能量"],
      default=["溫馨親切"],
      key=f"tone_{st.session_state.reset_counter}",
  )
  edu = st.multiselect(
      "💡 教育理念 (可複選)",
      [
          "日常生活體驗",
          "生活自理",
          "邏輯與專注力",
          "人際與分享",
          "感覺統合與大肌肉",
          "美感與創造力",
      ],
      key=f"edu_{st.session_state.reset_counter}",
  )
  cta = st.multiselect(
      "🎯 互動目標 (可複選)",
      ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"],
      key=f"cta_{st.session_state.reset_counter}",
  )

# --- 📸 步驟 3：匯入素材與進階設定 ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")

enable_blur = st.toggle(
    "✨ 啟用 IG 防裁切模式：自動補上高級模糊背景 (轉為 4:5 完美比例)",
    value=True,
    key=f"blur_{st.session_state.reset_counter}",
)
uploaded_files = st.file_uploader(
    "請拖曳或從手機相簿選擇多張照片 (數量無上限)",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    key=f"files_{st.session_state.reset_counter}",
)

if uploaded_files:
  st.success(
      f"🎉 已成功接收 {len(uploaded_files)} 張照片！交給 AI"
      " 為您依據多樣性原則精選最佳畫面。"
  )

# --- 🚀 執行與操作按鈕區 ---
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])

with btn_col1:
  generate_btn = st.button(
      "✨ 步驟 4：一鍵分析並產出社群貼文",
      width="stretch",
      type="primary",
  )

with btn_col2:
  if st.button("🔄 一鍵清空 / 開始下一篇", width="stretch"):
    st.session_state.reset_counter += 1
    st.rerun()

# --- 🧠 AI 核心運作邏輯 (v3.3.0 google-genai 新版 SDK) ---
if generate_btn:
  if not api_key:
    st.error("請先在最上方輸入 Gemini API Key！")
  elif not uploaded_files:
    st.error("請至少上傳一張照片！")
  else:
    with st.spinner(
        "系統正在全神貫注分析素材並撰寫精美文案中，請稍候..."
    ):
      try:
        # 新版 SDK：timeout 單位為毫秒（90 秒，多圖分析較保險）
        client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=90_000),
        )

        prompt_text = f"""
                你是小鳥幼兒園的專業社群小編（品牌理念：everythingforkids，特色：自然探索、生活自理）。
                我目前總共上傳了 {len(uploaded_files)} 張照片（第一張序號為 1，以此類推）。

                【核心設定】
                - 關鍵字：{keywords} | 類型：{post_type} | 敘事視角：{perspective}
                - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                【文案長度與風格限制】: 必須嚴格依據您選取的「{text_length}」模式撰寫
                - 一句話入魂 (極度精簡)：最高指導原則——「能用一個詞解決就不用一句話，能用一句話解決就絕對不寫一段話！」字數自然落在 50~60 字以內即可（請勿硬湊字數），保持洗鍊、震撼、直擊人心的風格。
                - 微故事 (輕量精簡版)：總字數嚴格控制在 100~150 字以內，最多拆成 2 到 3 個極短段落。
                - 情境對話 (還原現場童言童語)：直接以引號重現現場對話，字數控制在 150 字以內。

                【核心撰寫原則】
                1. 標籤規範：無論是 FB 或 IG 貼文，文末請務必「空一行」後，加入 6~8 個與照片內容相關的 hashtag（必須強制包含 #小鳥幼兒園 和 #everythingforkids 這兩個標籤）。
                2. 互動克制：貼文內容請以自然敘事為主，絕對不要刻意加入要求家長互動的文字（例如：「大家覺得呢？」），除非上方勾選了明確的互動目標。

                【任務 1：IG 智能挑圖 - 照片選用原則與上限嚴格限制】
                1. 🌟數量限制🌟：如果上傳總數大於 10 張，您「必須且只能」從中精選出「剛好 10 張」最精彩、最值得串成一篇相簿的照片。如果總數小於或等於 10 張，請將上傳的所有序號全部列出。
                2. 🌟多樣性選用原則🌟：在挑選時，必須嚴格避免單一人物重複率過高（不要都是同一個孩子的特寫），強制畫面模式分散（必須包含遠景呈現場景、中景呈現互動、特寫呈現專注表情）。
                3. 您必須在整段回應的「最開頭」，使用以下暗號格式列出您挑選的照片「數字序號」（以半形逗號分隔，不要加任何文字、空格或英文字母），並依建議發文順序排列：
                [SELECTED_IMAGES]1,2,3,4,5,6,7,8,9,10[/SELECTED_IMAGES]

                【任務 2：撰寫雙平台文案】
                請嚴格遵守上方的設定與原則撰寫，並使用以下標籤包裹您的回應，方便系統解析：
                [IG_POST]
                這裡放 IG 貼文內容（含豐富表情符號，文末空一行加上 6~8 個 hashtag）
                [/IG_POST]
                [FB_POST]
                這裡放 FB 貼文內容（文末空一行加上 6~8 個 hashtag）
                [/FB_POST]
                [SUGGESTION]
                這裡放 IG 挑圖建議（簡述這個照片組合最亮眼、最能打動家長的是哪一個畫面或瞬間）
                [/SUGGESTION]
                """

        # 送 API 用的壓縮圖（v3.3.0：修正小圖被提前關閉的 Bug，並自動轉正）
        api_images = [load_image(f, max_size=1024) for f in uploaded_files]
        contents = [prompt_text] + api_images

        response_text = None
        status_text = st.empty()
        error_log = []

        for idx, current_model in enumerate(FALLBACK_MODELS):
          try:
            if idx > 0:
              status_text.warning(
                  f"🔄 正在為您自動嘗試備用模型: {current_model}..."
              )
            response = client.models.generate_content(
                model=current_model, contents=contents
            )
            if response.text:
              response_text = response.text
              status_text.empty()
              break
            error_log.append(f"{current_model}：回傳內容為空")
          except Exception as e:
            if is_fatal_error(e):
              status_text.empty()
              raise Exception(
                  "API 金鑰無效或沒有權限，請到 Google AI Studio 確認金鑰"
                  f"是否正確、是否已啟用。（原始訊息：{e}）"
              )
            error_log.append(f"{current_model}：{e}")
            continue

        # 傳輸完成後立即清除 API 圖片陣列並回收記憶體
        del contents
        del api_images
        gc.collect()

        if not response_text:
          detail = "\n".join(f"• {line}" for line in error_log)
          raise Exception(
              "所有備用模型均嘗試失敗，各模型錯誤如下：\n" + detail
          )

        st.success("🎉 文案與分析皆已順利產出！")

        # 1. 嚴選照片區塊（延遲加載：僅讀取被選中的照片）
        match = re.search(
            r"\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]",
            response_text,
            re.DOTALL,
        )
        if match:
          st.markdown("### 🏆 AI 嚴選最佳照片")
          st.info(
              "💡 **手機存圖秘訣**：請直接「長按」下方您喜歡的照片，選擇"
              " **「儲存影像」** 即可！"
          )

          picked = parse_selected_indices(match.group(1), len(uploaded_files))
          if picked:
            img_cols = st.columns(2)
            for order_idx, file_idx in enumerate(picked):
              # 一次只處理一張，處理完立即釋放，降低記憶體高峰
              original_img = load_image(uploaded_files[file_idx], max_size=1600)
              if enable_blur:
                final_img = add_blur_padding(original_img)
                caption_text = (
                    f"🏆 建議擺在第 {order_idx + 1} 張 (已防裁切處理)"
                )
              else:
                final_img = original_img
                caption_text = f"🏆 建議擺在第 {order_idx + 1} 張 (原圖尺寸)"
              img_cols[order_idx % 2].image(
                  final_img, width="stretch", caption=caption_text
              )
              del original_img, final_img
            gc.collect()

        # 2. 雙平台貼文文案精準拆解
        fb_match = re.search(
            r"\[FB_POST\](.*?)\[/FB_POST\]", response_text, re.DOTALL
        )
        ig_match = re.search(
            r"\[IG_POST\](.*?)\[/IG_POST\]", response_text, re.DOTALL
        )
        sug_match = re.search(
            r"\[SUGGESTION\](.*?)\[/SUGGESTION\]", response_text, re.DOTALL
        )

        fb_text = (
            fb_match.group(1).strip() if fb_match else "FB 貼文生成失敗"
        )
        ig_text = (
            ig_match.group(1).strip() if ig_match else "IG 貼文生成失敗"
        )
        sug_text = (
            sug_match.group(1).strip() if sug_match else "無提供建議"
        )

        st.markdown("---")
        st.markdown("### 📘 Facebook 貼文文案")
        st.text_area(
            "FB 專用格式（已自動整合標籤）",
            value=fb_text,
            height=250,
            key="fb_area",
        )

        st.markdown("### 📸 Instagram 貼文文案")
        st.text_area(
            "IG 專用格式（豐富表情與精準排版）",
            value=ig_text,
            height=250,
            key="ig_area",
        )

        st.markdown("### 💡 AI 小編挑圖建議")
        st.info(sug_text)

        with st.expander("🔍 檢視 AI 原始完整回應 (除錯與備份用)"):
          st.text(response_text)

      except Exception as e:
        st.error(f"系統偵測到錯誤：{e}")
