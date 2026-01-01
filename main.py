import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 設定目標網址
URL = "https://www.ncl.com/in/en/vacations?cruise-port=hkg,inc,kee,sin,tok,yok&sort=price_low_high"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
LAST_SEEN_FILE = "last_seen.txt"

def send_discord_notification(title, price, link):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ 未設定 Discord Webhook")
        return
    data = {
        "content": "🚢 **發現新的 NCL 亞洲特價郵輪！**",
        "embeds": [{
            "title": title,
            "description": f"價格: **{price}** (低於 $1000 USD)",
            "url": link,
            "color": 5814783
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
        print("✅ Discord 通知已發送")
    except Exception as e:
        print(f"❌ Discord 通知發送失敗: {e}")

def get_last_seen():
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_seen(title):
    with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
        f.write(title)

def check_cruise():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") # 使用新版 Headless 模式
    chrome_options.add_argument("--window-size=1920,1080") # 設定大視窗，避免變成手機版
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") # 嘗試避開偵測
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"🚀 前往: {URL}")
        driver.get(URL)
        
        # 1. 模擬人類捲動 (很多網站不捲動不會載入資料)
        print("⏳ 等待並捲動頁面...")
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(5) # 強制等待 JS 渲染

        # 2. 保存 HTML 以便除錯 (如果失敗，我們可以查看這個檔案)
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        # 3. 嘗試多種方式尋找卡片
        # NCL 的卡片通常會有 "view-cruise-btn" 或者是列表項目
        wait = WebDriverWait(driver, 15)
        
        # 策略 A: 找尋含有 'Day' 的標題連結 (通常行程標題是 "X-Day Asia...")
        try:
            # 尋找所有可能是標題的元素
            titles = driver.find_elements(By.XPATH, "//a[contains(@class, 'link') and contains(text(), 'Day')]")
            # 過濾掉太短的文字
            valid_titles = [t for t in titles if len(t.text) > 10]
            
            if valid_titles:
                title_element = valid_titles[0]
                title = title_element.text.strip()
            else:
                # 策略 B: 嘗試找 h3 (備用)
                title_element = driver.find_element(By.CSS_SELECTOR, "h3")
                title = title_element.text.strip()
        except Exception:
            print("⚠️ 找不到標題元素")
            title = "未知行程"

        # 策略: 抓取價格
        # 抓取頁面上所有顯示價格的地方，找出最小的那個
        price_elements = driver.find_elements(By.XPATH, "//span[contains(text(), '$')]")
        
        lowest_price = 99999
        price_str = ""
        found_price = False

        print(f"🔎 掃描到 {len(price_elements)} 個價格標籤...")

        for p in price_elements:
            text = p.text.strip().replace(',', '')
            # 確保格式像 $799 而不是其他文字
            if '$' in text:
                try:
                    # 提取數字
                    num_list = re.findall(r'\d+', text)
                    if num_list:
                        val = int(num_list[0])
                        # 過濾掉明顯不合理的價格 (例如 $0 或太小的雜訊)
                        if 100 < val < lowest_price:
                            lowest_price = val
                            price_str = text
                            found_price = True
                except:
                    continue
        
        link = driver.current_url

        print(f"📊 分析結果 -> 標題: [{title}] | 最低價格: [{price_str}] (${lowest_price})")

        if found_price and lowest_price < 1000:
            last_seen_title = get_last_seen()
            
            if title != last_seen_title:
                print("🎉 條件符合！準備發送通知...")
                send_discord_notification(title, price_str, link)
                save_last_seen(title)
            else:
                print("💤 此行程上次已通知過")
        else:
            print("❌ 價格未低於標準 ($1000) 或未找到有效價格")

    except Exception as e:
        print(f"💀 發生錯誤: {e}")
        driver.save_screenshot("error_screenshot.png")
    finally:
        driver.quit()

if __name__ == "__main__":
    check_cruise()
