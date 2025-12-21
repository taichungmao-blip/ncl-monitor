import time
import re
import datetime
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ================= 設定區 =================
# 鎖定亞洲 + 價格排序
TARGET_URL = "https://www.ncl.com/vacations?cruise-destination=asia&sortBy=price&autoPopulate=f&from=resultpage"

# 您的 Discord Webhook
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

# [關鍵設定] 通知門檻：低於此價格才通知 (美金)
NOTIFY_THRESHOLD = 1000 

def setup_driver():
    options = Options()
    # GitHub Actions 必須使用無頭模式
    options.add_argument("--headless=new") 
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'eager'
    
    # 偽裝 User-Agent (避免被擋)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Linux 環境必要參數 (避免崩潰)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver

def force_close_modal(driver):
    try:
        time.sleep(2)
        buttons = driver.find_elements(By.CSS_SELECTOR, "a.c230_close, button.close, i.nis-times")
        if buttons: driver.execute_script("arguments[0].click();", buttons[0])
    except: pass

def get_price_from_card(card):
    try:
        # [策略 1] CSS 定位
        price_elements = card.find_elements(By.CSS_SELECTOR, ".headline-3, span[data-code='price']")
        if price_elements:
            for p_el in price_elements:
                txt = p_el.text.strip().replace(",", "").replace("$", "")
                if txt and re.match(r'^\d+$', txt):
                    return int(txt), "CSS"

        # [策略 2] 全文分析
        card_text = card.text
        lines = card_text.split('\n')
        candidates = []
        exclude_keywords = ['save', 'off', 'discount', '節省', '割引', 'avg', 'day']
        
        for line in lines:
            if any(k in line.lower() for k in exclude_keywords): continue
            found = re.findall(r'\$([\d,]+)|([\d,]+)\s*USD', line)
            for f in found:
                p_str = f[0] if f[0] else f[1]
                try:
                    val = int(p_str.replace(",", ""))
                    # 亞洲航線下限設為 200，避免抓到雜訊
                    if val > 200 and val not in [2025, 2026, 2027, 2028]:
                        candidates.append(val)
                except: pass
        
        if candidates:
            return max(candidates), "TextScan"

    except: pass
    return 0, "Fail"

def send_discord_alert(items):
    """
    智慧通知：只發送符合「破盤價」條件的行程
    """
    # 1. 先排序
    items.sort(key=lambda x: x[1])
    
    # 2. 過濾：只保留低於門檻的行程
    deals = [item for item in items if item[1] < NOTIFY_THRESHOLD]
    
    print(f"📊 分析報告：")
    print(f"   - 全網最低價: ${items[0][1] if items else 'N/A'}")
    print(f"   - 設定門檻值: < ${NOTIFY_THRESHOLD}")
    
    if not deals:
        print(f"   🤐 結論：目前最低價 (${items[0][1]}) 未低於 ${NOTIFY_THRESHOLD}，不發送 Discord 通知。")
        return

    print(f"   🚨 結論：發現 {len(deals)} 筆破盤價！正在發送警報...")

    # 取前 3 名發送
    top_deals = deals[:3]
    
    embed = {
        "title": f"🚨 發現破盤價！亞洲郵輪低於 ${NOTIFY_THRESHOLD}",
        "description": f"監測系統發現了 {len(deals)} 筆超低價行程，快搶！",
        "color": 15548997, # 紅色緊急警報
        "footer": {
            "text": f"掃描時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        },
        "fields": []
    }

    for item in top_deals:
        title, price, date, link, _ = item
        embed["fields"].append({
            "name": f"🔥 ${price} USD - {title}",
            "value": f"📅 日期: {date}\n🔗 [點擊搶購]({link})",
            "inline": False
        })

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"username": "NCL Sniper Bot", "embeds": [embed]})
        print("✅ Discord 警報已發送！")
    except Exception as e:
        print(f"❌ Discord 發送錯誤: {e}")

def run_ncl_sniper():
    print(f"🚀 啟動 NCL 亞洲破盤價監控 (V28: Sniper Mode)...")
    print(f"🎯 目標：亞洲航線 < ${NOTIFY_THRESHOLD} USD")
    
    driver = setup_driver()
    results = []

    try:
        driver.get(TARGET_URL)
        force_close_modal(driver)
        time.sleep(5)
        
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(2)
        
        cards = driver.find_elements(By.CSS_SELECTOR, "article, li.slide")
        print(f"🔍 掃描中... (共 {len(cards)} 區塊)")
        
        for card in cards:
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", card)
                
                title = "Unknown"
                title_els = card.find_elements(By.CSS_SELECTOR, "h2, .c729_body_title, .headline-2")
                if title_els: title = title_els[0].text.strip()
                if not title or len(title) < 5: continue

                price, method = get_price_from_card(card)
                
                date_text = "Unknown"
                date_els = card.find_elements(By.CSS_SELECTOR, ".c282_list_item, .e34")
                if date_els: date_text = date_els[0].text.replace("\n", " ")
                
                link = ""
                link_els = card.find_elements(By.TAG_NAME, "a")
                for l in link_els:
                    href = l.get_attribute("href")
                    if href and "/cruises/" in href:
                        link = href
                        break

                if price > 0:
                    # 只有當真的抓到價格時才加入清單
                    results.append([title, price, date_text, link, method])
                
            except: continue

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.quit()

    if results:
        send_discord_alert(results)
    else:
        print("⚠️ 未抓取到有效資料。")

if __name__ == "__main__":
    run_ncl_sniper()
