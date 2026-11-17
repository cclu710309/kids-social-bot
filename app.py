# =========================================================================
# 🐦 小鳥幼兒園貼文神器
# Current Version: v4.1.0 (2026.11.17 Build)｜🟣 Claude 協作版
#
# 🧬 開發歷程 (AI 協作夥伴):
#   ├─ v3.0.0 ~ v3.2.0 ── 🔵 Google Gemini 協作開發
#   └─ v3.3.0 起 ──────── 🟣 Anthropic Claude 協作開發
#
# 📄 變更日誌 (Changelog):
# [2026.11.17] v4.1.0 🟣Claude - 🛡️ 孩子肖像權保護：
#   AI 挑圖時同時標出每張臉的位置（只找「臉在哪」，不辨識「是誰」，不保存任何臉部資料）；
#   老師按照片下方的編號按鈕選擇要遮的臉，或一鍵全部遮住／取消；
#   四種程式繪製貼圖（笑臉、星星、愛心、花朵），每篇可選，預設笑臉；
#   下載 ZIP、存到相簿、長按存圖前，須先勾選「已確認沒有未同意公開的孩子」。
# [2026.11.17] v4.0.0 🟣Claude - 全面升級版（逐項討論定案後一次完成）：
#   🧱 基礎：結果存入 session_state（按任何按鈕都不會消失）；AI 改用 JSON 結構化輸出；
#           第一次分析同時產生「照片內容摘要」。
#   📸 照片：統一輸出 1080×1350；園所 Logo 浮水印（右下、原色 80%、寬 12%，優先放在模糊區）；
#           📦 ZIP 打包下載（電腦）；📲 一次存到手機相簿（手機，試做）。
#   ✍️ 文案：複製框＋「✏️ 我要修改」開關；字數改為「模式決定風格、平台決定長短」；
#           IG/FB 共用 hashtag 最多 5 個（必含 #小鳥幼兒園 #everythingforkids，程式把關）；
#           補齊五大教學特色、台中在地語感與品牌調性。
#   🔁 再給我一版：可只重寫 IG / FB / 兩者；依照片摘要快速重寫；修改方向輸入框；保留最多 5 版。
#   🗂️ 發文歷史：Google 試算表；「✅ 採用這版」才記錄；只存文字不存照片；
#           顯示最近 10 篇，AI 自動參考避免重複。
# [2026.11.17] v3.3.0 🟣Claude - 穩定性修復：小圖致命 Bug、模型鏈換代、SDK 遷移、金鑰防外洩、通行密碼。
# [2026.11.05] v3.2.0 🔵Gemini - 記憶體效能大優化 (Linux OOM)：延遲加載、gc 回收、渲染圖上限 1600px。
# [2026.08.18] v3.1.0 🔵Gemini - 主力 AI 引擎升級為 gemini-2.5-flash / gemini-2.0-flash。
# [2026.07.02] v3.0.0 🔵Gemini - 移出影片模式、多樣性挑圖原則、10 張上限、排序直顯。
# =========================================================================

import base64
import gc
import hmac
import io
import json
import os
import re
import uuid
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from google import genai
from google.genai import types as genai_types
from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel

APP_VERSION = "v4.1.0"
STICKERS = {"笑臉": "smile", "星星": "star", "愛心": "heart", "花朵": "flower"}
MAX_SELECTED = 10
MAX_VERSIONS = 5
MAX_HASHTAGS = 5
BRAND_TAGS = ["#小鳥幼兒園", "#everythingforkids"]
OUT_W, OUT_H = 1080, 1350  # IG 直式 4:5 標準尺寸
TZ = ZoneInfo("Asia/Taipei")

# 模型防禦鏈（由上而下依序嘗試）。可在 Streamlit Secrets 以 GEMINI_MODELS="a,b,c" 覆寫。
DEFAULT_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
]

# 字數規則：模式決定風格、平台決定長短
LENGTH_RULES = {
    "一句話入魂 (極度精簡)": {
        "ig": "30～60 字",
        "fb": "60～100 字",
        "style": "能用一個詞解決就不用一句話，能用一句話解決就絕對不寫一段話；洗鍊、直擊人心，請勿硬湊字數",
    },
    "微故事 (輕量精簡版)": {
        "ig": "80～120 字",
        "fb": "150～250 字",
        "style": "以小故事敘事，最多拆成 2～3 個極短段落",
    },
    "情境對話 (還原現場童言童語)": {
        "ig": "150 字以內",
        "fb": "250 字以內",
        "style": "以引號重現現場童言童語的對話，再用一兩句收尾",
    },
}

BRAND_CONTEXT = """你是小鳥幼兒園的專業社群小編。
【園所資料】小鳥幼兒園，位於台中市西區，招收 2–6 歲幼兒，品牌精神 everythingforkids。
【五大教學特色】自然探索、藝術創作、生活自理、品格教育、主題教學。
【品牌調性】精緻用心、高質感。讀者是台中在地 2–6 歲幼兒的家長，請用貼近台中在地家長的語感。
【文字原則】精簡有力，能一句話說完不說一段，能一個詞說完不說一句；不堆疊形容詞、不說套話；
自然帶入 everythingforkids（一切為了孩子）的精神，但不必每次都直接寫出這個字。"""


# =========================================================================
# 🔑 Secrets 讀取
# =========================================================================
def get_secret(name, default=""):
  try:
    value = st.secrets.get(name, None)
  except Exception:
    value = None
  if value is None:
    value = os.environ.get(name, default)
  return str(value).strip() if value else default


EMBEDDED_API_KEY = get_secret("GEMINI_API_KEY")
APP_PASSWORD = get_secret("APP_PASSWORD")
HISTORY_URL = get_secret("HISTORY_URL")
HISTORY_TOKEN = get_secret("HISTORY_TOKEN")
_custom_models = get_secret("GEMINI_MODELS")
FALLBACK_MODELS = (
    [m.strip() for m in _custom_models.split(",") if m.strip()]
    if _custom_models
    else DEFAULT_MODELS
)


# =========================================================================
# 🧾 AI 回傳格式（JSON 結構化輸出）
# =========================================================================
class FaceBox(BaseModel):
  ymin: int
  xmin: int
  ymax: int
  xmax: int


class PhotoFaces(BaseModel):
  image: int
  faces: list[FaceBox]


class AnalysisResult(BaseModel):
  selected_images: list[int]
  faces: list[PhotoFaces]
  photo_summary: str
  ig_text: str
  fb_text: str
  content_hashtags: list[str]
  suggestion: str


class RewriteResult(BaseModel):
  ig_text: str
  fb_text: str
  content_hashtags: list[str]


# =========================================================================
# 🛠️ 影像處理
# =========================================================================
def load_image(file, max_size):
  """讀取上傳照片：自動轉正、低記憶體解碼、縮到 max_size 以內。"""
  file.seek(0)
  with Image.open(file) as im:
    try:
      im.draft("RGB", (max_size, max_size))
    except Exception:
      pass
    img = ImageOps.exif_transpose(im)
  if img.mode != "RGB":
    img = img.convert("RGB")
  img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
  return img


@st.cache_resource
def load_logo():
  if not os.path.exists("logo.png"):
    return None
  try:
    logo = Image.open("logo.png").convert("RGBA")
    alpha = logo.getchannel("A").point(lambda a: int(a * 0.8))  # 80% 不透明
    logo.putalpha(alpha)
    return logo
  except Exception:
    return None


def compose_post_image(img, blur):
  """回傳 (畫布, 照片所在區域)。模糊模式統一輸出 1080×1350。"""
  w, h = img.size
  if blur:
    if abs(w / h - OUT_W / OUT_H) < 0.01:
      return img.resize((OUT_W, OUT_H), Image.Resampling.LANCZOS), (0, 0, OUT_W, OUT_H)
    bg = ImageOps.fit(img, (OUT_W, OUT_H), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
    scale = min(OUT_W / w, OUT_H / h)
    nw, nh = int(w * scale), int(h * scale)
    fg = img.resize((nw, nh), Image.Resampling.LANCZOS)
    ox, oy = (OUT_W - nw) // 2, (OUT_H - nh) // 2
    bg.paste(fg, (ox, oy))
    return bg, (ox, oy, ox + nw, oy + nh)
  # 原圖比例：寬度統一縮到 1080（小圖不放大）
  if w > OUT_W:
    img = img.resize((OUT_W, int(h * OUT_W / w)), Image.Resampling.LANCZOS)
  return img, (0, 0, img.size[0], img.size[1])


def add_watermark(canvas, photo_box, logo):
  """右下角 Logo；若下方或右側有模糊區，優先放在模糊區內。"""
  W, H = canvas.size
  ratio = logo.size[1] / logo.size[0]
  lw = int(W * 0.12)          # 標準寬度：照片寬 12%
  min_lw = int(W * 0.08)      # 為了塞進模糊區，最多縮到 8%
  margin = int(W * 0.03)
  gap = 12
  bottom_strip = H - photo_box[3]
  right_strip = W - photo_box[2]
  fit_bottom = int((bottom_strip - 2 * gap) / ratio) if bottom_strip > 2 * gap else 0
  fit_right = right_strip - 2 * gap
  if fit_bottom >= min_lw:
    lw = min(lw, fit_bottom)
    lh = int(lw * ratio)
    x, y = W - lw - margin, photo_box[3] + (bottom_strip - lh) // 2
  elif fit_right >= min_lw:
    lw = min(lw, fit_right)
    lh = int(lw * ratio)
    x, y = photo_box[2] + (right_strip - lw) // 2, H - lh - margin
  else:
    lh = int(lw * ratio)
    x, y = W - lw - margin, H - lh - margin
  mark = logo.resize((lw, max(1, lh)), Image.Resampling.LANCZOS)
  out = canvas.convert("RGBA")
  out.alpha_composite(mark, (x, y))
  return out.convert("RGB")


def to_jpeg(img, quality=90):
  buf = io.BytesIO()
  img.save(buf, "JPEG", quality=quality, optimize=True)
  return buf.getvalue()


def make_base_photo(file, blur, face_boxes):
  """產生「尚未遮臉、尚未加 Logo」的底圖，並把 AI 的臉部座標換算到底圖上。"""
  img = load_image(file, max_size=1600)
  canvas, box = compose_post_image(img, blur)
  ox, oy, x2, y2 = box
  pw, ph = x2 - ox, y2 - oy
  faces = []
  for f in face_boxes:
    ymin, xmin, ymax, xmax = (max(0, min(1000, int(v))) for v in f)
    if ymax <= ymin or xmax <= xmin:
      continue
    faces.append((
        ox + xmin * pw // 1000, oy + ymin * ph // 1000,
        ox + xmax * pw // 1000, oy + ymax * ph // 1000,
    ))
  band = max(1, canvas.size[1] // 5)  # 由上到下分成 5 排，每排再由左到右編號
  faces.sort(key=lambda b: (((b[1] + b[3]) // 2) // band, b[0]))
  data = {"base": to_jpeg(canvas, 95), "box": box, "faces": faces}
  del img, canvas
  return data


# --- 🛡️ 遮臉貼圖（程式繪製，不需額外字型）---
def _bezier(p0, p1, p2, p3, n=24):
  pts = []
  for i in range(n + 1):
    t = i / n
    a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
    pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
  return pts


@st.cache_data(show_spinner=False, max_entries=64)
def draw_sticker(kind, size):
  """以 120×120 的設計座標（中心為 0,0）繪製，再縮成 size×size。"""
  from PIL import ImageDraw
  ss = 4
  S = max(8, size) * ss
  k = S / 120.0
  im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
  d = ImageDraw.Draw(im)

  def P(x, y):
    return (S / 2 + x * k, S / 2 + y * k)

  def circle(x, y, r, fill, outline=None, w=0):
    (a, b), (c, e) = P(x - r, y - r), P(x + r, y + r)
    d.ellipse([a, b, c, e], fill=fill, outline=outline, width=int(w * k))

  def ellipse(x, y, rx, ry, fill):
    (a, b), (c, e) = P(x - rx, y - ry), P(x + rx, y + ry)
    d.ellipse([a, b, c, e], fill=fill)

  def smile(x0, y0, cy, x1, color, w):
    pts = [P(*p) for p in _bezier((x0, y0), (x0 * 0.33, cy), (x1 * 0.33, cy), (x1, y0), 16)]
    d.line(pts, fill=color, width=int(w * k), joint="curve")

  brown, amber, gold = "#633806", "#BA7517", "#FAC775"
  if kind == "star":
    pts = [(0, -52), (14, -18), (50, -16), (22, 8), (32, 44), (0, 24),
           (-32, 44), (-22, 8), (-50, -16), (-14, -18)]
    d.polygon([P(*p) for p in pts], fill=gold, outline=amber, width=int(3 * k))
    circle(-9, -2, 3.5, brown)
    circle(9, -2, 3.5, brown)
    smile(-8, 9, 16, 8, brown, 3)
  elif kind == "heart":
    path = (_bezier((0, 44), (-60, 4), (-52, -46), (-22, -46))
            + _bezier((-22, -46), (-8, -46), (0, -36), (0, -28))
            + _bezier((0, -28), (0, -36), (8, -46), (22, -46))
            + _bezier((22, -46), (52, -46), (60, 4), (0, 44)))
    d.polygon([P(*p) for p in path], fill="#ED93B1", outline="#993556", width=int(3 * k))
    circle(-13, -12, 4, "#4B1528")
    circle(13, -12, 4, "#4B1528")
    smile(-9, 0, 9, 9, "#4B1528", 3)
  elif kind == "flower":
    for x, y in ((0, -30), (28.5, -9), (17.6, 24), (-17.6, 24), (-28.5, -9)):
      circle(x, y, 20, "#F4C0D1", "#D4537E", 2.5)
    circle(0, 0, 22, gold, amber, 2.5)
    circle(-7, -4, 3, brown)
    circle(7, -4, 3, brown)
    smile(-7, 6, 12, 7, brown, 2.5)
  else:  # smile
    circle(0, 0, 48, gold, amber, 3)
    ellipse(-16, -10, 5, 8, brown)
    ellipse(16, -10, 5, 8, brown)
    circle(-28, 10, 7, (240, 153, 123, 180))
    circle(28, 10, 7, (240, 153, 123, 180))
    smile(-18, 14, 34, 18, brown, 4)
  return im.resize((size, size), Image.Resampling.LANCZOS)


def apply_covers(canvas, faces, covers, kind):
  out = canvas.convert("RGBA")
  W, H = out.size
  for n in covers:
    if not (1 <= n <= len(faces)):
      continue
    x1, y1, x2, y2 = faces[n - 1]
    size = int(max(x2 - x1, y2 - y1) * 1.35) + 8
    sticker = draw_sticker(kind, size)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    out.alpha_composite(sticker, (max(0, min(W - size, cx - size // 2)),
                                  max(0, min(H - size, cy - size // 2))))
  return out.convert("RGB")


def render_photo(photo, covers, kind, watermark):
  """乾淨成品：遮臉貼圖 + Logo（下載、存相簿、長按用）。"""
  canvas = Image.open(io.BytesIO(photo["base"])).convert("RGB")
  canvas = apply_covers(canvas, photo["faces"], covers, kind)
  logo = load_logo() if watermark else None
  if logo is not None:
    canvas = add_watermark(canvas, photo["box"], logo)
  return to_jpeg(canvas, 90)


def render_preview(final_jpeg, faces, covers, width=540):
  """確認用預覽：在成品上標出每張臉的編號（只在畫面上看，不會被下載）。"""
  from PIL import ImageDraw, ImageFont
  img = Image.open(io.BytesIO(final_jpeg)).convert("RGB")
  scale = width / img.size[0]
  img = img.resize((width, int(img.size[1] * scale)), Image.Resampling.LANCZOS)
  d = ImageDraw.Draw(img)
  try:
    font = ImageFont.load_default(size=16)
  except Exception:
    font = ImageFont.load_default()
  for n, (x1, y1, x2, y2) in enumerate(faces, start=1):
    x1, y1, x2, y2 = (int(v * scale) for v in (x1, y1, x2, y2))
    covered = n in covers
    if not covered:
      d.rectangle([x1, y1, x2, y2], outline="#FFFFFF", width=3)
      d.rectangle([x1 + 2, y1 + 2, x2 - 2, y2 - 2], outline="#BA7517", width=2)
    r = 12
    cx, cy = max(r, x1), max(r, y1)
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill="#3B6D11" if covered else "#BA7517", outline="#FFFFFF", width=2)
    d.text((cx, cy), str(n), fill="#FFFFFF", font=font, anchor="mm")
  return to_jpeg(img, 85)


def safe_name(text, fallback):
  name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", (text or "").strip())
  name = re.sub(r"\s+", "_", name)[:15]
  return name or fallback


def build_zip(images, activity):
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
    for i, data in enumerate(images, start=1):
      zf.writestr(f"{i:02d}_{activity}.jpg", data)
  return buf.getvalue()


SHARE_TEMPLATE = """
<div style="margin:4px 0 8px 0;">
  <button id="btn-__UID__" style="width:100%;padding:10px 14px;border-radius:8px;border:1px solid rgba(128,128,128,.4);
    background:#ff4b4b;color:#fff;font-size:16px;font-weight:600;cursor:pointer;">📲 一次存到手機相簿（__N__ 張）</button>
  <div id="msg-__UID__" style="font-size:13px;margin-top:6px;opacity:.85;"></div>
</div>
<script>
(function () {
  const data = __DATA__;
  const files = data.map(function (d) {
    const bin = atob(d[1]);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new File([arr], d[0], { type: "image/jpeg" });
  });
  const btn = document.getElementById("btn-__UID__");
  const msg = document.getElementById("msg-__UID__");
  if (!btn) return;
  btn.addEventListener("click", async function () {
    if (navigator.canShare && navigator.canShare({ files: files })) {
      try {
        await navigator.share({ files: files });
        msg.textContent = "✅ 已開啟分享選單：iPhone 請選「儲存 __N__ 張影像」，Android 請選存到相簿。";
      } catch (e) {
        if (e.name !== "AbortError") msg.textContent = "⚠️ 無法開啟分享（" + e.message + "），請改用下方長按存圖。";
      }
    } else {
      msg.textContent = "ℹ️ 這個裝置或瀏覽器不支援一次儲存，請改用下方長按存圖，或用電腦下載 ZIP。";
    }
  });
})();
</script>
"""


def share_widget_html(images, activity):
  data = [
      [f"{i:02d}_{activity}.jpg", base64.b64encode(b).decode()]
      for i, b in enumerate(images, start=1)
  ]
  return (
      SHARE_TEMPLATE.replace("__UID__", uuid.uuid4().hex[:8])
      .replace("__N__", str(len(images)))
      .replace("__DATA__", json.dumps(data))
  )


# =========================================================================
# #️⃣ Hashtag 與文案組裝（程式把關：最多 5 個、必含品牌標籤）
# =========================================================================
HASHTAG_ONLY_LINE = re.compile(r"^\s*(#[^\s#]+\s*)+$")


def build_hashtags(content_tags):
  result = list(BRAND_TAGS)
  seen = {t.lower() for t in result}
  for tag in content_tags or []:
    clean = re.sub(r"[\s#＃,，。、!！?？]+", "", str(tag))
    if not clean:
      continue
    full = "#" + clean
    if full.lower() in seen:
      continue
    result.append(full)
    seen.add(full.lower())
    if len(result) >= MAX_HASHTAGS:
      break
  return result


def strip_hashtag_lines(text):
  lines = [l for l in (text or "").strip().splitlines() if not HASHTAG_ONLY_LINE.match(l)]
  return "\n".join(lines).strip()


def compose_post(body, tags):
  return f"{strip_hashtag_lines(body)}\n\n{' '.join(tags)}"


def count_hashtags(text):
  return len(re.findall(r"#[^\s#]+", text or ""))


# =========================================================================
# 🗂️ 發文歷史（Google 試算表 + Apps Script）
# =========================================================================
def history_enabled():
  return bool(HISTORY_URL and HISTORY_TOKEN)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(url, token, n=10):
  try:
    r = requests.get(url, params={"token": token, "n": n}, timeout=20)
    data = r.json()
    if not data.get("ok"):
      return None, data.get("error", "未知錯誤")
    return data.get("rows", []), None
  except Exception as e:
    return None, str(e)


def save_history(payload):
  try:
    body = dict(payload, token=HISTORY_TOKEN)
    r = requests.post(
        HISTORY_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        timeout=30,
    )
    data = r.json()
    if data.get("ok"):
      fetch_history.clear()
      return True, None
    return False, data.get("error", "未知錯誤")
  except Exception as e:
    return False, str(e)


def history_prompt_block(rows):
  if not rows:
    return ""
  lines = []
  for row in rows[:10]:
    row = list(row) + [""] * 8
    date, kw, _ptype, _len, ig, _fb, tags = row[:7]
    first = re.sub(r"\s+", " ", str(ig))[:40]
    lines.append(f"- {str(date)[:10]}｜{kw}｜IG 開頭：{first}｜hashtag：{tags}")
  return (
      "\n【最近已發布的貼文（請避免重複）】\n"
      + "\n".join(lines)
      + "\n請避免重複上述貼文的開頭句型、慣用詞與內容 hashtag（品牌標籤除外），讓每篇都有新鮮感。\n"
  )


# =========================================================================
# 🧠 AI 呼叫（模型防禦鏈 + JSON）
# =========================================================================
def is_fatal_error(e):
  code = getattr(e, "code", None)
  msg = str(e).lower()
  if code in (401, 403):
    return True
  if code == 400 and ("api key" in msg or "api_key" in msg):
    return True
  return False


def call_gemini(api_key, contents, schema, status=None):
  client = genai.Client(
      api_key=api_key, http_options=genai_types.HttpOptions(timeout=90_000)
  )
  config = genai_types.GenerateContentConfig(
      response_mime_type="application/json", response_schema=schema
  )
  errors = []
  for idx, model in enumerate(FALLBACK_MODELS):
    try:
      if idx > 0 and status is not None:
        status.warning(f"🔄 正在為您自動嘗試備用模型: {model}...")
      resp = client.models.generate_content(
          model=model, contents=contents, config=config
      )
      parsed = getattr(resp, "parsed", None)
      if isinstance(parsed, BaseModel):
        data = parsed.model_dump()
      elif resp.text:
        data = schema.model_validate_json(resp.text).model_dump()
      else:
        errors.append(f"{model}：回傳內容為空")
        continue
      if status is not None:
        status.empty()
      return data, resp.text or json.dumps(data, ensure_ascii=False)
    except Exception as e:
      if is_fatal_error(e):
        if status is not None:
          status.empty()
        raise Exception(
            "API 金鑰無效或沒有權限，請到 Google AI Studio 確認金鑰是否正確、"
            f"是否已啟用。（原始訊息：{e}）"
        )
      errors.append(f"{model}：{e}")
  detail = "\n".join(f"• {line}" for line in errors)
  raise Exception("所有備用模型均嘗試失敗，各模型錯誤如下：\n" + detail)


def settings_block(s):
  rule = LENGTH_RULES[s["text_length"]]
  return f"""
【本篇設定】
- 活動關鍵字 / 描述：{s['keywords'] or '（未填寫，請依照片判斷）'}
- 貼文類型：{s['post_type']}｜敘事視角：{s['perspective']}
- 語氣：{'、'.join(s['tone']) or '溫馨親切'}｜教育價值：{'、'.join(s['edu']) or '（不指定）'}
- 互動目標：{'、'.join(s['cta']) or '（無）'}

【文案長度與風格】模式：「{s['text_length']}」——{rule['style']}
- IG 文案：{rule['ig']}，含適量表情符號。
- FB 文案：{rule['fb']}，溫馨敘述，適量表情符號。

【撰寫原則】
1. ig_text、fb_text 只放內文，「不要」寫任何 hashtag（系統會自動加在文末）。
2. content_hashtags：給 3 個與照片內容相關、台灣在地化的 hashtag（例如活動主題、#台中幼兒園 這類），
   不要包含 #小鳥幼兒園、#everythingforkids（系統會自動加入）。IG 規定整篇最多 5 個 hashtag。
3. 互動克制：以自然敘事為主，除非上方有勾選互動目標，否則不要加入「大家覺得呢？」這類要求互動的句子。
"""


def build_analysis_prompt(n_photos, s, history_rows):
  return f"""{BRAND_CONTEXT}
{settings_block(s)}{history_prompt_block(history_rows)}
【任務 1：IG 智能挑圖】目前共上傳 {n_photos} 張照片（第一張序號為 1，以此類推）。
1. 若總數大於 10 張，必須且只能精選「剛好 10 張」；若小於或等於 10 張，列出全部序號。
2. 多樣性原則：避免同一個孩子重複出現太多次；畫面要分散（遠景呈現場景、中景呈現互動、特寫呈現專注表情）。
3. selected_images：依「建議發文順序」排列的照片序號（整數）。

【任務 2：照片內容摘要】photo_summary：用 150～300 字描述入選照片的場景、活動、孩子們在做什麼、
氣氛與亮點（不要猜測孩子的名字）。之後重寫文案時只會參考這段摘要，請寫得具體。

【任務 3：雙平台文案】依上方設定撰寫 ig_text、fb_text、content_hashtags。

【任務 4：挑圖建議】suggestion：簡述這組照片最亮眼、最能打動家長的畫面或瞬間。

【任務 5：臉部位置（肖像權保護用）】faces：對 selected_images 中的「每一張」照片各給一筆，
image 填該照片的原序號，faces 列出照片中所有看得到的人臉位置（孩子與大人都要，包含側臉、
遠處很小的臉、被部分遮住的臉）。座標用 0～1000 的相對位置：ymin、xmin、ymax、xmax。
只要標出位置，不要辨識或猜測是誰。照片中看不到任何臉時，faces 給空陣列。
"""


def build_rewrite_prompt(summary, s, current, target, direction, history_rows):
  target_text = {"both": "IG 與 FB 兩篇", "ig": "IG", "fb": "FB"}[target]
  return f"""{BRAND_CONTEXT}
{settings_block(s)}{history_prompt_block(history_rows)}
【照片內容摘要】
{summary}

【目前版本】
IG：{current['ig_body']}
FB：{current['fb_body']}

【任務】請重寫「{target_text}」文案，寫出跟目前版本明顯不同的新版本（換開頭、換切入角度）。
修改方向：{direction or '（未指定，請自由發揮出不同的寫法）'}
仍請完整回傳 ig_text、fb_text、content_hashtags 三個欄位。
"""


# =========================================================================
# 🧩 版本與狀態
# =========================================================================
def full_text(version, platform):
  edited = version.get(f"{platform}_edit")
  if edited is not None:
    return edited
  return compose_post(version[f"{platform}_body"], version["hashtags"])


def on_edit_change(vid, platform):
  versions = st.session_state.result["versions"]
  versions[vid][f"{platform}_edit"] = st.session_state[f"edit_{platform}_{vid}"]


def snapshot_settings():
  rc = st.session_state.reset_counter
  return {
      "keywords": st.session_state.get(f"keywords_{rc}", ""),
      "post_type": st.session_state.get(f"post_type_{rc}", "日常紀錄"),
      "perspective": st.session_state.get(f"perspective_{rc}", "老師視角"),
      "text_length": st.session_state.get(f"text_length_{rc}", "一句話入魂 (極度精簡)"),
      "tone": st.session_state.get(f"tone_{rc}", ["溫馨親切"]),
      "edu": st.session_state.get(f"edu_{rc}", []),
      "cta": st.session_state.get(f"cta_{rc}", []),
  }


# =========================================================================
# 🖥️ 頁面
# =========================================================================
if os.path.exists("logo.png"):
  st.set_page_config(
      page_title="小鳥幼兒園貼文神器", page_icon=Image.open("logo.png"), layout="wide"
  )
else:
  st.set_page_config(page_title="小鳥幼兒園貼文神器", page_icon="🐦", layout="wide")

if "reset_counter" not in st.session_state:
  st.session_state.reset_counter = 0

if os.path.exists("logo.png"):
  try:
    with open("logo.png", "rb") as f:
      encoded_img = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 15px; margin-top: 10px; margin-bottom: 20px;">
            <img src="data:image/png;base64,{encoded_img}" style="width: 60px; height: 60px; object-fit: contain; flex-shrink: 0;">
            <h2 style="margin: 0; font-weight: bold; line-height: 1.3; font-size: 22px;">小鳥幼兒園專屬：AI 社群發文系統</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )
  except Exception:
    st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")
else:
  st.title("🐦 小鳥幼兒園專屬：AI 社群發文系統")

st.caption(f"版本 {APP_VERSION}｜🟣 Claude 協作版（v3.2.0 以前為 🔵 Gemini 協作）")

# 🔒 園所通行密碼
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

st.markdown("上傳活動照片，設定風格，一鍵智能嚴選並產出雙平台精美文案。")

# --- ⚙️ 步驟 1：系統驗證 ---
st.markdown("---")
st.subheader("⚙️ 步驟 1：系統驗證")
if EMBEDDED_API_KEY:
  api_key = EMBEDDED_API_KEY
  st.success("✅ 已自動由雲端安全保險箱（Secrets）載入您綁定的 API 金鑰！")
else:
  api_key = st.text_input("🔑 請貼上您的 Google Gemini API Key", type="password")
  if not api_key:
    st.warning("請先輸入金鑰以解鎖 AI 功能。")

# --- 📝 步驟 2：活動資訊與貼文定調 ---
st.markdown("---")
st.subheader("📝 步驟 2：活動資訊與貼文定調")
rc = st.session_state.reset_counter
col1, col2 = st.columns(2)
with col1:
  st.text_area(
      "🔑 活動關鍵字 / 描述",
      placeholder="例如：萬聖節、不怕跌倒、中秋吃柚子...",
      key=f"keywords_{rc}",
  )
  st.radio(
      "📌 貼文類型",
      ["日常紀錄", "節慶活動", "主題教學", "藝術活動", "幼兒科學", "體能/戶外", "園所公告"],
      horizontal=True,
      key=f"post_type_{rc}",
  )
  st.radio(
      "👁️ 敘事視角", ["老師視角", "孩子視角", "旁觀者視角"], horizontal=True, key=f"perspective_{rc}"
  )
  st.radio("⚡ 文字長度", list(LENGTH_RULES.keys()), horizontal=True, key=f"text_length_{rc}")
with col2:
  st.multiselect(
      "🎨 語氣與氛圍 (可複選)",
      ["溫馨親切", "活潑逗趣", "專業信賴", "夢幻童話", "陽光正能量"],
      default=["溫馨親切"],
      key=f"tone_{rc}",
  )
  st.multiselect(
      "💡 教育理念 (可複選)",
      ["日常生活體驗", "生活自理", "邏輯與專注力", "人際與分享", "感覺統合與大肌肉", "美感與創造力"],
      key=f"edu_{rc}",
  )
  st.multiselect(
      "🎯 互動目標 (可複選)", ["呼籲按讚/愛心", "引導家長留言討論", "提醒重要事項"], key=f"cta_{rc}"
  )

# --- 📸 步驟 3：匯入素材與進階設定 ---
st.markdown("---")
st.subheader("📸 步驟 3：匯入素材與進階設定")
opt1, opt2 = st.columns(2)
with opt1:
  enable_blur = st.toggle(
      "✨ IG 防裁切模式：補上模糊背景，統一輸出 1080×1350 (4:5)", value=True, key=f"blur_{rc}"
  )
with opt2:
  enable_mark = st.toggle(
      "🖼️ 加上園所 Logo 浮水印（右下角）", value=True, key=f"mark_{rc}",
      disabled=load_logo() is None,
      help=None if load_logo() is not None else "找不到 logo.png，無法加浮水印",
  )
uploaded_files = st.file_uploader(
    "請拖曳或從手機相簿選擇多張照片 (數量無上限)",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    key=f"files_{rc}",
)
if uploaded_files:
  st.success(
      f"🎉 已成功接收 {len(uploaded_files)} 張照片！交給 AI 為您依據多樣性原則精選最佳畫面。"
  )

# --- 🚀 執行與操作按鈕區 ---
st.markdown("---")
btn_col1, btn_col2 = st.columns([3, 1])
with btn_col1:
  generate_btn = st.button("✨ 步驟 4：一鍵分析並產出社群貼文", width="stretch", type="primary")
with btn_col2:
  if st.button("🔄 一鍵清空 / 開始下一篇", width="stretch"):
    st.session_state.reset_counter += 1
    for k in list(st.session_state.keys()):
      if k in ("result", "consent_ok", "sticker_kind") or k.startswith(
          ("edit_", "adopt_", "ver_pick", "rw_", "cover_")):
        del st.session_state[k]
    st.rerun()

history_rows = None
if history_enabled():
  history_rows, _hist_err = fetch_history(HISTORY_URL, HISTORY_TOKEN, 10)

# --- 🧠 第一次分析 ---
if generate_btn:
  if not api_key:
    st.error("請先在最上方輸入 Gemini API Key！")
  elif not uploaded_files:
    st.error("請至少上傳一張照片！")
  else:
    with st.spinner("系統正在全神貫注分析素材並撰寫精美文案中，請稍候..."):
      try:
        settings = snapshot_settings()
        prompt = build_analysis_prompt(len(uploaded_files), settings, history_rows)
        api_images = [load_image(f, max_size=1024) for f in uploaded_files]
        status = st.empty()
        data, raw = call_gemini(api_key, [prompt] + api_images, AnalysisResult, status)
        del api_images
        gc.collect()

        picked = []
        for n in data.get("selected_images", []):
          idx = int(n) - 1
          if 0 <= idx < len(uploaded_files) and idx not in picked:
            picked.append(idx)
          if len(picked) >= MAX_SELECTED:
            break
        if not picked:
          picked = list(range(min(len(uploaded_files), MAX_SELECTED)))

        face_map = {}
        for item in data.get("faces", []) or []:
          try:
            face_map[int(item["image"]) - 1] = [
                (f["ymin"], f["xmin"], f["ymax"], f["xmax"]) for f in item.get("faces", [])
            ]
          except Exception:
            continue

        photos = []
        for idx in picked:
          photos.append(make_base_photo(uploaded_files[idx], enable_blur, face_map.get(idx, [])))
          gc.collect()

        st.session_state.result = {
            "photos": photos,
            "watermark": enable_mark,
            "render_cache": {},
            "blur": enable_blur,
            "activity": safe_name(settings["keywords"], settings["post_type"]),
            "summary": data.get("photo_summary", ""),
            "suggestion": data.get("suggestion", ""),
            "settings": settings,
            "raw": [raw],
            "versions": [{
                "label": "初版",
                "ig_body": data.get("ig_text", ""),
                "fb_body": data.get("fb_text", ""),
                "hashtags": build_hashtags(data.get("content_hashtags", [])),
                "ig_edit": None,
                "fb_edit": None,
            }],
            "adopted": [],
        }
        st.session_state.ver_pick = 0
        for k in list(st.session_state.keys()):
          if k.startswith(("edit_ig_", "edit_fb_", "cover_")) or k in ("consent_ok", "sticker_kind"):
            del st.session_state[k]
      except Exception as e:
        st.error(f"系統偵測到錯誤：{e}")

# =========================================================================
# 📤 成果區（存在 session_state，按任何按鈕都不會消失）
# =========================================================================
result = st.session_state.get("result")
if result:
  # 🔁 處理「再給我一版」（在版本選單繪製前執行）
  if st.session_state.get("rw_go"):
    current_vid = st.session_state.get("ver_pick", 0)
    current = result["versions"][current_vid]
    target = {"兩篇都重寫": "both", "只重寫 IG": "ig", "只重寫 FB": "fb"}[
        st.session_state.get("rw_target", "兩篇都重寫")
    ]
    direction = st.session_state.get("rw_direction", "").strip()
    with st.spinner("正在依照片摘要重新撰寫文案..."):
      try:
        settings = snapshot_settings()
        prompt = build_rewrite_prompt(
            result["summary"], settings, current, target, direction, history_rows
        )
        data, raw = call_gemini(api_key, [prompt], RewriteResult, st.empty())
        new = {
            "label": direction[:12] if direction else f"第 {len(result['versions']) + 1} 版",
            "ig_body": data["ig_text"] if target in ("both", "ig") else current["ig_body"],
            "fb_body": data["fb_text"] if target in ("both", "fb") else current["fb_body"],
            "hashtags": build_hashtags(data.get("content_hashtags", []))
            if target == "both" else list(current["hashtags"]),
            "ig_edit": None if target in ("both", "ig") else current.get("ig_edit"),
            "fb_edit": None if target in ("both", "fb") else current.get("fb_edit"),
        }
        result["versions"].append(new)
        result["raw"].append(raw)
        if len(result["versions"]) > MAX_VERSIONS:
          result["versions"].pop(0)
          result["raw"].pop(0)
          result["adopted"] = [a - 1 for a in result["adopted"] if a - 1 >= 0]
          for k in list(st.session_state.keys()):
            if k.startswith(("edit_ig_", "edit_fb_")):
              del st.session_state[k]
        st.session_state.ver_pick = len(result["versions"]) - 1
        st.session_state.rw_direction = ""
      except Exception as e:
        st.error(f"重寫時發生錯誤：{e}")

  st.success("🎉 文案與分析皆已產出！下方的照片與文案會保留到您按「一鍵清空」為止。")

  # ---------- 照片 ----------
  photos = result["photos"]
  activity = result["activity"]
  cache = result["render_cache"]
  if len(cache) > 120:
    cache.clear()

  st.markdown("### 🛡️ AI 嚴選照片｜肖像權確認")
  st.caption(
      "照片上的 ① ② ③ 是 AI 找到的臉。若有未同意公開的孩子，請按該照片下方的號碼蓋上貼圖；"
      "再按一次可取消。大多數貼文不需要點任何東西。"
  )
  s1, s2, s3 = st.columns([2, 1, 1])
  with s1:
    kind_label = st.segmented_control(
        "遮臉貼圖", list(STICKERS.keys()), default="笑臉", key="sticker_kind", required=True
    ) or "笑臉"
  kind = STICKERS[kind_label]

  def _set_all(on):
    for j, p in enumerate(photos):
      st.session_state[f"cover_{j}"] = list(range(1, len(p["faces"]) + 1)) if on else []
    st.session_state.consent_ok = False

  def _covers_changed():
    st.session_state.consent_ok = False

  with s2:
    st.button("全部遮住", width="stretch", on_click=_set_all, args=(True,))
  with s3:
    st.button("全部取消", width="stretch", on_click=_set_all, args=(False,))

  finals = []
  prev_cols = st.columns(2)
  for i, p in enumerate(photos):
    covers = tuple(sorted(st.session_state.get(f"cover_{i}", []) or []))
    fkey = (i, covers, kind, "final")
    if fkey not in cache:
      cache[fkey] = render_photo(p, covers, kind, result["watermark"])
    finals.append(cache[fkey])
    pkey = (i, covers, kind, "preview")
    if pkey not in cache:
      cache[pkey] = render_preview(cache[fkey], p["faces"], covers)
    with prev_cols[i % 2]:
      n_faces = len(p["faces"])
      st.image(cache[pkey], width="stretch",
               caption=f"建議擺在第 {i + 1} 張｜偵測到 {n_faces} 張臉")
      if n_faces:
        st.pills(
            f"第 {i + 1} 張：要遮的臉",
            options=list(range(1, n_faces + 1)),
            selection_mode="multi",
            key=f"cover_{i}",
            on_change=_covers_changed,
        )
      else:
        st.caption("沒有偵測到臉，不用處理")

  st.warning(
      "⚠️ AI 可能漏掉很小、側面或被擋住的臉，請逐張確認。"
      "若有漏標又不能公開的孩子，建議換掉那張照片。"
  )
  n_covered = sum(len(st.session_state.get(f"cover_{i}", []) or []) for i in range(len(photos)))
  st.caption(f"目前已遮住 {n_covered} 張臉。")
  consent = st.checkbox("我已確認本篇照片中，沒有未同意公開的孩子", key="consent_ok")

  if not consent:
    st.info("勾選上方確認後，才會出現下載按鈕與可儲存的照片。")
  else:
    st.markdown("### 🏆 可下載的完成照片")
    d1, d2 = st.columns(2)
    with d1:
      st.download_button(
          f"📦 下載 ZIP（{len(finals)} 張，電腦用）",
          data=build_zip(finals, activity),
          file_name=f"{datetime.now(TZ):%Y%m%d}_{activity}.zip",
          mime="application/zip",
          on_click="ignore",
          width="stretch",
      )
    with d2:
      st.html(share_widget_html(finals, activity), unsafe_allow_javascript=True)
    st.caption("💡 手機也可以「長按」下方照片，選擇「儲存影像」。照片依建議發文順序排列。")
    img_cols = st.columns(2)
    mode_note = "1080×1350" if result["blur"] else "原圖比例"
    for i, data in enumerate(finals):
      img_cols[i % 2].image(data, width="stretch", caption=f"🏆 建議擺在第 {i + 1} 張（{mode_note}）")

  # ---------- 文案 ----------
  st.markdown("---")
  versions = result["versions"]
  if st.session_state.get("ver_pick", 0) >= len(versions):
    st.session_state.ver_pick = len(versions) - 1
  st.markdown("### ✍️ 貼文文案")
  vid = st.radio(
      "📚 版本（最多保留 5 版，關閉網頁後清空）",
      options=list(range(len(versions))),
      format_func=lambda i: f"版本 {i + 1}｜{versions[i]['label']}" + ("　✅已採用" if i in result["adopted"] else ""),
      horizontal=True,
      key="ver_pick",
  )
  ver = versions[vid]
  editing = st.toggle("✏️ 我要修改文案", key="edit_mode")

  tab_ig, tab_fb = st.columns(2)
  for col, platform, title in ((tab_ig, "ig", "📸 Instagram"), (tab_fb, "fb", "📘 Facebook")):
    with col:
      st.markdown(f"#### {title}")
      text = full_text(ver, platform)
      if editing:
        st.text_area(
            f"{title} 文案（修改後自動更新下方複製框）",
            value=text,
            height=260,
            key=f"edit_{platform}_{vid}",
            on_change=on_edit_change,
            args=(vid, platform),
        )
        text = full_text(ver, platform)
      st.code(text, language=None, wrap_lines=True)
      st.caption("👆 點右上角圖示即可一鍵複製")
      n_tags = count_hashtags(text)
      if n_tags > MAX_HASHTAGS:
        st.warning(f"⚠️ 目前有 {n_tags} 個 hashtag，Instagram 規定最多 {MAX_HASHTAGS} 個，請刪減。")

  # ---------- 採用這版 ----------
  a1, a2 = st.columns([1, 2])
  with a1:
    if vid in result["adopted"]:
      st.success("✅ 這個版本已記錄到發文歷史")
    elif st.button("✅ 採用這版（記錄到發文歷史）", type="primary", width="stretch",
                   disabled=not history_enabled(), key=f"adopt_{vid}"):
      s = result["settings"]
      ok, err = save_history({
          "date": f"{datetime.now(TZ):%Y-%m-%d %H:%M}",
          "keywords": s["keywords"],
          "post_type": s["post_type"],
          "text_length": s["text_length"],
          "ig": full_text(ver, "ig"),
          "fb": full_text(ver, "fb"),
          "hashtags": " ".join(ver["hashtags"]),
          "version": f"版本 {vid + 1}",
      })
      if ok:
        result["adopted"].append(vid)
        st.rerun()
      else:
        st.error(f"記錄失敗：{err}")
  with a2:
    if not history_enabled():
      st.caption("ℹ️ 尚未設定 Google 試算表（HISTORY_URL / HISTORY_TOKEN），發文歷史功能暫時關閉。")

  # ---------- 再給我一版 ----------
  st.markdown("---")
  st.markdown("### 🔁 再給我一版")
  st.caption(
      "照片不變，只依「照片摘要」快速重寫文案。也可以先回到步驟 2 調整語氣、文字長度等設定，再按重寫。"
  )
  r1, r2 = st.columns([1, 2])
  with r1:
    st.radio("重寫範圍", ["兩篇都重寫", "只重寫 IG", "只重寫 FB"], key="rw_target")
  with r2:
    st.text_input(
        "修改方向（選填）",
        placeholder="例如：再活潑一點、提到今天下雨還是玩得很開心、不要用驚嘆號",
        key="rw_direction",
    )
  st.button(
      f"🔁 再給我一版（目前 {len(versions)}/{MAX_VERSIONS} 版，超過會移除最舊的）",
      key="rw_go",
      width="stretch",
      disabled=not api_key,
  )

  st.markdown("### 💡 AI 小編挑圖建議")
  st.info(result["suggestion"] or "無提供建議")
  with st.expander("🔍 檢視照片摘要與 AI 原始回應 (除錯與備份用)"):
    st.markdown("**照片內容摘要**")
    st.write(result["summary"])
    st.markdown("**AI 原始回應（最新一次）**")
    st.code(result["raw"][-1], language="json", wrap_lines=True)

# =========================================================================
# 🗂️ 發文歷史紀錄
# =========================================================================
st.markdown("---")
with st.expander("🗂️ 最近 10 篇發文紀錄"):
  if not history_enabled():
    st.caption("尚未設定 Google 試算表。設定方式請見功能清單「發文歷史設定」章節。")
  elif history_rows is None:
    st.warning(f"讀取發文紀錄失敗：{_hist_err}")
  elif not history_rows:
    st.caption("目前還沒有紀錄。產出文案後按「✅ 採用這版」就會記錄在這裡。")
  else:
    table = []
    for row in history_rows:
      row = list(row) + [""] * 8
      table.append({
          "日期": str(row[0])[:16],
          "活動關鍵字": row[1],
          "類型": row[2],
          "IG 文案": re.sub(r"\s+", " ", str(row[4]))[:60],
          "Hashtag": row[6],
      })
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("AI 撰寫新文案時，會自動參考這些紀錄避免重複。")
