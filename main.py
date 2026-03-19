import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# 設定目標網址
URL = "https://www.ncl.com/in/en/vacations?cruise-port=hkg,inc,kee,sin,tok,yok&sort=price_low_high"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
LAST_SEEN_FILE = "last_seen.txt"

def send_discord_notification(main_dest, cruise_info, departure, price_str, link, old_price=None):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ 未設定 Discord Webhook")
        return
    
    # 建立通知訊息，增加行程資訊排版
    desc = f"**🚢 行程資訊:** {cruise_info}\n"
    desc += f"**📍 出發地點:** {departure}\n"
    desc += f"**💰 目前價格: {price_str}** (低於 $1000 USD)"
    
    if old_price and old_price > 0:
        desc += f"\n📉 (上次價格: ${old_price})"

    data = {
        "content": "🚢 **NCL 郵輪價格/行程變動通知！**",
        "embeds": [{
            "title": main_dest, # 顯示主要目的地 (例如: Southern Africa...)
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
            if "|" in content:
                parts = content.split("|")
                title_part = "|".join(parts[:-1]) 
                try:
                    price_part = int(parts[-1])
                except:
                    price_part = 0
                return title_part, price_part
            else:
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

        # --- 1. 抓取行程詳細資訊 (根據提供的 HTML 結構) ---
        main_dest = "未知目的地"
        cruise_info = "未知天數與船名"
        departure = "未知出發地"

        try:
            # 抓取主要目的地 (e.g., Southern Africa: Maldives...)
            main_dest = driver.find_element(By.CSS_SELECTOR, ".c66_title h2").text.strip()
            # 抓取天數與船名 (e.g., 16-day Cruise on Norwegian Sun)
            cruise_info = driver.find_element(By.CSS_SELECTOR, ".c66_label h2").text.strip()
            # 抓取出發地 (e.g., from Singapore, Singapore)
            departure = driver.find_element(By.CSS_SELECTOR, ".c66_subtitle h3").text.strip()
        except Exception as e:
            print(f"⚠️ 找不到部分標題元素: {e}")
            # 保留基本的 Fallback
            try:
                main_dest = driver.find_element(By.CSS_SELECTOR, "h3").text.strip()
            except:
                pass

        # --- 2. 抓取價格 (已過濾稅金) ---
        price_elements = driver.find_elements(By.XPATH, "//span[contains(text(), '$')]")
        lowest_price = 99999
        price_str = ""
        found_price = False

        print(f"🔎 掃描到 {len(price_elements)} 個價格標籤...")

        for p in price_elements:
            raw_text = p.text.strip()
            text_lower = raw_text.lower()
            
            if "tax" in text_lower or "fee" in text_lower or "port" in text_lower or "expense" in text_lower:
                continue

            if '$' in raw_text:
                try:
                    num_list = re.findall(r'\d+', raw_text.replace(',', ''))
                    if num_list:
                        val = int(num_list[0])
                        if 100 < val < lowest_price:
                            lowest_price = val
                            price_str = raw_text
                            found_price = True
                except:
                    continue
        
        link = driver.current_url

        # 將主要目的地與船名組合作為紀錄的唯一標識
        title_for_record = f"{main_dest} | {cruise_info}"
        print(f"📊 分析結果 -> 行程: [{title_for_record}] | 最低船票價格: [{price_str}] (${lowest_price})")

        # --- 判斷邏輯更新 ---
        if found_price and lowest_price < 1000:
            last_title, last_price = get_last_seen()
            
            if title_for_record != last_title or lowest_price != last_price:
                print(f"🎉 發現變化！(舊: ${last_price} -> 新: ${lowest_price})")
                
                # 發送通知，傳入所有新抓取的資訊
                send_discord_notification(main_dest, cruise_info, departure, price_str, link, old_price=last_price)
                
                save_last_seen(title_for_record, lowest_price)
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
