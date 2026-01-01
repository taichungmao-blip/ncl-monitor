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
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"🚀 前往: {URL}")
        driver.get(URL)
        
        print("⏳ 等待並捲動頁面...")
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(5) 

        # 保存 HTML 以便除錯
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        # --- 1. 抓取標題 ---
        title = "未知行程"
        try:
            # 尋找行程標題 (優先找包含 'Day' 的連結)
            titles = driver.find_elements(By.XPATH, "//a[contains(@class, 'link') and contains(text(), 'Day')]")
            valid_titles = [t for t in titles if len(t.text) > 10]
            
            if valid_titles:
                title = valid_titles[0].text.strip()
            else:
                # 備用方案：找 h3
                title_element = driver.find_element(By.CSS_SELECTOR, "h3")
                title = title_element.text.strip()
        except Exception:
            print("⚠️ 找不到標題元素")

        # --- 2. 抓取價格 (重點修正部分) ---
        price_elements = driver.find_elements(By.XPATH, "//span[contains(text(), '$')]")
        
        lowest_price = 99999
        price_str = ""
        found_price = False

        print(f"🔎 掃描到 {len(price_elements)} 個價格標籤，開始過濾...")

        for p in price_elements:
            raw_text = p.text.strip()
            text_lower = raw_text.lower()
            
            # --- 過濾邏輯 ---
            # 如果文字中包含 'tax', 'fee', 'expense' (稅費) 就跳過
            if "tax" in text_lower or "fee" in text_lower or "port" in text_lower or "expense" in text_lower:
                continue

            # 確保格式像 $799
            if '$' in raw_text:
                try:
                    # 提取數字
                    num_list = re.findall(r'\d+', raw_text.replace(',', ''))
                    if num_list:
                        val = int(num_list[0])
                        # 設定合理價格區間 (大於 100 且小於目前的最低價)
                        # 這邊特別把 lowest_price 的判斷加進來，只抓取"最小的船票價格"
                        if 100 < val < lowest_price:
                            lowest_price = val
                            price_str = raw_text
                            found_price = True
                except:
                    continue
        
        link = driver.current_url

        print(f"📊 分析結果 -> 標題: [{title}] | 最低船票價格: [{price_str}] (${lowest_price})")

        if found_price and lowest_price < 1000:
            last_seen_title = get_last_seen()
            
            # 為了避免因為標題相同但價格變動而漏發，或是單純只看標題
            # 這裡維持「標題不同才通知」的邏輯。如果你希望「標題相同但價格變便宜」也通知，可以修改這裡。
            if title != last_seen_title:
                print("🎉 條件符合！準備發送通知...")
                send_discord_notification(title, price_str, link)
                save_last_seen(title)
            else:
                print("💤 此行程上次已通知過")
        else:
            print(f"❌ 未發送通知 (價格: ${lowest_price} >= 1000 或未找到)")

    except Exception as e:
        print(f"💀 發生錯誤: {e}")
        driver.save_screenshot("error_screenshot.png")
    finally:
        driver.quit()

if __name__ == "__main__":
    check_cruise()
