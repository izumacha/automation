"""
ブラウザ自動化スクリプト
- https://izumacha.github.io/profile-portfolio/ を開く
- サイト内の要素から https://github.com/izumacha に移動する
"""

from playwright.sync_api import sync_playwright
import time


def main():
    with sync_playwright() as p:
        # ブラウザを起動（headless=Falseで画面表示）
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 1. ポートフォリオサイトを開く
        print("ポートフォリオサイトを開いています...")
        page.goto("https://izumacha.github.io/profile-portfolio/")
        page.wait_for_load_state("networkidle")
        print(f"現在のURL: {page.url}")

        # 少し待機してページを確認
        time.sleep(2)

        # 2. GitHubへのリンクを探してクリック
        print("GitHubリンクを探しています...")

        # 方法1: href属性でGitHubリンクを直接探す
        github_link = page.locator('a[href*="github.com/izumacha"]').first

        if github_link.count() > 0:
            print("GitHubリンクを見つけました。クリックします...")
            github_link.click()
        else:
            # 方法2: テキストで「GitHub」を含むリンクを探す
            github_text_link = page.locator('a:has-text("GitHub")').first
            if github_text_link.count() > 0:
                print("'GitHub'テキストのリンクを見つけました。クリックします...")
                github_text_link.click()
            else:
                # 方法3: GitHubアイコン（SVGやi要素）を含むリンクを探す
                github_icon_link = page.locator('a:has([class*="github"]), a:has([class*="fa-github"])').first
                if github_icon_link.count() > 0:
                    print("GitHubアイコンリンクを見つけました。クリックします...")
                    github_icon_link.click()
                else:
                    print("GitHubリンクが見つかりませんでした")
                    browser.close()
                    return

        # ページ遷移を待つ
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 3. 結果を確認
        current_url = page.url
        print(f"遷移後のURL: {current_url}")

        if "github.com/izumacha" in current_url:
            print("GitHubプロフィールページへの移動に成功しました！")
        else:
            print(f"予期しないURLに移動しました: {current_url}")

        # 確認のため少し待機
        time.sleep(3)

        # ブラウザを閉じる
        browser.close()
        print("ブラウザを閉じました。")


if __name__ == "__main__":
    main()
