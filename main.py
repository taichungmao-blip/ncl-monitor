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

def send_discord_notification(title, price_str, link, old_price=None):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ 未設定 Discord Webhook")
        return
    
    # 建立通知訊息
    desc = f"目前價格: **{price_str}** (低於 $1000 USD)"
    if old_price and old_price > 0:
        desc += f"\n(上次價格: ${old_price})"

    data = {
        "content": "🚢 **NCL 郵輪價格/行程變動通知！**",
        "embeds": [{
            "title": title,
            "description": desc,
            "url": link,
            "color": 5814783 # 藍色
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
        print("✅ Discord 通知已發送")
    except Exception as e:
        print(f"❌ Discord 通知發送失敗: {e}")

def get_last_seen():
    """讀取上次的標題與價格，回傳 (title, price_int)"""
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            # 嘗試解析 "標題|價格" 格式
            if "|" in content:
                parts = content.split("|")
                # 取出標題和價格 (最後一個部分視為價格)
                title_part = "|".join(parts[:-1]) 
                try:
                    price_part = int(parts[-1])
                except:
                    price_part = 0
                return title_part, price_part
            else:
                # 兼容舊格式 (檔案裡只有標題)
                return content, 0
    return "", 0

def save_last_seen(title, price_int):
    """儲存格式：標題|價格整數"""
    with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
        f.write(f"{title}|{price_int}")

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

        # --- 1. 抓取標題 ---
        title = "未知行程"
        try:
            titles = driver.find_elements(By.XPATH, "//a[contains(@class, 'link') and contains(text(), 'Day')]")
            valid_titles = [t for t in titles if len(t.text) > 10]
            if valid_titles:
                title = valid_titles[0].text.strip()
            else:
                title_element = driver.find_element(By.CSS_SELECTOR, "h3")
                title = title_element.text.strip()
        except Exception:
            print("⚠️ 找不到標題元素")

        # --- 2. 抓取價格 (已過濾稅金) ---
        price_elements = driver.find_elements(By.XPATH, "//span[contains(text(), '$')]")
        lowest_price = 99999
        price_str = ""
        found_price = False

        print(f"🔎 掃描到 {len(price_elements)} 個價格標籤...")

        for p in price_elements:
            raw_text = p.text.strip()
            text_lower = raw_text.lower()
            
            # 過濾稅金關鍵字
            if "tax" in text_lower or "fee" in text_lower or "port" in text_lower or "expense" in text_lower:
                continue

            if '$' in raw_text:
                try:
                    num_list = re.findall(r'\d+', raw_text.replace(',', ''))
                    if num_list:
                        val = int(num_list[0])
                        # 只取大於100且目前最小的價格
                        if 100 < val < lowest_price:
                            lowest_price = val
                            price_str = raw_text
                            found_price = True
                except:
                    continue
        
        link = driver.current_url

        print(f"📊 分析結果 -> 標題: [{title}] | 最低船票價格: [{price_str}] (${lowest_price})")

        # --- 判斷邏輯更新 ---
        if found_price and lowest_price < 1000:
            last_title, last_price = get_last_seen()
            
            # 觸發條件：(標題不同) 或 (價格不同)
            if title != last_title or lowest_price != last_price:
                print(f"🎉 發現變化！(舊: {last_title} ${last_price} -> 新: {title} ${lowest_price})")
                
                # 發送通知，並傳入舊價格方便比較
                send_discord_notification(title, price_str, link, old_price=last_price)
                
                # 更新紀錄
                save_last_seen(title, lowest_price)
            else:
                print(f"💤 行程相同且價格未變 ({lowest_price})，跳過通知")
        else:
            print(f"❌ 未發送通知 (價格: ${lowest_price} >= 1000 或未找到)")

    except Exception as e:
        print(f"💀 發生錯誤: {e}")
        driver.save_screenshot("error_screenshot.png")
    finally:
        driver.quit()

if __name__ == "__main__":
    check_cruise()
