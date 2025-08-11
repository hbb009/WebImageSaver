import os
from threading import Thread
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import requests

SAVE_FOLDER = os.path.expanduser("~/Pictures/WebImageSaver")

# 通过 PageFastSave 实例来判断是否接收 & 推送队列
_fast_page_ref = None

def start_server_thread(page_fast):
    global _fast_page_ref
    _fast_page_ref = page_fast
    app = Flask(__name__); CORS(app)

    @app.route('/save', methods=['POST'])
    def save_from_url():
        if _fast_page_ref is None or not _fast_page_ref.allow_accept():
            return jsonify({"status":"ignored"})
        data = request.json or {}
        url = data.get("url")
        if not url:
            return jsonify({"error":"no url"}), 400
        try:
            r = requests.get(url)
            ext = url.split('.')[-1].split('?')[0][:4]
            filename = f"img_ext_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            os.makedirs(SAVE_FOLDER, exist_ok=True)
            full_path = os.path.join(SAVE_FOLDER, filename)
            with open(full_path, 'wb') as f: f.write(r.content)
            # 推入页面队列
            _fast_page_ref.shared_queue().append({"type":"image","filename":filename})
            return jsonify({"status":"ok"})
        except Exception as e:
            return jsonify({"error":str(e)}), 500

    Thread(target=lambda: app.run(port=8787, debug=False, use_reloader=False), daemon=True).start()