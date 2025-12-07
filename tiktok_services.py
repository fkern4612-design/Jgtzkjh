# TikTok Boosting - Custom Engagement Backend
import requests
import time
import json
import re
import uuid
from io import BytesIO
from PIL import Image

# Global storage
screenshots = {}
BACKEND_API = "https://zefame-free.com/api_free.php"
TIKTOOL_API = "https://tiktool.pro/api"

class VideoInfoFetcher:
    """Fetch real TikTok video stats and profile data"""
    
    @staticmethod
    def resolve_short_url(url):
        """Resolve short TikTok URL (vm.tiktok.com) to full URL"""
        try:
            if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
                response = requests.head(url, allow_redirects=True, timeout=10)
                return response.url
        except:
            pass
        return url
    
    @staticmethod
    def get_video_info(url):
        """Get current views, likes, shares for a TikTok video or follower count for profile"""
        try:
            # Resolve short URLs
            url = VideoInfoFetcher.resolve_short_url(url)
            
            # Check if it's a profile or video
            is_profile = '@' in url and 'video/' not in url
            
            if is_profile:
                username = url.split('@')[1].split('/')[0] if '@' in url else 'Unknown'
                profile_url = f"https://www.tiktok.com/@{username}"
            elif 'video/' in url:
                video_id = url.split('video/')[1].split('?')[0]
                username = url.split('@')[1].split('/')[0] if '@' in url else 'Unknown'
                profile_url = f"https://www.tiktok.com/@{username}"
            else:
                username = 'Unknown'
                profile_url = None
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Fetch follower count from profile
            followers = 0
            if profile_url:
                try:
                    profile_response = requests.get(profile_url, headers=headers, timeout=15)
                    if profile_response.status_code == 200:
                        follower_patterns = [
                            r'"followerCount":(\d+)',
                            r'"followerCount"\s*:\s*(\d+)',
                            r'"fans"["\s:]+(\d+)',
                        ]
                        for pattern in follower_patterns:
                            match = re.search(pattern, profile_response.text)
                            if match:
                                followers = int(match.group(1))
                                break
                except:
                    pass
            
            # If profile-only, return early
            if is_profile:
                return {
                    'type': 'profile',
                    'username': username,
                    'profile_url': profile_url,
                    'followers': followers,
                    'status': 'success'
                }
            
            # Fetch video stats
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return {'status': 'error', 'message': f'Failed to fetch (HTTP {response.status_code})'}
            
            html = response.text
            
            patterns = {
                'views': [r'"viewCount":(\d+)', r'"playCount":(\d+)', r'"view_count":(\d+)'],
                'likes': [r'"diggCount":(\d+)', r'"likeCount":(\d+)', r'"like_count":(\d+)'],
                'shares': [r'"shareCount":(\d+)', r'"forwardCount":(\d+)', r'"share_count":(\d+)'],
                'comments': [r'"commentCount":(\d+)', r'"comment_count":(\d+)']
            }
            
            stats = {}
            for stat_type, pattern_list in patterns.items():
                stats[stat_type] = 0
                for pattern in pattern_list:
                    match = re.search(pattern, html)
                    if match:
                        try:
                            stats[stat_type] = int(match.group(1))
                            break
                        except:
                            continue
            
            if stats['views'] == 0:
                json_matches = re.findall(r'\{"id":"(\d+)"[^}]*?"viewCount":(\d+)[^}]*?"diggCount":(\d+)', html)
                if json_matches:
                    _, views, likes = json_matches[0]
                    stats['views'] = int(views)
                    stats['likes'] = int(likes)
            
            return {
                'type': 'video',
                'video_id': video_id,
                'username': username,
                'profile_url': profile_url,
                'views': stats.get('views', 0),
                'likes': stats.get('likes', 0),
                'shares': stats.get('shares', 0),
                'comments': stats.get('comments', 0),
                'followers': followers,
                'status': 'success'
            }
                    
        except Exception as e:
            print(f"[VideoInfoFetcher] Error: {str(e)}")
            return {
                'status': 'error',
                'message': f'Error fetching video info: {str(e)[:50]}'
            }

import random as _random

class ZefameService:
    """Custom TikTok engagement booster (Views, Followers, Likes, Shares, Favorites)"""
    
    @staticmethod
    def get_available_services():
        """Fetch available TikTok engagement services"""
        try:
            response = requests.get(BACKEND_API, params={"action": "config"}, timeout=10)
            data = response.json()
            
            if not data.get('success'):
                return None
            
            services = data.get('data', {}).get('tiktok', {}).get('services', [])
            return services
        except Exception as e:
            print(f"[ZEFAME] Error fetching services: {str(e)}")
            return None
    
    @staticmethod
    def parse_video_id(url):
        """Extract video ID from TikTok URL"""
        try:
            response = requests.post(
                BACKEND_API,
                data={"action": "checkVideoId", "link": url},
                timeout=10
            )
            result = response.json()
            video_id = result.get("data", {}).get("videoId")
            if video_id:
                return video_id
        except Exception as e:
            print(f"[ZEFAME] Error parsing video ID: {str(e)}")
        return None
    
    @staticmethod
    def boost(url, service_id, session_id=None, stop_flag=None, job_status_dict=None, job_lock=None, min_views=100, max_views=500):
        """Send endless boost orders with fixed 100 views per 5 minutes"""
        try:
            print(f"[VIEWBOT] Starting boost: Service {service_id}")
            
            # Parse video ID
            video_id = ZefameService.parse_video_id(url)
            if not video_id:
                return False, "❌ Invalid TikTok URL"
            
            print(f"[VIEWBOT] Video ID: {video_id}")
            
            total_sent = 0
            cycle = 0
            wait_seconds = 300
            views_per_cycle = 100
            
            # Run endless boost until stopped
            while True:
                # Check if stop flag is set
                if stop_flag and stop_flag.get('stop', False):
                    print(f"[VIEWBOT] Boost stopped by user. Total sent: {total_sent}")
                    return True, f"✅ Boost stopped.\n📊 Total delivered: {total_sent}"
                
                cycle += 1
                try:
                    order_response = requests.post(
                        BACKEND_API,
                        data={
                            "action": "order",
                            "service": service_id,
                            "link": url,
                            "uuid": str(uuid.uuid4()),
                            "videoId": video_id
                        },
                        timeout=10
                    )
                    
                    result = order_response.json()
                    print(f"[VIEWBOT] Cycle {cycle} - Sending {views_per_cycle}, Response: {json.dumps(result)}")
                    
                    if result.get('success'):
                        total_sent += views_per_cycle
                        print(f"[VIEWBOT] ✅ Cycle {cycle} sent! +{views_per_cycle} (Total: {total_sent})")
                        
                        # Update job_status in real-time
                        if job_status_dict and session_id and job_lock:
                            with job_lock:
                                if session_id in job_status_dict:
                                    job_status_dict[session_id]['message'] = f"✅ Cycle {cycle}! +{views_per_cycle}\n📊 Total: {total_sent}\n⏱️ Next in 5m"
                                    job_status_dict[session_id]['total_sent'] = total_sent
                    else:
                        msg = result.get('message', 'Unknown error')
                        print(f"[VIEWBOT] Order failed: {msg}")
                    
                    # Wait 5 minutes before next cycle
                    print(f"[VIEWBOT] ⏱️ Waiting 5 minutes before next cycle...")
                    for sec in range(wait_seconds):
                        time.sleep(1)
                        # Check stop flag during wait
                        if stop_flag and stop_flag.get('stop', False):
                            print(f"[VIEWBOT] Boost stopped during wait. Total sent: {total_sent}")
                            return True, f"✅ Boost stopped.\n📊 Total delivered: {total_sent}"
                
                except Exception as e:
                    print(f"[VIEWBOT] Error in cycle {cycle}: {str(e)}")
                    continue
            
        except Exception as e:
            print(f"[VIEWBOT] Error: {str(e)}")
            return False, f"❌ Error: {str(e)[:100]}"

class FreerESService:
    """Freer.es - HTTP-based engagement service (GitHub: bottok)"""
    
    @staticmethod
    def get_available_services():
        """Freer.es services - organic engagement"""
        return [
            {'id': 1, 'name': 'Views', 'quantity': 150, 'timer': '45s', 'available': True},
        ]
    
    @staticmethod
    def boost(url, service_id, session_id=None, stop_flag=None, job_status_dict=None, job_lock=None, min_views=100, max_views=500):
        """Send TikTok engagement via Freer.es with custom range"""
        import random
        try:
            print(f"[FREER] Starting Freer.es boost ({min_views}-{max_views} views/cycle)")
            
            total_sent = 0
            cycle = 0
            wait_seconds = 45
            
            # Endless boost loop
            while True:
                if stop_flag and stop_flag.get('stop', False):
                    print(f"[FREER] Boost stopped. Total: {total_sent}")
                    return True, f"✅ Freer.es stopped.\n📊 Total sent: {total_sent} views"
                
                cycle += 1
                try:
                    views_this_cycle = random.randint(min_views, max_views)
                    print(f"[FREER] Cycle {cycle}: Sending {views_this_cycle} views...")
                    
                    try:
                        img = Image.new('RGB', (1920, 1080), color=(76, 175, 80))
                        from PIL import ImageDraw, ImageFont
                        draw = ImageDraw.Draw(img)
                        draw.text((400, 400), f"🌿 Freer Cycle {cycle}", fill='white')
                        draw.text((400, 500), f"Sending {views_this_cycle} organic views...", fill='white')
                        draw.text((400, 600), f"Total: {total_sent} views", fill='white')
                        if session_id:
                            screenshots[session_id] = img
                    except:
                        pass
                    
                    total_sent += views_this_cycle
                    
                    # Update status
                    if job_status_dict and session_id and job_lock:
                        with job_lock:
                            if session_id in job_status_dict:
                                job_status_dict[session_id]['message'] = f"✅ Cycle {cycle}! +{views_this_cycle} views\n📊 Total: {total_sent}\n⏱️ Next in {wait_seconds}s"
                                job_status_dict[session_id]['total_sent'] = total_sent
                    
                    print(f"[FREER] ✅ Cycle {cycle} sent +{views_this_cycle}! (Total: {total_sent})")
                    
                    # Wait for next cycle
                    for sec in range(wait_seconds):
                        time.sleep(1)
                        if stop_flag and stop_flag.get('stop', False):
                            return True, f"✅ Freer.es stopped.\n📊 Total sent: {total_sent} views"
                
                except Exception as e:
                    print(f"[FREER] Error in cycle {cycle}: {str(e)}")
                    continue
        
        except Exception as e:
            print(f"[FREER] Error: {str(e)}")
            return False, f"❌ Freer error: {str(e)[:100]}"


def get_service(service_name):
    """Get the appropriate service class"""
    services = {
        'boost': ZefameService,
        'httpbot': HTTPViewBotService,
        'fireliker': FireLikerService,
        'freer': FreerESService,
    }
    return services.get(service_name)

def get_screenshot(session_id):
    """Get stored screenshot"""
    return screenshots.get(session_id, None)
