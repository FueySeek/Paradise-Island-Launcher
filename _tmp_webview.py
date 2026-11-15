import os
import threading
import time

import webview

storage = os.path.join(os.getcwd(), "_tmp_webview_data")
os.makedirs(storage, exist_ok=True)

window = webview.create_window(
    "PIL WebView Test",
    html="<body style='background:#15181d;color:#e8e8e8;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'><h1>WebView2 OK</h1></body>",
    width=720,
    height=420,
)


def close_later():
    time.sleep(8)
    window.destroy()


threading.Thread(target=close_later, daemon=True).start()
webview.start(private_mode=False, storage_path=storage)
print("closed")
