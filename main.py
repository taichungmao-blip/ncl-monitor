import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://www.ncl.com/in/en/vacations?cruise-port=hkg,inc,kee,sin,tok,yok&sort=price_low_high"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
LAST_SEEN_FILE = "last_seen.txt"

def send_discord_notification(title, price, link):
    if not DISCORD_WEBHOOK_URL:
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
    requests.post(DISCORD_WEBHOOK_URL, json=data)

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
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"前往: {URL}")
        driver.get(URL)
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//span[contains(text(), '$')]")))

        # 抓取第一個行程
        title_element = driver.find_element(By.CSS_SELECTOR, "h3, .title") 
        title = title_element.text.strip()
        
        # 尋找價格
        price_elements = driver.find_elements(By.XPATH, "//span[contains(text(), '$')]")
        target_price = 0
        price_str = ""
        found_valid_price = False

        import re
        for p in price_elements:
            text = p.text.strip().replace(',', '')
            if '$' in text and any(char.isdigit() for char in text):
                try:
                    num_str = re.search(r'\d+', text).group()
                    value = int(num_str)
                    if value > 0:
                        target_price = value
                        price_str = text
                        found_valid_price = True
                        break 
                except:
                    continue
        
        link = driver.current_url

        print(f"目前最便宜: {title} | 價格: {price_str}")

        if found_valid_price and target_price < 1000:
            last_seen_title = get_last_seen()
            
            # 比對邏輯：如果標題跟上次不一樣，才通知
            if title != last_seen_title:
                print("發現新行程！發送通知並更新紀錄...")
                send_discord_notification(title, price_str, link)
                save_last_seen(title) # 更新檔案
            else:
                print("這個行程上次已經通知過了，跳過。")
        else:
            print("價格未低於標準或未找到。")

    except Exception as e:
        print(f"錯誤: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    check_cruise()
