"""截取界面交互状态的截图（安装面板、弹窗等）。

用法: python tools/shot_steps.py home install picker mods instsettings log
需要完整权限运行（Chrome 需要命名管道）。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = os.environ.get("PIL_URL", "http://127.0.0.1:10140")
OUT = os.path.join(ROOT, ".shots")
DEMO = os.path.join(ROOT, "static", "_shot.html")

INJECT = """
<style>* { transition: none !important; animation: none !important; }</style>
<script>
(function(){
  var step = new URLSearchParams(location.search).get("step") || "";
  function ready(fn){
    var n = 0;
    var t = setInterval(function(){
      if (window.__PIL_READY || n > 100) { clearInterval(t); setTimeout(fn, 600); }
      n++;
    }, 100);
  }
  ready(function(){
    if (step === "install") {
      document.querySelector('.nav-item[data-page="instances"]').click();
      setTimeout(function(){ document.querySelector('[data-action="toggle-install"]').click(); }, 500);
    } else if (step === "picker") {
      document.querySelector('.nav-item[data-page="instances"]').click();
      setTimeout(function(){ document.querySelector('[data-action="toggle-install"]').click(); }, 400);
      setTimeout(function(){ document.querySelector('[data-action="pick-install-version"]').click(); }, 900);
    } else if (step === "mods" || step === "instsettings") {
      document.querySelector('.nav-item[data-page="instances"]').click();
      setTimeout(function(){
        var card = document.querySelector('.instance-card');
        if (!card) return;
        var r = card.getBoundingClientRect();
        card.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:r.left+40,clientY:r.top+20}));
      }, 700);
      setTimeout(function(){
        var items = document.querySelectorAll('.ctx-item');
        var idx = step === "mods" ? 2 : 3;
        if (items[idx]) items[idx].click();
      }, 1200);
    } else if (step === "log") {
      setTimeout(function(){ document.querySelector('[data-action="open-log"]').click(); }, 700);
    } else if (step === "settings-bottom") {
      document.querySelector('.nav-item[data-page="settings"]').click();
      setTimeout(function(){
        var p = document.querySelector('#page-settings');
        if (p) p.scrollTop = p.scrollHeight;
      }, 800);
    } else if (step === "version") {
      setTimeout(function(){ document.querySelector('[data-action="pick-version"]').click(); }, 700);
    }
  });
})();
</script>
"""


def build_demo():
    with open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("</body>", INJECT + "</body>")
    with open(DEMO, "w", encoding="utf-8") as f:
        f.write(html)


def shot(step):
    url = BASE + "/static/_shot.html?step=" + step
    path = os.path.join(OUT, "step-" + step + ".png")
    subprocess.run([
        CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
        "--window-size=1440,900", "--virtual-time-budget=16000",
        "--screenshot=" + path, url,
    ], capture_output=True)
    print("saved", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    build_demo()
    try:
        for step in sys.argv[1:] or ["install"]:
            shot(step)
    finally:
        if os.path.exists(DEMO):
            os.remove(DEMO)


if __name__ == "__main__":
    main()
