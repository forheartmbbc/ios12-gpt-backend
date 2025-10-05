import os, base64, textwrap, uuid, html
from flask import Flask, request, make_response

import requests  # 用 requests 直接打 OpenAI REST API，比安裝 openai 套件更穩

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "3500000"))  # ~3.5MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB 上傳限制

def render_html(title, body_html):
    # 簡單乾淨的 HTML，iOS 12 友善
    return f"""<!doctype html><html lang="zh-Hant"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;background:#f6f7f9;color:#222;margin:0;padding:24px;}}
.container{{max-width:680px;margin:0 auto;}}
h1{{font-size:20px;margin:0 0 12px;}}
label{{display:block;margin:12px 0 6px;}}
input,textarea,button{{font-size:16px;}}
textarea{{width:100%;min-height:120px;padding:10px;}}
button{{background:#10a37f;color:#fff;border:0;border-radius:8px;padding:10px 16px;}}
pre{{white-space:pre-wrap;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px;}}
.note{{color:#666;font-size:14px;}}
a.btn{{display:inline-block;margin-top:14px;text-decoration:none;background:#e5e7eb;color:#111;padding:8px 12px;border-radius:8px;}}
footer{{margin-top:24px;color:#777;font-size:13px;}}
</style></head><body><div class="container">
{body_html}
<footer>© iOS12 GPT Gateway · 由你的 Render 後端提供</footer>
</div></body></html>"""

def answer_page(answer_text, back_url=None):
    back_link = f'<a class="btn" href="{html.escape(back_url)}">← 回到前端頁面</a>' if back_url else ""
    return render_html("回答結果", f"<h1>回答結果</h1><pre>{html.escape(answer_text)}</pre>{back_link}")

def form_page(action_url=""):
    # 提供一個內建表單（當你直接打開後端網址，也能用）
    return render_html("iOS12 ChatGPT 表單", f"""
<h1>iOS 12 ChatGPT 表單（備用）</h1>
<form method="post" action="{html.escape(action_url or "/ask")}" enctype="multipart/form-data">
  <label>你的問題</label>
  <textarea name="question" placeholder="請輸入問題"></textarea>
  <label>上傳圖片（可直接拍照）</label>
  <input type="file" name="image" accept="image/*" capture="camera">
  <div style="margin-top:14px;"><button type="submit">送出</button></div>
</form>
<p class="note">提示：iOS 12 可用，圖片上限約 3.5MB。</p>
""")

@app.route("/", methods=["GET"])
def index():
    # 後端首頁（備用），可測試
    return form_page("/ask")

@app.route("/ask", methods=["POST"])
def ask():
    if not OPENAI_API_KEY:
        return render_html("設定錯誤", "<h1>後端尚未設 OPENAI_API_KEY</h1>"), 500

    question = (request.form.get("question") or "").strip()
    img_file = request.files.get("image")
    referer = request.headers.get("Referer", "")

    if not question and not img_file:
        return render_html("缺少內容", "<h1>請至少輸入問題或上傳圖片</h1><a class='btn' href='javascript:history.back()'>← 返回</a>"), 400

    # 處理圖片（可選）
    image_block = None
    if img_file and img_file.filename:
        img_bytes = img_file.read()
        if len(img_bytes) > MAX_IMAGE_BYTES:
            return render_html("圖片過大", f"<h1>圖片超過 {MAX_IMAGE_BYTES//1000000}MB，請壓小再上傳</h1><a class='btn' href='javascript:history.back()'>← 返回</a>"), 400
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        image_block = {
            "type": "image_url",
            "image_url": { "url": f"data:image/jpeg;base64,{b64}" }
        }

    # 準備 messages
    if image_block:
        content = [
            {"type": "text", "text": question or "請根據圖片說明重點"},
            image_block
        ]
    else:
        content = question

    payload = {
        "model": MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是精簡、有條理的中文助理，回覆儘量短而準。"},
            {"role": "user", "content": content}
        ]
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=90
        )
        data = resp.json()
        if resp.status_code >= 400:
            msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return render_html("OpenAI 錯誤", f"<h1>OpenAI 回應錯誤</h1><pre>{html.escape(msg)}</pre><a class='btn' hr_
