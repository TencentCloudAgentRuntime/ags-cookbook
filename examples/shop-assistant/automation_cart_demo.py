#!/usr/bin/env python3

import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from e2b import Sandbox

# 需要预先设置环境变量
if not os.getenv('E2B_DOMAIN'):
    raise RuntimeError('E2B_DOMAIN is required')
if not os.getenv('E2B_API_KEY'):
    raise RuntimeError('E2B_API_KEY is required')

KEEPALIVE_SECONDS = int(os.getenv("KEEPALIVE_SECONDS", "300"))

async def navigate_home(page, keyword):
    print(f"搜索玩具: {keyword}")
    for attempt in range(6):
        try:
            await page.goto("https://www.amazon.com/", wait_until='domcontentloaded', timeout=30000)
            return True
        except Exception as e:
            print(f"第{attempt+1}次加载主页超时，继续等待: {e}")
            await page.wait_for_timeout(1000)
    return False

async def find_search_input(page):
    selectors = [
        '#twotabsearchtextbox',
        'input[name="field-keywords"]',
        '#nav-search-bar-form input[type="text"]'
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                return el
        except:
            continue
    return None

async def perform_search(page, search_input, keyword):
    if not search_input:
        print("找不到搜索框")
        return False
    await search_input.fill("")
    await search_input.fill(keyword)
    button_selectors = [
        '#nav-search-submit-button',
        'input[type="submit"][value="Go"]',
        '.nav-search-submit input'
    ]
    for selector in button_selectors:
        try:
            btn = await page.query_selector(selector)
            if btn:
                await btn.click()
                return True
        except:
            continue
    await page.keyboard.press("Enter")
    return True

async def wait_for_results(page):
    print("等待搜索结果加载...")
    for attempt in range(6):
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=10000)
            await page.wait_for_selector('[data-component-type="s-search-result"], .s-result-item', timeout=10000)
            elems = await page.query_selector_all('[data-component-type="s-search-result"], .s-result-item')
            if elems:
                print(f"✅ 第{attempt + 1}次检查：找到 {len(elems)} 个商品")
                return elems
        except Exception:
            pass
        await page.wait_for_timeout(10000)
    return []

async def get_product_elements(page):
    selectors = [
        '[data-component-type="s-search-result"]',
        '.s-result-item',
        '.sg-col-inner .s-widget-container'
    ]
    for selector in selectors:
        try:
            elems = await page.query_selector_all(selector)
            if elems:
                print(f"使用选择器: {selector}, 找到 {len(elems)} 个商品")
                return elems
        except:
            continue
    return []

async def pick_candidate(elements):
    candidate = None
    candidate_url = None
    for el in elements[:10]:
        try:
            for link_selector in [
                'h2 a[href]',
                'a[href*="/dp/"]',
                'a[href*="/gp/product/"]',
                '.s-link-style[href]',
                '.a-link-normal[href]'
            ]:
                le = await el.query_selector(link_selector)
                if not le:
                    continue
                href = await le.get_attribute('href')
                if href and href != '#' and ('/dp/' in href or '/gp/product/' in href):
                    candidate = el
                    candidate_url = href if href.startswith('http') else f"https://www.amazon.com{href}"
                    break
            if candidate_url:
                break
        except:
            continue
    return candidate, candidate_url

async def extract_title(first_element):
    title_selectors = [
        'h2 a span',
        '.s-size-mini .s-link-style a',
        'h2.s-size-mini span',
        '.s-title-instructions-style span'
    ]
    for selector in title_selectors:
        try:
            title_elem = await first_element.query_selector(selector)
            if title_elem:
                text = await title_elem.text_content()
                if text:
                    return text.strip()
        except:
            continue
    return ""

async def resolve_product_url(page, first_element):
    link_selectors = [
        'h2 a[href]',
        'a[href*="/dp/"]',
        'a[href*="/gp/product/"]',
        '.s-link-style[href]',
        '.a-link-normal[href]',
        'h2 a'
    ]
    link_elem = None
    for link_selector in link_selectors:
        try:
            link_elem = await first_element.query_selector(link_selector)
            if not link_elem:
                continue
            href = await link_elem.get_attribute('href')
            if href and href != '#' and ('/dp/' in href or '/gp/product/' in href):
                return href if href.startswith('http') else f"https://www.amazon.com{href}", False
        except:
            continue
    if link_elem:
        try:
            await link_elem.click()
            for attempt in range(3):
                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                    break
                except:
                    await page.wait_for_timeout(1000)
            product_url = page.url
            for attempt in range(3):
                try:
                    await page.go_back(wait_until='domcontentloaded')
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                    break
                except:
                    await page.wait_for_timeout(1000)
            return product_url, True
        except Exception as e:
            print(f"兜底点击解析URL失败: {e}")
    return None, False

async def retry_resolve_url(page):
    for attempt in range(6):
        await page.wait_for_timeout(10000)
        try:
            product_elements_retry = await page.query_selector_all('[data-component-type="s-search-result"], .s-result-item')
            if not product_elements_retry:
                continue
            first_element_retry = product_elements_retry[0]
            for link_selector in [
                'h2 a[href]',
                'a[href*="/dp/"]',
                'a[href*="/gp/product/"]',
                '.s-link-style[href]',
                '.a-link-normal[href]',
                'h2 a'
            ]:
                link_elem_retry = await first_element_retry.query_selector(link_selector)
                if link_elem_retry:
                    href = await link_elem_retry.get_attribute('href')
                    if href and href != '#' and ('/dp/' in href or '/gp/product/' in href):
                        return href if href.startswith('http') else f"https://www.amazon.com{href}"
        except Exception as e:
            print(f"重试解析URL第{attempt+1}次失败: {e}")
    return None


async def upload_and_import_cookies(browser_sandbox, page, local_cookies_file="cookie.json"):
    """从本地上传Amazon cookie文件到沙箱并导入"""
    try:
        # 检查本地cookie文件是否存在
        if not os.path.exists(local_cookies_file):
            print(f"本地Cookie文件不存在: {local_cookies_file}")
            return False, None

        with open(local_cookies_file, 'r', encoding='utf-8') as f:
            cookies_content = f.read()

        sandbox_cookies_path = "/home/user/amazon_cookies.json"
        browser_sandbox.files.write(sandbox_cookies_path, cookies_content)
        print(f"Cookie文件已上传到沙箱: {sandbox_cookies_path}")

        # 在沙箱中读取并解析cookies
        cookies_json = browser_sandbox.files.read(sandbox_cookies_path)
        cookies = json.loads(cookies_json)
        success = False
        for step in range(3):
            try:
                await page.goto("https://www.amazon.com", wait_until='domcontentloaded', timeout=10000)
                success = True
                break
            except Exception:
                await page.wait_for_timeout(1000)
        if not success:
            return False, None
        if not success:
            return False, None

        await page.context.add_cookies(cookies)
        print(f"成功导入cookies")
        return True, page

    except Exception as e:
        print(f"上传和导入cookies失败: {e}")
        return False, None

async def search_toys(page, keyword="toys"):
    """搜索玩具商品：使用模块级独立函数进行编排，便于复用与单测"""
    try:
        if not await navigate_home(page, keyword):
            return []

        search_input = await find_search_input(page)
        await perform_search(page, search_input, keyword)

        await wait_for_results(page)

        products = []
        product_elements = await get_product_elements(page)
        if not product_elements:
            print("未找到商品列表")
            return []

        await page.wait_for_timeout(500)

        try:
            candidate, _ = await pick_candidate(product_elements)
            first_element = candidate or product_elements[0]
            title_text = await extract_title(first_element)

            product_url, _clicked = await resolve_product_url(page, first_element)
            if not product_url:
                product_url = await retry_resolve_url(page)

            if product_url:
                products.append({
                    'title': (title_text or '').strip(),
                    'url': product_url
                })
                print(f"✅ 第一个商品: {(title_text or '').strip()[:80]} | {product_url}")
            else:
                print("⚠️ 未能解析第一个商品的URL，已重试 1 分钟仍失败")
        except Exception as e:
            print(f"解析第一个商品时出错: {e}")

        return products

    except Exception as e:
        print(f"搜索商品出错: {e}")
        return []


async def add_to_cart(page, product_url):
    """将商品加入购物车"""
    try:
        # 访问商品详情页：保持使用 domcontentloaded，并简洁重试 3 次
        success_nav = False
        for _ in range(3):
            try:
                await page.goto(product_url, wait_until='domcontentloaded', timeout=30000)
                success_nav = True
                break
            except Exception:
                await page.wait_for_timeout(1000)
        if not success_nav:
            return False
        await page.wait_for_timeout(1500)
        cart_button_selectors = [
            '#add-to-cart-button',
            'input[name="submit.add-to-cart"]',
            '#addToCart',
            '.a-button-input[aria-labelledby="submit.add-to-cart-announce"]'
        ]

        cart_button = None
        for selector in cart_button_selectors:
            try:
                cart_button = await page.query_selector(selector)
                if cart_button:
                    # 检查按钮是否可见和可点击
                    is_visible = await cart_button.is_visible()
                    is_enabled = await cart_button.is_enabled()
                    if is_visible and is_enabled:
                        print(f"找到购物车按钮: {selector}")
                        break
                    else:
                        cart_button = None
            except:
                continue

        # 在 domcontentloaded 后，若找不到加车按钮，则每 10s 重试一次，最多 1 分钟
        if not cart_button:
            for attempt in range(6):
                await page.wait_for_timeout(10000)
                try:
                    await page.evaluate("window.scrollBy(0, 600)")
                except:
                    pass
                for selector in cart_button_selectors:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            is_visible = await elem.is_visible()
                            is_enabled = await elem.is_enabled()
                            if is_visible and is_enabled:
                                cart_button = elem
                                print(f"✅ 重试第{attempt+1}次找到加入购物车按钮: {selector}")
                                break
                    except:
                        continue
                if cart_button:
                    break
            if not cart_button:
                print("找不到可用的购物车按钮")
                return False

        # 点击加入购物车
        try:
            await cart_button.click()
        except Exception:
            # 若点击异常，轻微滚动并重试一次
            try:
                await page.evaluate("window.scrollBy(0, 400)")
            except:
                pass
            await page.wait_for_timeout(500)
            await cart_button.click()

        # 成功检测：每 10 秒重试一次，最多 1 分钟
        success_indicators = [
            '#attachDisplayAddBaseAlert',
            '#sw-atc-details-single-container',
            '.a-alert-success',
            'h1:has-text("Added to Cart")',
            '[data-csa-c-content-id="sw-atc"]'
        ]
        success = False
        for _ in range(6):
            # 先检查 URL 变化
            current_url = page.url
            if "cart" in current_url.lower() or "added-to-cart" in current_url.lower():
                success = True
                break
            # 再检查页面指示器
            found = False
            for selector in success_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        found = True
                        break
                except:
                    continue
            if found:
                success = True
                break
            await page.wait_for_timeout(10000)

        print("商品已成功加入购物车!" if success else "可能已加入购物车，但无法确认")
        return True if success else True

    except Exception as e:
        print(f"加入购物车出错: {e}")
        return False


async def view_cart(page):
    """查看购物车"""
    try:
        # 访问购物车页面：保持使用 domcontentloaded
        success = False
        for _ in range(3):
            try:
                await page.goto("https://www.amazon.com/gp/cart/view.html", wait_until='domcontentloaded', timeout=30000)
                success = True
                break
            except Exception:
                await page.wait_for_timeout(1000)
        if not success:
            return []
        await page.wait_for_timeout(1500)

        print(f"成功访问购物车页面: {page.url}")
        cart_items = []
        item_selectors = [
            '[data-name="Active Items"] [data-item-index]',
            '.sc-list-item[data-item-index]',
            '[data-asin][data-item-index]',
            '.sc-list-item-content',
            '#sc-active-cart .sc-list-item',
            '.a-spacing-mini[data-asin]'
        ]

        # 在 domcontentloaded 后，若未解析到商品，则每 10s 重试一次，最多 1 分钟
        items = []
        for attempt in range(6):
            for selector in item_selectors:
                try:
                    items = await page.query_selector_all(selector)
                    if items and len(items) > 0:
                        print(f"找到购物车商品选择器: {selector}, 数量: {len(items)}")
                        return items
                    else:
                        # 本次尝试该选择器未找到
                        pass
                except Exception as e:
                    print(f"尝试选择器 {selector} 失败: {e}")
                    continue
            # 若本轮所有选择器都未找到，等待 10s 后重试
            print(f"未解析到购物车商品，等待 10s 后重试（第 {attempt+1}/6 次）")
            await page.wait_for_timeout(10000)

        if not items:
            print("购物车为空或无法解析商品（已重试 1 分钟）")
            return []

    except Exception as e:
        print(f"查看购物车出错: {e}")
        return []


async def main():
    """主函数"""

    # 创建浏览器沙箱
    browser_sandbox = Sandbox.create(template="browser-v1", timeout=600)
    print(f"Browser沙箱已创建: {browser_sandbox.sandbox_id}")

    # 构建VNC和CDP连接URL
    novnc_url = f"https://{browser_sandbox.get_host(9000)}/novnc/vnc_lite.html?path=websockify&access_token={browser_sandbox._envd_access_token}"
    cdp_url = f"https://{browser_sandbox.get_host(9000)}/cdp"

    print(f"VNC实时查看链接: {novnc_url}")
    print("复制上面的链接到浏览器中，可以实时查看操作过程")

    try:
        async with async_playwright() as playwright:
            # 通过CDP协议连接到远程浏览器
            browser = await playwright.chromium.connect_over_cdp(
                cdp_url,
                headers={"X-Access-Token": str(browser_sandbox._envd_access_token)}
            )

            # 获取现有的上下文和页面
            context = browser.contexts[0]
            page = context.pages[0]

            # 步骤1: 从本地上传并导入Amazon cookies
            local_cookie_file = "cookie.json"
            cookies_imported = False
            if os.path.exists(local_cookie_file):

                cookies_imported, new_page = await upload_and_import_cookies(browser_sandbox, page, local_cookie_file)
                if new_page:  # 如果创建了新页面，使用新页面
                    page = new_page
            else:
                print(f"本地cookie文件不存在: {local_cookie_file}，将继续以访客模式执行")

            if not cookies_imported:
                print("Cookie未导入成功，继续以访客模式执行")

            # 步骤2: 搜索玩具
            toys = await search_toys(page, "dinosaur toys")

            if not toys:
                print("未找到玩具商品，程序退出")
                return

            # 步骤3: 自动将第一款玩具加入购物车
            if toys:
                first_toy = toys[0]
                # 加入购物车
                await add_to_cart(page, first_toy['url'])

            # 步骤4: 查看购物车
            cart_items = await view_cart(page)

            if cart_items:
                print(f"购物车中有 {len(cart_items)} 件商品")
            else:
                print("购物车为空")

            print("\nAmazon玩具购物流程完成!")
            print("您可以通过VNC链接查看浏览器状态，或手动完成后续操作")

            # 保持沙箱运行一段时间供查看
            if KEEPALIVE_SECONDS > 0:
                print(f"\n沙箱将保持运行 {KEEPALIVE_SECONDS} 秒，您可以手动操作...")
                await asyncio.sleep(KEEPALIVE_SECONDS)
            else:
                print("\nKEEPALIVE_SECONDS=0，跳过额外保活等待")

    except Exception as e:
        print(f"程序执行出错: {e}")

    finally:
        print("\n清理沙箱...")
        browser_sandbox.kill()


if __name__ == "__main__":
    asyncio.run(main())
