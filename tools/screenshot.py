"""用无头浏览器截图检查界面。用法: python tools/screenshot.py [url]"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:10140/"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".shots")
os.makedirs(OUT, exist_ok=True)

errors = []


def shot(page, name):
    page.wait_for_timeout(450)
    path = os.path.join(OUT, name + ".png")
    page.screenshot(path=path)
    print("saved", path)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(m.type + ": " + m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.goto(URL, wait_until="networkidle")
        page.wait_for_function("window.__PIL_READY === true", timeout=40000)
        page.wait_for_timeout(900)
        shot(page, "01-home")

        page.click('.nav-item[data-page="instances"]')
        page.wait_for_timeout(500)
        shot(page, "02-instances")

        page.click('[data-action="toggle-install"]')
        page.wait_for_timeout(500)
        shot(page, "03-install-panel")

        page.click('[data-action="pick-install-version"]')
        page.wait_for_timeout(600)
        shot(page, "04-version-picker")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        page.click('.nav-item[data-page="accounts"]')
        page.wait_for_timeout(600)
        shot(page, "05-accounts")

        page.click('.nav-item[data-page="java"]')
        page.wait_for_timeout(700)
        shot(page, "06-java")

        page.click('.nav-item[data-page="settings"]')
        page.wait_for_timeout(700)
        shot(page, "07-settings")

        page.select_option("#languageSelect", "ja")
        page.wait_for_timeout(700)
        shot(page, "08-settings-ja")
        page.select_option("#languageSelect", "en")
        page.wait_for_timeout(700)

        page.click('.nav-item[data-page="home"]')
        page.wait_for_timeout(400)
        page.click('[data-action="open-log"]')
        page.wait_for_timeout(900)
        shot(page, "09-log")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        page.click('.nav-item[data-page="instances"]')
        page.wait_for_timeout(400)
        card = page.query_selector(".instance-card")
        if card:
            card.click(button="right")
            page.wait_for_timeout(300)
            shot(page, "10-context-menu")
            items = page.query_selector_all(".ctx-item")
            if len(items) > 2:
                items[2].click()
                page.wait_for_timeout(800)
                shot(page, "11-mods")
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)

        page.click('.nav-item[data-page="home"]')
        page.wait_for_timeout(400)
        page.click(".switch-version")
        page.wait_for_timeout(600)
        shot(page, "12-switch-version")

        browser.close()
    if errors:
        print("CONSOLE ERRORS:")
        for e in dict.fromkeys(errors):
            print("  " + e)
    else:
        print("no console errors")


if __name__ == "__main__":
    main()
