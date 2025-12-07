from flask import Flask, render_template, request, jsonify
import random
import string
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from queue import Queue
import uuid
from threading import Semaphore
import json
import os
from datetime import datetime

from spotify_aio import spotify_bp
from tiktok_aio import tiktok_bp
from instagram_aio import instagram_bp
from discord_selenium_aio import discord_bp
from roblox_selenium_aio import roblox_bp

app = Flask(__name__)
app.register_blueprint(spotify_bp)
app.register_blueprint(tiktok_bp)
app.register_blueprint(instagram_bp)
app.register_blueprint(discord_bp)
app.register_blueprint(roblox_bp)
browser_semaphore = Semaphore(5)  # Limit to 5 concurrent browsers

# Main routes
@app.route('/')
def home():
    return render_template('launcher.html')

@app.route('/launcher')
def launcher():
    return render_template('launcher.html')

@app.route('/spotify-viewer')
def spotify_viewer():
    """Spotify Live Screen Viewer"""
    return render_template('spotify_viewer.html')

bot_status = {}
drivers = []
check_jobs = {}
job_lock = threading.Lock()
bot_names = {}
leaderboard = {}
tiktok_jobs = {}
bot_drivers = {}  # Store driver refs for video capture
flooder_active = False
flooder_games = {}  # {game_pin: {code, bot_count, driver, bot_drivers}}
flooder_thread = None
flooder_bot_drivers = {}  # Keep flooder bots alive
flooder_status = {"status": "Idle", "games_created": 0, "bots_joined": 0, "current_game": None}
successful_bots = 0  # Track successful joins
target_bots = 0  # Target number of successful bots
bot_buffer_lock = threading.Lock()  # Lock for tracking successful joins

def generate_random_username(length=8, custom_prefix=""):
    if custom_prefix:
        chars = string.ascii_letters + string.digits
        return custom_prefix + ''.join(random.choice(chars) for _ in range(length))
    chars = string.ascii_letters + string.digits
    return 'Sex' + ''.join(random.choice(chars) for _ in range(length))

def launch_browser():
    """Launch browser with semaphore to prevent resource exhaustion"""
    browser_semaphore.acquire()  # Wait if too many browsers already running
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        
        driver = webdriver.Chrome(options=options)
        drivers.append(driver)
        return driver
    except Exception as e:
        browser_semaphore.release()
        raise e

def wait_for_clickable(driver, by, locator, timeout=8, retries=3):
    for attempt in range(retries):
        try:
            wait = WebDriverWait(driver, timeout, poll_frequency=0.1)
            element = wait.until(EC.element_to_be_clickable((by, locator)))
            return element
        except:
            time.sleep(0.3)
    raise Exception(f"Element {locator} not clickable after {retries} retries")

def join_bot_with_buffer(game_pin: str, bot_number: int, custom_prefix: str = "", target: int = 10):
    """Join bot with buffer - stop trying if we've reached target"""
    global bot_status, bot_names, bot_drivers, successful_bots, target_bots, bot_buffer_lock, browser_semaphore
    
    # Check if we've already reached target
    with bot_buffer_lock:
        if successful_bots >= target:
            bot_status[bot_number] = "Skipped (target reached)"
            return
    
    driver = None
    try:
        bot_status[bot_number] = "Launching browser..."
        driver = launch_browser()
        bot_drivers[bot_number] = driver
        
        driver.get("https://www.kahoot.it")

        # Enter Game PIN
        bot_status[bot_number] = "Entering Game PIN..."
        game_input = wait_for_clickable(driver, By.ID, "game-input")
        game_input.clear()
        game_input.send_keys(game_pin)
        game_input.send_keys(Keys.ENTER)

        # Click Join
        bot_status[bot_number] = "Clicking Join button..."
        join_button = wait_for_clickable(driver, By.CSS_SELECTOR, "main div form button")
        driver.execute_script("arguments[0].click();", join_button)

        # Enter nickname
        bot_status[bot_number] = "Entering nickname..."
        nickname_input = wait_for_clickable(driver, By.CSS_SELECTOR, "#nickname")
        nickname = generate_random_username(custom_prefix=custom_prefix)
        nickname_input.clear()
        nickname_input.send_keys(nickname)
        nickname_input.send_keys(Keys.ENTER)
        
        bot_names[bot_number] = nickname
        bot_status[bot_number] = f"✓ Joined as {nickname}"
        
        # Increment successful count
        with bot_buffer_lock:
            successful_bots += 1

        # Keep running
        while True:
            time.sleep(10)

    except Exception as e:
        bot_status[bot_number] = f"✗ Error: {str(e)}"
        if driver:
            try:
                driver.quit()
            except:
                pass
        browser_semaphore.release()
    finally:
        # Try to keep the loop going
        if bot_status.get(bot_number, "").startswith("✗"):
            while True:
                time.sleep(10)

def join_bot(game_pin: str, bot_number: int, custom_prefix: str = ""):
    """Legacy join_bot for compatibility"""
    join_bot_with_buffer(game_pin, bot_number, custom_prefix, 1)

@app.route('/')
def launcher_home():
    return render_template('launcher.html')

@app.route('/kahoot')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    return render_template('status.html')

@app.route('/game-generator')
def game_generator():
    return render_template('game_generator.html')

def create_and_extract_game_pin():
    """GitHub exact implementation - creates game and extracts PIN"""
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(20)
        
        # Open the Kahoot game page
        driver.get("https://play.kahoot.it/v2/?quizId=a13d166b-c332-4085-a8c5-9e15321b7024")
        
        wait = WebDriverWait(driver, 20)
        
        # CLICK COOKIE BUTTON
        try:
            cookie_button = wait.until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            cookie_button.click()
        except:
            pass
        
        # CLICK FIRST BUTTON
        try:
            first_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".button__Button-sc-c6mvr2-0.iVnhsJ")
                )
            )
            first_btn.click()
        except:
            pass
        
        # CLICK START BUTTON
        try:
            start_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".fluid-button__Button-sc-1jrnqsz-2.ejFPvE.start-button__Button-sc-7wankj-12.hfmKJH")
                )
            )
            start_btn.click()
        except:
            pass
        
        # READ THE GAME PIN
        try:
            pin_parts = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "button[data-functional-selector='game-pin'] span")
                )
            )
            game_pin = "".join([part.text for part in pin_parts])
            
            if game_pin:
                return game_pin, driver
        except:
            pass
        
        driver.quit()
        return None, None
            
    except Exception as e:
        if driver:
            try:
                driver.quit()
            except:
                pass
        return None, None

@app.route('/api/generate-game', methods=['POST'])
def generate_game():
    try:
        game_pin, driver = create_and_extract_game_pin()
        
        if game_pin and driver:
            driver.quit()
            return jsonify({
                "success": True,
                "pin": game_pin,
                "message": f"Game PIN: {game_pin}"
            })
        
        # If no PIN found, return error
        return jsonify({
            "success": False,
            "error": "Could not extract game PIN"
        }), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

def flooder_worker():
    """Flooder - creates 30s games and fills with 10 bots via dashboard joiner"""
    global flooder_active, flooder_games, flooder_bot_drivers, flooder_status
    
    game_count = 0
    bot_count = 0
    
    while flooder_active:
        try:
            flooder_status["status"] = f"🎮 Creating game #{game_count + 1}..."
            flooder_status["games_created"] = game_count
            flooder_status["bots_joined"] = bot_count
            
            # Create game using exact working code
            game_pin, game_driver = create_and_extract_game_pin()
            
            if game_pin and game_driver:
                game_count += 1
                flooder_games[game_pin] = {
                    "code": game_pin,
                    "bot_count": 0,
                    "driver": game_driver,
                    "bot_drivers": []
                }
                flooder_status["current_game"] = game_pin
                flooder_status["status"] = f"✅ Created game: {game_pin} - Starting 10 bots..."
                
                try:
                    # Use dashboard joiner to add 10 bots via API
                    import requests
                    response = requests.post('http://localhost:5000/api/start', json={
                        'game_pin': game_pin,
                        'num_bots': 10,
                        'custom_prefix': 'FlooperBot'
                    }, timeout=5)
                    
                    if response.status_code == 200:
                        flooder_status["status"] = f"👥 Joining 10 bots to {game_pin}..."
                        bot_count += 10
                        flooder_games[game_pin]["bot_count"] = 10
                        flooder_status["bots_joined"] = bot_count
                except:
                    # Fallback: try to join manually if API fails
                    flooder_status["status"] = f"⚠️ API method failed, trying manual join..."
                    pass
                
                # Game runs for 30 seconds
                flooder_status["status"] = f"🎮 Game {game_pin} running (30s)..."
                time.sleep(30)
                
                # Clean up after 30s
                flooder_status["status"] = f"✅ Game {game_pin} complete - Next game..."
                if game_pin in flooder_games:
                    try:
                        game_driver.quit()
                    except:
                        pass
                    flooder_games.pop(game_pin, None)
                time.sleep(2)
            else:
                flooder_status["status"] = "⚠️ Failed to create game"
                time.sleep(2)
        
        except Exception as e:
            flooder_status["status"] = f"❌ Error: {str(e)}"
            time.sleep(2)

@app.route('/api/start-flooder', methods=['POST'])
def start_flooder():
    global flooder_active, flooder_thread, flooder_status
    
    if flooder_active:
        return jsonify({"success": False, "message": "Flooder already running"}), 400
    
    flooder_active = True
    flooder_status = {"status": "Starting...", "games_created": 0, "bots_joined": 0, "current_game": None}
    
    # Start single worker thread - sequential, no parallel workers
    flooder_thread = threading.Thread(target=flooder_worker, daemon=True)
    flooder_thread.start()
    
    return jsonify({"success": True, "message": "Flooder started - creating games sequentially"})

@app.route('/api/stop-flooder', methods=['POST'])
def stop_flooder():
    global flooder_active, flooder_games, flooder_status
    
    flooder_active = False
    
    # Clean up all games
    for pin, game_info in list(flooder_games.items()):
        try:
            game_info["driver"].quit()
        except:
            pass
    
    flooder_games.clear()
    flooder_status = {"status": "Stopped", "games_created": 0, "bots_joined": 0, "current_game": None}
    
    return jsonify({"success": True, "message": "Flooder stopped"})

@app.route('/api/get-flooder-status', methods=['GET'])
def get_flooder_status():
    global flooder_active, flooder_games, flooder_status
    
    games_list = []
    for pin, info in flooder_games.items():
        games_list.append({
            "code": info["code"],
            "bots": info["bot_count"]
        })
    
    return jsonify({
        "active": flooder_active,
        "status": flooder_status.get("status", "Idle"),
        "games_created": flooder_status.get("games_created", 0),
        "bots_joined": flooder_status.get("bots_joined", 0),
        "current_game": flooder_status.get("current_game", None),
        "games": games_list,
        "total_games": len(games_list),
        "total_bots": sum(g["bots"] for g in games_list)
    })

@app.route('/viewer')
def viewer():
    return render_template('viewer.html')

@app.route('/checker')
def checker():
    return render_template('checker.html')

def validate_code_worker(job_id, start_num, end_num, length):
    import requests
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    
    for i in range(start_num, end_num):
        if job_id not in check_jobs:
            break
        
        code = str(i).zfill(length)
        is_valid = False
        
        try:
            response = session.get(f"https://kahoot.it/rest/gameBlock?code={code}", timeout=2)
            is_valid = response.status_code == 200 and 'game' in response.text.lower()
            
            with job_lock:
                if job_id in check_jobs:
                    check_jobs[job_id]['results'].append({
                        "code": code,
                        "valid": is_valid,
                        "status": "✓ Valid" if is_valid else "✗ Invalid"
                    })
                    check_jobs[job_id]['checked'] += 1
        except Exception as e:
            with job_lock:
                if job_id in check_jobs:
                    check_jobs[job_id]['results'].append({
                        "code": code,
                        "valid": False,
                        "status": "✗ Invalid"
                    })
                    check_jobs[job_id]['checked'] += 1

@app.route('/api/check-codes', methods=['POST'])
def check_codes():
    data = request.json or {}
    code_type = data.get('code_type', '7')
    num_workers = int(data.get('workers', 3))
    num_workers = min(num_workers, 5)  # Cap at 5 to prevent Chrome crashes
    
    job_id = str(uuid.uuid4())
    
    ranges = []
    total_count = 0
    
    if code_type == '5':
        ranges.append((0, 100000, 5))
        total_count = 100000
    elif code_type == '6':
        ranges.append((0, 1000000, 6))
        total_count = 1000000
    elif code_type == '7':
        ranges.append((0, 10000000, 7))
        total_count = 10000000
    elif code_type == '5,6':
        ranges.append((0, 100000, 5))
        ranges.append((0, 1000000, 6))
        total_count = 1100000
    elif code_type == '5,7':
        ranges.append((0, 100000, 5))
        ranges.append((0, 10000000, 7))
        total_count = 10100000
    elif code_type == '6,7':
        ranges.append((0, 1000000, 6))
        ranges.append((0, 10000000, 7))
        total_count = 11000000
    elif code_type == 'all':
        ranges.append((0, 100000, 5))
        ranges.append((0, 1000000, 6))
        ranges.append((0, 10000000, 7))
        total_count = 11100000
    
    with job_lock:
        check_jobs[job_id] = {
            'total': total_count,
            'checked': 0,
            'results': [],
            'status': 'running'
        }
    
    # Distribute codes across workers
    for start, end, length in ranges:
        codes_per_worker = (end - start) // num_workers
        for w in range(num_workers):
            w_start = start + (w * codes_per_worker)
            w_end = start + ((w + 1) * codes_per_worker) if w < num_workers - 1 else end
            thread = threading.Thread(target=validate_code_worker, args=(job_id, w_start, w_end, length), daemon=True)
            thread.start()
    
    return jsonify({"job_id": job_id, "total": total_count})

@app.route('/api/check-progress', methods=['GET'])
def check_progress():
    job_id = request.args.get('job_id')
    
    with job_lock:
        if job_id not in check_jobs:
            return jsonify({"error": "Job not found"}), 404
        
        job = check_jobs[job_id]
        is_complete = job['checked'] >= job['total']
        
        if is_complete:
            job['status'] = 'complete'
        
        return jsonify({
            "job_id": job_id,
            "total": job['total'],
            "checked": job['checked'],
            "results": job['results'],
            "status": job['status'],
            "progress": int((job['checked'] / job['total']) * 100) if job['total'] > 0 else 0
        })

@app.route('/api/test-code/<code>', methods=['GET'])
def test_single_code(code):
    """Quick test endpoint to verify a single code works using Selenium"""
    driver = None
    try:
        driver = launch_browser()
        driver.set_page_load_timeout(8)
        driver.get("https://www.kahoot.it")
        time.sleep(0.5)
        
        # Find and fill the game input field
        game_input = driver.find_element(By.ID, "game-input")
        game_input.clear()
        game_input.send_keys(code)
        time.sleep(0.3)
        game_input.send_keys(Keys.ENTER)
        time.sleep(1)
        
        # Check if we're on a valid game page
        current_url = driver.current_url
        page_source = driver.page_source
        is_valid = ("kahoot.it/join" in current_url or "preview" in current_url or "game" in current_url.lower()) and ("join" in page_source.lower() or "game" in page_source.lower())
        
        driver.quit()
        return jsonify({
            "code": code,
            "valid": is_valid,
            "status": "✓ Valid - Game Found!" if is_valid else "✗ Invalid - No Game",
            "url": current_url
        })
    except Exception as e:
        if driver:
            try:
                driver.quit()
            except:
                pass
        return jsonify({
            "code": code,
            "valid": False,
            "status": "✗ Invalid - Error",
            "error": str(e)
        })

@app.route('/api/find-valid-code/<code_type>', methods=['GET'])
def find_valid_code(code_type):
    """Find a random valid code in the specified range"""
    import requests
    
    # Determine range based on code type
    if code_type == '5':
        length = 5
        max_code = 100000
    elif code_type == '6':
        length = 6
        max_code = 1000000
    elif code_type == '7':
        length = 7
        max_code = 10000000
    else:
        return jsonify({"error": "Invalid code type. Use 5, 6, or 7"}), 400
    
    attempts = 0
    max_attempts = 100
    
    while attempts < max_attempts:
        # Random code in the range
        random_code = str(random.randint(0, max_code - 1)).zfill(length)
        attempts += 1
        
        try:
            response = requests.get(f"https://kahoot.it/rest/gameBlock?code={random_code}", timeout=2)
            is_valid = response.status_code == 200 and 'game' in response.text.lower()
            
            if is_valid:
                return jsonify({
                    "code": random_code,
                    "valid": True,
                    "status": "✓ Found Valid Code!",
                    "attempts": attempts,
                    "code_type": code_type
                })
        except:
            pass
    
    return jsonify({
        "code": None,
        "valid": False,
        "status": "✗ No valid code found after 100 random attempts",
        "attempts": attempts,
        "code_type": code_type
    })

@app.route('/api/start', methods=['POST'])
def start_bots():
    data = request.json or {}
    game_pin = data.get('game_pin')
    num_bots = int(data.get('num_bots', 1))
    custom_prefix = data.get('custom_prefix', '')
    
    global bot_status, bot_names, leaderboard, successful_bots, target_bots
    bot_status = {}
    bot_names = {}
    leaderboard = {}
    successful_bots = 0
    target_bots = num_bots
    
    # Create 50% buffer: if requesting 10 bots, try 15 to account for failures
    extra_accounts = max(3, int(num_bots * 0.5))
    total_attempts = num_bots + extra_accounts
    
    for i in range(1, total_attempts + 1):
        bot_status[i] = "Waiting..."
        thread = threading.Thread(target=join_bot_with_buffer, args=(game_pin, i, custom_prefix, num_bots), daemon=True)
        thread.start()
        time.sleep(0.15)  # Minimal stagger for speed - semaphore controls concurrency
    
    return jsonify({"success": True, "message": f"Starting {num_bots} bots (trying {total_attempts} accounts)..."})

@app.route('/api/status')
def get_status():
    return jsonify(bot_status)

@app.route('/api/bot-screenshot/<int:bot_id>')
def get_bot_screenshot(bot_id):
    global bot_drivers
    if bot_id not in bot_drivers:
        return jsonify({"error": "Bot not found"}), 404
    
    try:
        driver = bot_drivers[bot_id]
        screenshot = driver.get_screenshot_as_png()
        import base64
        b64_screenshot = base64.b64encode(screenshot).decode()
        return jsonify({"screenshot": b64_screenshot, "status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/leaderboard')
def get_leaderboard():
    return jsonify(leaderboard)

def generate_tiktok_views_worker(job_id, video_url, num_views_per_browser, view_speed):
    driver = None
    try:
        driver = launch_browser()
        driver.set_page_load_timeout(10)
        
        sleep_time = 3 if view_speed == "slow" else 1.5 if view_speed == "normal" else 0.5
        
        for i in range(num_views_per_browser):
            if job_id not in tiktok_jobs:
                break
            
            try:
                driver.get(video_url)
                time.sleep(sleep_time)
                
                with job_lock:
                    if job_id in tiktok_jobs:
                        tiktok_jobs[job_id]['views_generated'] += 1
                        tiktok_jobs[job_id]['checked'] += 1
            except:
                time.sleep(1)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

@app.route('/api/generate-tiktok-views', methods=['POST'])
def generate_tiktok_views():
    data = request.json or {}
    video_url = data.get('video_url', '')
    num_views = int(data.get('num_views', 50))
    view_speed = data.get('view_speed', 'normal')
    num_browsers = int(data.get('num_browsers', 5))
    
    if not video_url:
        return jsonify({"error": "Video URL is required"}), 400
    
    if 'tiktok.com' not in video_url and len(video_url) < 10:
        return jsonify({"error": "Invalid TikTok URL or video ID"}), 400
    
    if not video_url.startswith('http'):
        video_url = f"https://www.tiktok.com/video/{video_url}"
    
    job_id = str(uuid.uuid4())
    views_per_browser = num_views // num_browsers
    
    with job_lock:
        tiktok_jobs[job_id] = {
            'total': num_views,
            'views_generated': 0,
            'checked': 0,
            'status': 'running'
        }
    
    for i in range(num_browsers):
        thread = threading.Thread(
            target=generate_tiktok_views_worker,
            args=(job_id, video_url, views_per_browser, view_speed),
            daemon=True
        )
        thread.start()
        time.sleep(0.05)
    
    return jsonify({"job_id": job_id, "message": "TikTok view generation started"})

@app.route('/api/tiktok-progress', methods=['GET'])
def tiktok_progress():
    job_id = request.args.get('job_id')
    
    with job_lock:
        if job_id not in tiktok_jobs:
            return jsonify({"error": "Job not found"}), 404
        
        job = tiktok_jobs[job_id]
        is_complete = job['checked'] >= job['total']
        
        if is_complete:
            job['status'] = 'complete'
        
        return jsonify({
            "job_id": job_id,
            "total": job['total'],
            "views_generated": job['views_generated'],
            "checked": job['checked'],
            "status": job['status'],
            "progress": int((job['checked'] / job['total']) * 100) if job['total'] > 0 else 0
        })

@app.route('/api/stop-tiktok', methods=['POST'])
def stop_tiktok():
    global tiktok_jobs
    tiktok_jobs = {}
    return jsonify({"message": "TikTok view generation stopped"})

@app.route('/api/generate-game', methods=['POST'])
def generate_game_code():
    driver = None
    try:
        driver = launch_browser()
        driver.set_page_load_timeout(20)
        
        # Go to the play.kahoot.it URL for guest play
        quiz_id = "a13d166b-c332-4085-a8c5-9e15321b7024"
        driver.get(f"https://play.kahoot.it/v2/?quizId={quiz_id}")
        time.sleep(4)
        
        # Click Host button to start hosting the game
        try:
            host_btn = driver.find_element(By.XPATH, "//button[contains(., 'Host')]")
            driver.execute_script("arguments[0].click();", host_btn)
            time.sleep(4)
        except:
            try:
                host_btn = driver.find_element(By.CSS_SELECTOR, "button")
                driver.execute_script("arguments[0].click();", host_btn)
                time.sleep(4)
            except:
                pass
        
        # Wait for game PIN to appear on screen
        time.sleep(2)
        
        # Try multiple ways to extract the game PIN
        game_code = None
        
        # Method 1: Look for text containing PIN/Code
        try:
            all_text = driver.find_element(By.TAG_NAME, "body").text
            import re
            matches = re.findall(r'\b\d{5,7}\b', all_text)
            if matches:
                game_code = matches[0]
        except:
            pass
        
        # Method 2: Check page source
        if not game_code:
            try:
                source = driver.page_source
                import re
                match = re.search(r'["\']?pin["\']?\s*[:=]\s*["\']?(\d{5,7})', source, re.IGNORECASE)
                if match:
                    game_code = match.group(1)
            except:
                pass
        
        # Method 3: Look for any large numbers in the page
        if not game_code:
            try:
                for elem in driver.find_elements(By.XPATH, "//*[contains(translate(., '0123456789', ''), '') = '']"):
                    text = elem.text.strip()
                    if len(text) >= 5 and len(text) <= 7 and text.isdigit():
                        game_code = text
                        break
            except:
                pass
        
        # If we found a code, return it
        if game_code:
            return jsonify({"game_code": game_code, "status": "success"})
        
        # Fallback - game is hosted but we couldn't extract code
        return jsonify({"status": "success", "message": "Game hosted! Check Kahoot.it for the PIN code"}), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error: {str(e)}"}), 400
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

@app.route('/api/stop', methods=['POST'])
def stop_bots():
    global drivers, bot_status, bot_drivers
    
    for driver in drivers:
        try:
            driver.quit()
        except:
            pass
    
    drivers = []
    bot_status = {}
    bot_drivers = {}
    
    return jsonify({"success": True, "message": "All bots stopped"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
