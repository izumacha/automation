"""
ブラウザ自動化スクリプト
- https://izumacha.github.io/profile-portfolio/ を開く
- サイト内の要素から https://github.com/izumacha に移動する
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

PORTFOLIO_URL = "https://izumacha.github.io/profile-portfolio/"
GITHUB_URL_FRAGMENT = "github.com/izumacha"

GITHUB_LINK_SELECTORS = [
    'a[href*="github.com/izumacha"]',
    'a:has-text("GitHub")',
    'a:has([class*="github"]), a:has([class*="fa-github"])',
]


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()

            print("ポートフォリオサイトを開いています...")
            page.goto(PORTFOLIO_URL, timeout=30_000)
            page.wait_for_load_state("networkidle")
            print(f"現在のURL: {page.url}")

            print("GitHubリンクを探しています...")
            clicked = False
            for selector in GITHUB_LINK_SELECTORS:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.click()
                    clicked = True
                    break

            if not clicked:
                print("GitHubリンクが見つかりませんでした")
                return

            page.wait_for_load_state("networkidle")
            page.wait_for_url(f"**/{GITHUB_URL_FRAGMENT}**", timeout=10_000)

            current_url = page.url
            print(f"遷移後のURL: {current_url}")

            if GITHUB_URL_FRAGMENT in current_url:
                print("GitHubプロフィールページへの移動に成功しました！")
            else:
                print(f"予期しないURLに移動しました: {current_url}")
        except PlaywrightTimeout as exc:
            print(f"タイムアウトが発生しました: {exc}")
        except Exception as exc:
            print(f"予期しないエラーが発生しました: {exc}")
        finally:
            browser.close()
            print("ブラウザを閉じました。")


if __name__ == "__main__":
    main()
