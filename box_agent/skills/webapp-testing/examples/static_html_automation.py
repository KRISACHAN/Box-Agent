from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from threading import Thread

from playwright.sync_api import sync_playwright

# Example: Automating local HTML through an ephemeral loopback HTTP server.
# OfficeV3's managed browser blocks file:// and concurrent tasks must not share
# a fixed preview port.

html_file_path = os.path.abspath('path/to/your/file.html')
html_dir = os.path.dirname(html_file_path)
handler = partial(SimpleHTTPRequestHandler, directory=html_dir)
server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
server_thread = Thread(target=server.serve_forever, daemon=True)
server_thread.start()
page_url = f'http://127.0.0.1:{server.server_port}/{os.path.basename(html_file_path)}'

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})

        page.goto(page_url)

        # Take screenshot
        page.screenshot(path='/mnt/user-data/outputs/static_page.png', full_page=True)

        # Interact with elements
        page.click('text=Click Me')
        page.fill('#name', 'John Doe')
        page.fill('#email', 'john@example.com')

        # Submit form
        page.click('button[type="submit"]')
        page.wait_for_timeout(500)

        # Take final screenshot
        page.screenshot(path='/mnt/user-data/outputs/after_submit.png', full_page=True)

        browser.close()
finally:
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=5)

print("Static HTML automation completed!")
