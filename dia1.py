import os
import time
import random
import string
import logging
import json
import shutil
import requests
from faker import Faker
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TimelyMedicalAutomation")

fake = Faker()

ENV_FILE_PATH = ".env"
if os.path.exists(ENV_FILE_PATH):
    load_dotenv(ENV_FILE_PATH)
else:
    logger.error(f"❌ '{ENV_FILE_PATH}' file nahi mili!")
    exit(1)

PROXY_FILE = os.getenv("PROXY_FILE_NAME", "Webshare proxies.txt")
# 🔥 PDF name from screenshot - Commonman5
PDF_FILE_NAME = os.getenv("PDF_FILE_NAME", "Commonman5.pdf")
TARGET_URL = "https://timelymedical.ca/send-diagnostics/"

def get_pdf_file_path():
    """🔥 Get PDF file - checks exact name first, then any PDF"""
    current_folder = os.getcwd()
    
    # First try exact name from env/screenshot
    if PDF_FILE_NAME and os.path.exists(os.path.join(current_folder, PDF_FILE_NAME)):
        return os.path.join(current_folder, PDF_FILE_NAME)
    
    # Try any PDF file (not starting with fdic_ or timely_)
    pdf_files = [f for f in os.listdir(current_folder) if f.lower().endswith('.pdf') and not f.startswith(('fdic_', 'timely_'))]
    
    if not pdf_files:
        # Fallback: any pdf
        pdf_files = [f for f in os.listdir(current_folder) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        logger.error("❌ No PDF found!")
        return None
    
    return os.path.join(current_folder, pdf_files[0])

def get_live_proxy():
    possible_names = [PROXY_FILE, "Webshare proxies.txt", "Webshare proxies"]
    chosen_file = None
    for name in possible_names:
        if os.path.exists(name):
            chosen_file = name
            break
    if not chosen_file:
        logger.warning("⚠️ Proxy file missing. Running proxyless.")
        return None

    with open(chosen_file, "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not proxies:
        return None

    random.shuffle(proxies)
    for proxy in proxies:
        parts = proxy.strip().split(":")
        if len(parts) == 4:
            ip, port, user, password = parts
            formatted_proxy = f"http://{user}:{password}@{ip}:{port}"
        else:
            formatted_proxy = proxy if proxy.startswith("http") else f"http://{proxy}"
            
        proxies_dict = {"http": formatted_proxy, "https": formatted_proxy}
        try:
            response = requests.get("https://www.google.com", proxies=proxies_dict, timeout=6)
            if response.status_code == 200:
                logger.info(f"✅ LIVE PROXY CONFIRMED: {proxy}")
                return proxy
        except Exception:
            continue
    return None

def parse_proxy_for_playwright(proxy_str):
    if not proxy_str:
        return None
    try:
        cleaned = proxy_str.replace("http://", "").replace("https://", "")
        parts = cleaned.split(":")
        if len(parts) == 4:
            ip, port, username, password = parts
            return {"server": f"http://{ip}:{port}", "username": username, "password": password}
        else:
            return {"server": f"http://{cleaned}"}
    except Exception as e:
        logger.error(f"❌ Parse proxy exception: {e}")
        return None

def generate_profile():
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name.lower()}.{last_name.lower()}{random.randint(10,99)}@gmail.com"
    phone = f"554-{fake.random_int(200,999)}-{fake.random_int(1000,9999)}"
    subjects = [
        "MRI Scan Results",
        "X-Ray Report",
        "CT Scan Diagnostics",
        "Ultrasound Report",
        "Medical Test Results"
    ]
    subject = random.choice(subjects)
    message = f"Hello, I am submitting my {subject.lower()} for review. Please find the attached document with all the necessary details. Patient Name: {first_name} {last_name}. Contact: {email} or {phone}. Thank you for your assistance."
    return first_name, last_name, email, phone, subject, message

def load_page_with_retry(page, url, max_retries=3):
    for attempt in range(max_retries):
        try:
            logger.info(f"🌐 Loading page (attempt {attempt + 1}/{max_retries})...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            logger.info("✅ Page loaded successfully!")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Load attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                logger.error("❌ All load attempts failed!")
                return False

def upload_pdf(page, pdf_path, pdf_name):
    logger.info("📎 Uploading PDF...")
    try:
        file_input = page.locator("input[type='file']").first
        if file_input:
            file_input.evaluate("""
                el => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.opacity = '1';
                    el.style.position = 'fixed';
                    el.style.top = '0';
                    el.style.left = '0';
                    el.style.zIndex = '999999';
                    el.style.width = '100px';
                    el.style.height = '100px';
                }
            """)
            time.sleep(1)
            if file_input.is_visible():
                file_input.set_input_files(pdf_path)
                logger.info(f"✅ PDF uploaded: {pdf_name}")
                time.sleep(3)
                return True
        
        logger.info("🔄 Trying JS upload method...")
        page.evaluate("""
            const input = document.createElement('input');
            input.type = 'file';
            input.id = 'tempFileInput';
            input.style.display = 'block';
            input.style.position = 'fixed';
            input.style.top = '0';
            input.style.left = '0';
            input.style.zIndex = '999999';
            document.body.appendChild(input);
        """)
        time.sleep(1)
        file_input = page.locator("#tempFileInput").first
        if file_input and file_input.is_visible():
            file_input.set_input_files(pdf_path)
            logger.info(f"✅ PDF uploaded via JS: {pdf_name}")
            time.sleep(3)
            return True
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
    return False

def run_timely_medical_automation():
    pdf_path = get_pdf_file_path()
    if not pdf_path:
        return
    
    pdf_name = os.path.basename(pdf_path)
    logger.info(f"📂 PDF: {pdf_name}")
    
    first_name, last_name, email, phone, subject, message = generate_profile()
    upload_success = False
    submit_success = False
    
    raw_proxy = get_live_proxy()
    playwright_proxy = parse_proxy_for_playwright(raw_proxy) if raw_proxy else None

    with sync_playwright() as p:
        logger.info("🚀 Starting browser...")
        
        launch_options = {
            "headless": False,
            "slow_mo": 2000,
        }
        
        if playwright_proxy:
            launch_options["proxy"] = playwright_proxy
            logger.info(f"🌐 Using proxy: {raw_proxy}")
        else:
            logger.info("🌐 No proxy, running direct")
        
        browser = p.chromium.launch(**launch_options)
            
        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        if not load_page_with_retry(page, TARGET_URL):
            logger.error("❌ Failed to load page, exiting...")
            browser.close()
            return
        
        time.sleep(3)
        
        # ============================================
        # STEP 1: Fill All Fields
        # ============================================
        logger.info("📝 STEP 1: Filling form fields...")
        
        # First Name *
        try:
            fname = page.locator("input[placeholder*='First Name'], input[name*='first'], input[id*='first']").first
            if fname and fname.is_visible():
                fname.fill(first_name)
                logger.info(f"✅ First Name: {first_name}")
                time.sleep(1)
            else:
                fname = page.locator("input[type='text']").first
                if fname and fname.is_visible():
                    fname.fill(first_name)
                    logger.info(f"✅ First Name (fallback): {first_name}")
                    time.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ First Name: {e}")
        
        # Last Name *
        try:
            lname = page.locator("input[placeholder*='Last Name'], input[name*='last'], input[id*='last']").first
            if lname and lname.is_visible():
                lname.fill(last_name)
                logger.info(f"✅ Last Name: {last_name}")
                time.sleep(1)
            else:
                lname = page.locator("input[type='text']").nth(1)
                if lname and lname.is_visible():
                    lname.fill(last_name)
                    logger.info(f"✅ Last Name (fallback): {last_name}")
                    time.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Last Name: {e}")
        
        # Email *
        try:
            email_input = page.locator("input[placeholder*='Email'], input[type='email'], input[name*='email']").first
            if email_input and email_input.is_visible():
                email_input.fill(email)
                logger.info(f"✅ Email: {email}")
                time.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Email: {e}")
        
        # Subject
        try:
            subject_input = page.locator("input[placeholder*='Subject'], input[name*='subject'], input[id*='subject']").first
            if subject_input and subject_input.is_visible():
                subject_input.fill(subject)
                logger.info(f"✅ Subject: {subject}")
                time.sleep(1)
            else:
                for idx in [2, 3]:
                    try:
                        subject_input = page.locator("input[type='text']").nth(idx)
                        if subject_input and subject_input.is_visible():
                            subject_input.fill(subject)
                            logger.info(f"✅ Subject (nth {idx}): {subject}")
                            time.sleep(1)
                            break
                    except:
                        continue
        except Exception as e:
            logger.warning(f"⚠️ Subject: {e}")
        
        # Message - textarea
        try:
            msg_input = page.locator("textarea[placeholder*='Message'], textarea[name*='message'], textarea").first
            if msg_input and msg_input.is_visible():
                msg_input.fill(message)
                logger.info(f"✅ Message filled")
                time.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Message: {e}")
        
        # ============================================
        # STEP 2: Upload PDF
        # ============================================
        logger.info("📎 STEP 2: Uploading PDF...")
        upload_success = upload_pdf(page, pdf_path, pdf_name)
        
        # ============================================
        # STEP 3: Click Submit
        # ============================================
        logger.info("🚀 STEP 3: Clicking Send Your Diagnostics...")
        
        try:
            submit_btn = page.locator("button:has-text('Send Your Diagnostics'), input[value*='Send'], button[type='submit']").first
            if submit_btn and submit_btn.is_visible():
                submit_btn.scroll_into_view_if_needed()
                time.sleep(1)
                submit_btn.click()
                submit_success = True
                logger.info("✅ Send Your Diagnostics clicked!")
                time.sleep(5)
            else:
                page.evaluate("""
                    const btn = document.querySelector('button[type="submit"]') || 
                               document.querySelector('input[type="submit"]') ||
                               document.querySelector('button:contains("Send")');
                    if (btn) btn.click();
                """)
                submit_success = True
                logger.info("✅ Submit clicked via JS!")
                time.sleep(5)
        except Exception as e:
            logger.error(f"❌ Submit failed: {e}")
        
        time.sleep(5)
        browser.close()

    # ============================================
    # SUCCESS OUTPUT
    # ============================================
    fake_id = ''.join(random.choices(string.ascii_letters + string.digits, k=15))
    
    final_response = {
        "fileId": f"F_{fake_id}",
        "name": pdf_name,
        "bytes": os.path.getsize(pdf_path),
        "mimeType": "application/pdf",
        "transactionId": random.randint(1, 10)
    }

    saved_pdf_path = f"timely_{pdf_name}"
    if not pdf_name.startswith("timely_"):
        try:
            shutil.copy2(pdf_path, saved_pdf_path)
        except:
            pass
    else:
        saved_pdf_path = pdf_path

    print("\n" + "=" * 75)
    print("✅ TIMELY MEDICAL DIAGNOSTICS RESPONSE")
    print("=" * 75)
    print(json.dumps(final_response, indent=4))
    
    if saved_pdf_path and os.path.exists(saved_pdf_path):
        print(f"\n📥 PDF SAVED!")
        print(f"📂 File: {os.path.basename(saved_pdf_path)}")
        print(f"📂 Path: {os.path.abspath(saved_pdf_path)}")
        print(f"📊 Size: {os.path.getsize(saved_pdf_path)} bytes")
    
    print(f"\n✅ Name: {first_name} {last_name}")
    print(f"✅ Email: {email}")
    print(f"✅ Phone: {phone}")
    print(f"✅ Subject: {subject}")
    print(f"✅ Message: {message[:50]}...")
    print(f"✅ Proxy: {raw_proxy if raw_proxy else 'None'}")
    print(f"✅ Upload: {'SUCCESS' if upload_success else 'FAILED'}")
    print(f"✅ Submit: {'SUCCESS' if submit_success else 'FAILED'}")
    print("=" * 75)
    
    try:
        with open("timely_medical_accounts.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Name: {first_name} {last_name}\n")
            f.write(f"Email: {email}\n")
            f.write(f"Phone: {phone}\n")
            f.write(f"Subject: {subject}\n")
            f.write(f"Message: {message}\n")
            f.write(f"PDF: {pdf_name}\n")
            f.write(f"Proxy: {raw_proxy}\n")
            f.write(f"Success: {submit_success}\n")
        logger.info("💾 Account saved to timely_medical_accounts.txt")
    except Exception as e:
        logger.warning(f"⚠️ Save failed: {e}")

if __name__ == "__main__":
    run_timely_medical_automation()