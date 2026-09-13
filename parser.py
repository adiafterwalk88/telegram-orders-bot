from playwright.async_api import async_playwright
import re

async def fetch_ozon_price(article: str) -> float | None:
    url = f"https://www.ozon.ru/product/{article}/"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # ждём подгрузки цены
            content = await page.content()
            # Ищем цену в HTML. Селекторы Ozon часто меняются — при поломке обновите regex.
            match = re.search(r'"price":"(\d+)"', content)
            if match:
                return float(match.group(1))
            # Альтернативный паттерн
            match = re.search(r'(\d[\d\s]*)\s*₽', content)
            if match:
                return float(match.group(1).replace(" ", ""))
            return None
        except Exception as e:
            print(f"Parser error for {article}: {e}")
            return None
        finally:
            await browser.close()
