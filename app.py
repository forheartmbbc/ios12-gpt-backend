import os, base64, html, requests
from flask import Flask, request

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = "gpt-4o"
MAX_MEDIA_BYTES = int(os.getenv("MAX_MEDIA_BYTES", "3500000"))  # 約 3.5MB 上限


def render_html(title, body_html):
    return f"""<!doctype html><html lang="zh-Hant"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{
  font-family:"Microsoft JhengHei","微軟正黑體","PingFang TC",Arial,sans-serif;
  font-size:16px;
  background:#f6f7f9;
  color:#222;
  margin:0;
  padding:24px;
  line-height:1.6;
}}
.container{{max-width:680px;margin:0 auto;}}
h1{{font-size:18px;margin:0 0 12px;font-weight:bold;}}
label{{display:block;margin:12px 0 6px;}}
input,textarea,button{{
  font-size:16px;
  font-family:"Microsoft JhengHei","微軟正黑體",Arial,sans-serif;
}}
textarea{{width:100%;min-height:120px;padding:10px;}}
button{{
  background:#10a37f;
  color:#fff;
  border:0;
  border-radius:8px;
  padding:10px 16px;
  cursor:pointer;
}}
pre{{
  white-space:pre-wrap;
  background:#fff;
  border:1px solid #e5e7eb;
  border-radius:8px;
  padding:12px;
  font-size:16px;
  font-family:"Microsoft JhengHei",monospace;
}}
.note{{color:#666;font-size:14px;}}
a.btn{{
  display:inline-block;
  margin-top:14px;
  text-decoration:none;
  background:#e5e7eb;
  color:#111;
  padding:8px 12px;
  border-radius:8px;
}}
footer{{margin-top:20px;color:#777;font-size:14px;}}
</style></head><body><div class="container">
{body_html}
<footer>© iOS12 GPT Gateway · Render 服務提供</footer>
</div></body></html>"""


def answer_page(answer_text, back_url=None):
    back_link = (
        f'<a class="btn" href="{html.escape(back_url)}">← 回到前端頁面</a>'
        if back_url else ""
    )
    return render_html("回答結果", f"<h1>回答結果</h1><pre>{html.escape(answer_text)}</pre>{back_link}")


def form_page(action_url="/ask"):
    return render_html(
        "iOS12 ChatGPT",
        f"""
<h1>iOS 12 ChatGPT</h1>
<form method="post" action="{html.escape(action_url)}" enctype="multipart/form-data">
  <label>你的問題</label>
  <textarea name="question" placeholder="請輸入問題"></textarea>
  <label>上傳圖片或影片（可直接拍照或從相簿選取）</label>
  <input type="file" name="media" accept="image/*,video/*">
  <div style="margin-top:14px;"><button type="submit">送出</button></div>
</form>
<p class="note">提示：可上傳圖片或影片（3.5MB 內），支援 iOS 12 Safari 拍照或選檔。</p>
""",
    )


@app.route("/", methods=["GET"])
def index():
    return form_page("/ask")


@app.route("/ask", methods=["POST"])
def ask():
    if not OPENAI_API_KEY:
        return render_html("設定錯誤", "<h1>後端尚未設定 OPENAI_API_KEY</h1>"), 500

    question = (request.form.get("question") or "").strip()
    media_file = request.files.get("media")
    referer = request.headers.get("Referer", "")
    if not question and not media_file:
        return render_html(
            "缺少內容",
            "<h1>請至少輸入問題或上傳圖片／影片</h1>"
            "<a class='btn' href='javascript:history.back()'>← 返回</a>",
        ), 400

    media_block = None
    if media_file and media_file.filename:
        filetype = media_file.mimetype
        media_bytes = media_file.read()
        if len(media_bytes) > MAX_MEDIA_BYTES:
            return render_html(
                "檔案過大",
                f"<h1>檔案超過 {MAX_MEDIA_BYTES//1000000}MB，請壓小再上傳</h1>"
                "<a class='btn' href='javascript:history.back()'>← 返回</a>",
            ), 400
        if filetype.startswith("image/"):
            b64 = base64.b64encode(media_bytes).decode("utf-8")
            media_block = {
                "type": "image_url",
                "image_url": {"url": f"data:{filetype};base64,{b64}"},
            }
        elif filetype.startswith("video/"):
            filename = html.escape(media_file.filename)
            media_block = {
                "type": "text",
                "text": f"[使用者上傳了一段影片（{filename}，格式 {filetype}），請根據文字問題回答。]"
            }

    if media_block:
        content = [
            {"type": "text", "text": question or "請根據上傳內容說明重點"},
            media_block,
        ]
    else:
        content = question

    payload = {
        "model": MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是簡潔、有條理的中文助理，請用清晰短句回覆。"},
            {"role": "user", "content": content},
        ],
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        data = resp.json()
        if resp.status_code >= 400:
            msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            if "quota" in msg:
                msg = "目前 OpenAI API 額度不足，請更新金鑰或稍後再試。"
            return render_html("OpenAI 錯誤", f"<h1>OpenAI 回應錯誤</h1><pre>{html.escape(msg)}</pre>"
                               "<a class='btn' href='javascript:history.back()'>← 返回</a>"), 502
        answer = data["choices"][0]["message"]["content"]
        return answer_page(answer, back_url=referer or "/")

    except Exception as e:
        return render_html("系統錯誤",
                           f"<h1>呼叫失敗</h1><pre>{html.escape(str(e))}</pre>"
                           "<a class='btn' href='javascript:history.back()'>← 返回</a>"), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
