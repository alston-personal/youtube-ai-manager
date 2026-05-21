#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error
import ssl
import argparse
from tqdm import tqdm
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ==========================================
# ⚙️ SYSTEM CONFIGURATION & CONSTANTS
# ==========================================
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"

# ==========================================
# 🔑 CREDENTIALS & API UTILITIES
# ==========================================
_GEMINI_KEYS = []
_CURRENT_KEY_INDEX = 0

def load_all_gemini_keys():
    global _GEMINI_KEYS
    if _GEMINI_KEYS:
        return _GEMINI_KEYS
        
    keys = []
    # 1. Try to load from environment first
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        keys.append(env_key)
        
    # 2. Try to load from /home/ubuntu/agentmanager/.env
    env_path = "/home/ubuntu/agentmanager/.env"
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                env_keys = {}
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        if k in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
                            env_keys[k] = v
                # Add them in order of preference
                for name in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
                    if name in env_keys and env_keys[name] not in keys:
                        keys.append(env_keys[name])
        except Exception:
            pass
            
    _GEMINI_KEYS = keys
    return _GEMINI_KEYS

def load_gemini_key():
    """Loads the currently selected Gemini API Key supporting rotation"""
    keys = load_all_gemini_keys()
    if not keys:
        return None
    global _CURRENT_KEY_INDEX
    if _CURRENT_KEY_INDEX >= len(keys):
        _CURRENT_KEY_INDEX = 0
    return keys[_CURRENT_KEY_INDEX]

def rotate_gemini_key():
    """Rotates to the next available Gemini API Key when hitting rate limits"""
    global _CURRENT_KEY_INDEX
    keys = load_all_gemini_keys()
    if len(keys) > 1:
        _CURRENT_KEY_INDEX = (_CURRENT_KEY_INDEX + 1) % len(keys)
        print(f"🔄 [Key Rotation] Rotating to next Gemini API Key (Key slot: {_CURRENT_KEY_INDEX+1}/{len(keys)})...")
        return True
    return False

def get_youtube_client():
    """Gets authenticated YouTube Data API client, loading or performing OAuth 2.0 flow"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"⚠️ Warning loading token.json: {e}")
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired OAuth credentials...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"❌ Failed to refresh token: {e}")
                creds = None
                
        if not creds:
            if not os.path.exists(CLIENT_SECRET_FILE):
                print(f"❌ Error: '{CLIENT_SECRET_FILE}' not found!")
                print("💡 Please download your OAuth client secret JSON from Google Cloud Console")
                print(f"   and save it to: {os.path.abspath(CLIENT_SECRET_FILE)}")
                sys.exit(1)
            
            print("🔑 Initiating OAuth 2.0 Authorization Flow...")
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            # Standard local server with predictable port 8090 for easier headless SSH tunneling/curl
            try:
                creds = flow.run_local_server(port=8090, open_browser=False)
            except Exception as e:
                print(f"⚠️ Port 8090 in use, falling back to random port: {e}")
                creds = flow.run_local_server(port=0, open_browser=False)
            
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
            print(f"💾 Saved authenticated credentials to {TOKEN_FILE}")
            
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)

# ==========================================
# 🧠 GEMINI AI GENERATIVE & FILES API UTILITIES
# ==========================================
def call_gemini(prompt, file_uri=None, mime_type=None, response_mime_type="application/json"):
    """Executes pure REST API call to Gemini 2.5 Flash supporting text and media files"""
    api_key = load_gemini_key()
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in environment or .env file!")
        sys.exit(1)
        
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    parts = []
    if file_uri and mime_type:
        parts.append({
            "fileData": {
                "fileUri": file_uri,
                "mimeType": mime_type
            }
        })
    parts.append({"text": prompt})
    
    payload = {
        "contents": [{
            "parts": parts
        }],
        "generationConfig": {
            "responseMimeType": response_mime_type
        }
    }
    
    req = urllib.request.Request(
        gemini_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    import time
    max_retries = 6
    backoff = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, context=ctx) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                return res_data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            if e.code in [500, 503, 429] and attempt < max_retries - 1:
                print(f"⚠️ Gemini API returned {e.code} (Server Error / High Demand). Retrying in {backoff} seconds (Attempt {attempt+1}/{max_retries})...")
                if rotate_gemini_key():
                    new_key = load_gemini_key()
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={new_key}"
                    req = urllib.request.Request(
                        gemini_url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"❌ Gemini API HTTP Error: {e.code} - {e.read().decode('utf-8')}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Gemini Connection Error: {e}")
            sys.exit(1)

def upload_file_to_gemini(file_path, mime_type="video/mp4"):
    """Uploads file to Google Gemini Files API via HTTP REST protocol for non-SDK stability"""
    api_key = load_gemini_key()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    
    # Step 1: Initiate Resumable Upload Session
    init_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json"
    }
    
    metadata = {"file": {"display_name": file_name}}
    req = urllib.request.Request(
        init_url,
        data=json.dumps(metadata).encode("utf-8"),
        headers=headers
    )
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            upload_url = response.getheader("X-Goog-Upload-URL")
    except urllib.error.HTTPError as e:
        print(f"❌ Failed to initiate Gemini file upload session: {e.code} - {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"❌ Failed to initiate Gemini file upload session: {e}")
        return None
        
    # Step 2: Upload File Content Bytes
    print(f"⬆️ Uploading video asset ({file_size / (1024*1024):.2f} MB) to Google Gemini...")
    headers = {
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
        "Content-Type": mime_type,
        "Content-Length": str(file_size)
    }
    
    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
            
        req = urllib.request.Request(upload_url, data=file_data, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
        file_uri = res_data["file"]["uri"]
        file_name_api = res_data["file"]["name"]
        print(f"✅ Uploaded successfully. Resource Name: {file_name_api}")
        return file_uri, file_name_api
    except urllib.error.HTTPError as e:
        print(f"❌ Failed uploading video file bytes to Gemini: {e.code} - {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"❌ Failed uploading video file to Gemini: {e}")
        return None

def check_gemini_file_status(file_name_api):
    """Checks processing state of uploaded file in Gemini API"""
    api_key = load_gemini_key()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    status_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name_api}?key={api_key}"
    req = urllib.request.Request(status_url)
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            state = res_data.get("state", "STATE_UNSPECIFIED")
            return state
    except Exception as e:
        print(f"⚠️ Error checking file status: {e}")
        return "ERROR"

def delete_gemini_file(file_name_api):
    """Deletes uploaded temporary video file from Google Gemini storage for security"""
    api_key = load_gemini_key()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    delete_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name_api}?key={api_key}"
    req = urllib.request.Request(delete_url, method="DELETE")
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            print("🗑️ Cleaned up temporary video asset from Gemini server.")
    except Exception as e:
        print(f"⚠️ Warning: Failed to clean up video '{file_name_api}' from Gemini: {e}")

def generate_funny_metadata(video_title, video_description):
    """Asks Gemini to rewrite video title, description, and generate funny timestamps semantically (Fallback)"""
    prompt = f"""
    You are an extremely funny, sarcastic, and viral YouTube channel manager for a Diablo IV campaign and gameplay series.
    Please rewrite the following video's metadata for maximum humor, clickability, and audience engagement!

    Original Title: {video_title}
    Original Description: {video_description}

    CRITICAL REWRITE DIRECTIONS:
    - Do NOT hallucinate generic Diablo IV endgame memes (like "莉莉絲的微笑", "畢業裝備", "新賽季刷寶", "賽季結束肝也結束") unless they are actually mentioned in the original title or are highly relevant to this specific video context.
    - Closely analyze the original title's quest name or story chapter (e.g., "視外安寧", "最後的赫拉迪姆"). Base all humor, narrative, and timestamps directly on the thematic lore, quest name, campaign progress, or specific story scene implied by the title.
    - Keep all terminology strictly using Traditional Chinese (Taiwan).
    - Ensure the timestamps and comments are logical, witty, and directly tied to the quest/story theme of the video.

    Rewrite Requirements:
    1. funny_title: A funny, satirical, or clickbait title (Traditional Chinese/Taiwanese, max 100 characters).
    2. funny_description: A highly engaging, humorous, or self-deprecating video description (Traditional Chinese/Taiwanese).
    3. funny_timestamps: Generate at least 3 funny time-stamps in standard MM:SS format representing highly relevant, funny narrative checkpoints matching the quest theme.

    Return your output strictly as a JSON object with this exact structure:
    {{
      "funny_title": "...",
      "funny_description": "...",
      "funny_timestamps": "00:00 精彩開場\\n01:30 智商掉線\\n02:45 爆笑收尾"
    }}
    """
    ai_response = call_gemini(prompt)
    try:
        # Robust parsing
        import re
        match = re.search(r"\{.*\}", ai_response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(ai_response)
    except Exception:
        print(f"❌ Failed to parse fallback AI Response: {ai_response}")
        sys.exit(1)

def download_lowres_video(video_id):
    """Downloads low-resolution (240p/360p) gameplay video, checking for browser cookies to bypass bot checks"""
    output_tpl = f"/tmp/yt_temp_{video_id}.%(ext)s"
    print(f"📥 Downloading lightweight 360p video for ID: '{video_id}' using yt-dlp...")
    
    cookies_opts = ""
    if os.path.exists("cookies.txt"):
        print("🍪 Detected local cookies.txt file! Passing it to bypass bot verification checks.")
        cookies_opts = "--cookies cookies.txt"
    elif os.path.exists("/home/ubuntu/youtube-ai-manager/cookies.txt"):
        print("🍪 Detected local cookies.txt in project directory! Passing it to bypass bot verification checks.")
        cookies_opts = "--cookies /home/ubuntu/youtube-ai-manager/cookies.txt"
        
    # Use best quality but not exceeding 360p to keep file size down to a few MBs
    cmd = (
        f"yt-dlp {cookies_opts} --js-runtimes node --remote-components ejs:github -f '18/worst[ext=mp4]/worst' "
        f"--max-filesize 50M "
        f"-o '{output_tpl}' "
        f"https://www.youtube.com/watch?v={video_id}"
    )
    
    ret = os.system(cmd)
    if ret != 0:
        print("⚠️ Warning: Failed to download with specific quality constraint. Retrying absolute worst format...")
        cmd_fallback = f"yt-dlp {cookies_opts} --js-runtimes node --remote-components ejs:github -f '18/worst' -o '{output_tpl}' https://www.youtube.com/watch?v={video_id}"
        ret_fallback = os.system(cmd_fallback)
        if ret_fallback != 0:
            print("\n⚠️ YouTube Bot Protection Blocked Cloud Server IP!")
            print("💡 To resolve this and enable 100% full visual multi-modal indexing, simply download a 'cookies.txt'")
            print("   from your browser using a 'Get cookies.txt' extension, place it as 'cookies.txt' in this directory,")
            print("   and run the command again!")
            print("🔄 Gracefully falling back to pure text semantic optimization...\n")
            return None
            
    # Locate downloaded file path
    import glob
    matching_files = glob.glob(f"/tmp/yt_temp_{video_id}.*")
    if matching_files:
        print(f"💾 Video successfully downloaded to: {matching_files[0]}")
        return matching_files[0]
    return None

def fetch_captions(youtube, video_id):
    """Attempts to retrieve available captions for a video via the YouTube Data API.
    Returns a string containing the merged caption text (UTF‑8) or None if not available.
    """
    try:
        # List caption tracks
        caps = youtube.captions().list(part="snippet", videoId=video_id).execute()
        items = caps.get("items", [])
        if not items:
            return None
        # Prefer a manually uploaded or auto-generated English/TW caption
        preferred = None
        for item in items:
            snippet = item.get("snippet", {})
            # Look for Traditional Chinese (zh-TW) first, then any language
            if snippet.get("language") == "zh-TW":
                preferred = item
                break
        if not preferred:
            preferred = items[0]
        caption_id = preferred.get("id")
        # Download caption track (API returns binary subtitle file)
        download_res = youtube.captions().download(id=caption_id).execute()
        # The response is bytes; decode as UTF‑8 assuming SRT format
        if isinstance(download_res, bytes):
            return download_res.decode("utf-8", errors="ignore")
        # Some client libraries return a dict with "body" key
        if isinstance(download_res, dict) and "body" in download_res:
            return download_res["body"]
        return None
    except Exception as e:
        print(f"⚠️ Unable to fetch captions for video {video_id}: {e}")
        return None

def analyze_video_multimodal(video_path, orig_title, orig_description, video_id=None):
    """Uploads low-res gameplay video to Gemini Files API and performs visual semantic indexing.
    Incorporates YouTube captions (if available) into the prompt to improve grounding.
    """
    upload_res = upload_file_to_gemini(video_path)
    if not upload_res:
        print("❌ Error: Unable to upload video to Gemini Files API!")
        return None
        
    file_uri, file_name_api = upload_res
    
    # Polling wait for video indexing to complete on Google server
    import time
    print("⏳ Waiting for Google servers to complete gameplay video visual indexing...")
    pbar = tqdm(total=10, desc="AI Video Processing")
    for _ in range(10):
        time.sleep(6)
        state = check_gemini_file_status(file_name_api)
        pbar.update(1)
        if state == "ACTIVE":
            break
        if state in ["FAILED", "ERROR"]:
            pbar.close()
            print(f"❌ Error: Gemini failed to process video. State: {state}")
            delete_gemini_file(file_name_api)
            return None
    pbar.close()
    
    print("⏳ Giving Google transcoders a 15-second grace period to settle frame indexing...")
    time.sleep(15)

    # Attempt to fetch captions to provide richer context
    caption_text = None
    if video_id:
        youtube = get_youtube_client()
        caption_text = fetch_captions(youtube, video_id=video_id)
    
    print("🤖 Analyzing gameplay video visually using Gemini 2.5 Flash...")
    transcript_section = f"\n    Video Transcript (if available):\n    {caption_text}\n" if caption_text else ""
    prompt = f"""
    You are an expert gameplay analyst, esports editor, and extremely funny YouTube channel manager for a Diablo IV campaign and gameplay series.
    Please visually watch the uploaded gameplay video frames and perform a deep semantic indexing and funny optimization.
    {transcript_section}
    Video original details (for context):
    Original Title: {orig_title}
    Original Description: {orig_description}
    
    CRITICAL REWRITE DIRECTIONS:
    - Do NOT hallucinate generic Diablo IV endgame memes (like "莉莉絲的微笑", "畢業裝備", "新賽季刷寶", "賽季結束肝也結束") unless they are actually visible in the video frames, mentioned in the original title, or appear in the provided transcript.
    - Focus your humor, timestamps, and description tightly on the actual gameplay, the specific quest campaign story (e.g., Vessel of Hatred quest names), or visual highlights observed in the video frames and transcript.
    - Keep all terminology strictly using Traditional Chinese (Taiwan).
    
    Requirements:
    1. funny_title: A hilarious, viral Traditional Chinese (Taiwanese) clickbait title reflecting gameplay highlights.
    2. funny_description: A highly engaging, self-deprecating video description (Traditional Chinese/Taiwanese).
    3. visual_index: A detailed list of key events and highlights that you observed in the video frames. For each event, provide:
       - time: The exact timestamp in standard MM:SS format.
       - event: A clear, descriptive summary of what happens on screen at that moment. This will be used in our Local Asset Library to let us search and repurpose video fragments later!
       Aim for at least 3-6 distinct highlights/chapters throughout the video.
    4. funny_timestamps: Generate at least 3 funny time-stamps in standard MM:SS format representing highly relevant, funny narrative checkpoints matching the quest theme or gameplay.
    
    Return your output strictly as a JSON object with this exact structure:
    {{
      "funny_title": "...",
      "funny_description": "...",
      "visual_index": [
        {{"time": "00:00", "event": "..."}},
        {{"time": "01:23", "event": "..."}}
      ],
      "funny_timestamps": "00:00 精彩開場\\n01:30 智商掉線\\n02:45 爆笑收尾"
    }}
    """
    
    try:
        ai_response = call_gemini(prompt, file_uri=file_uri, mime_type="video/mp4")
        
        # Robust parsing
        import re
        match = re.search(r"\{.*\}", ai_response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(ai_response)
    except Exception as e:
        print(f"❌ Failed to parse Gemini multi-modal response: {e}")
        print(f"Raw Response: {ai_response}")
        return None
    finally:
        # Clean up files both locally and on Gemini
        delete_gemini_file(file_name_api)
        if os.path.exists(video_path):
            os.remove(video_path)
            print("🗑️ Cleaned up temporary local downloaded video file.")

# ==========================================
# 🛠️ YOUTUBE ACTIONS & OPERATIONS
# ==========================================
def cmd_login(args):
    """Triggers login and OAuth 2.0 flow to cache token"""
    print("🔑 Authenticating and verifying Google / YouTube account...")
    youtube = get_youtube_client()
    print("✅ Authentication successful! Connected to YouTube channel.")

# ==========================================
# 📂 LOCAL ASSET DATABASE & CMS UTILITIES
# ==========================================
DB_FILE = "video_library.json"

def load_library():
    """Loads local video asset database"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Warning loading video_library.json: {e}")
    return {}

def save_library(db):
    """Saves local video asset database"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Failed to save video_library.json: {e}")

import hashlib

def calculate_file_hash(filepath):
    """Calculates SHA-256 hash of a file to verify content changes"""
    if not filepath or not os.path.exists(filepath):
        return None
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return None

def get_video_duration(filepath):
    """Gets duration of a video using ffprobe"""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        import subprocess
        cmd = ["ffprobe", "-i", filepath, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
        out = subprocess.check_output(cmd).decode("utf-8").strip()
        return float(out)
    except Exception:
        return None

def update_library_entry(video_id, data, file_hash=None, duration=None, live_stats=None):
    """Updates or inserts a video entry in the local database, keeping a history of indexing runs"""
    db = load_library()
    
    # Check if there is an existing entry
    if video_id not in db:
        db[video_id] = {
            "video_id": video_id,
            "original_title": data.get("original_title", ""),
            "original_description": data.get("original_description", ""),
            "published_at": data.get("published_at", ""),
            "file_hash": file_hash,
            "duration_seconds": duration,
            "active_version": 1,
            "versions": []
        }
    else:
        # If the file hash changed, print warning
        old_hash = db[video_id].get("file_hash")
        if old_hash and file_hash and old_hash != file_hash:
            print(f"\n⚠️ WARNING: Detected that the video content has been modified or edited online!")
            print(f"   Old SHA-256 Hash: {old_hash[:12]}...")
            print(f"   New SHA-256 Hash: {file_hash[:12]}...\n")
        
        if file_hash:
            db[video_id]["file_hash"] = file_hash
        if duration:
            db[video_id]["duration_seconds"] = duration
            
        if "versions" not in db[video_id]:
            db[video_id]["versions"] = []

    # Build the new version item
    new_version_id = len(db[video_id].get("versions", [])) + 1
    new_version = {
        "version_id": new_version_id,
        "indexed_at": datetime.now().isoformat(),
        "funny_title": data.get("funny_title", ""),
        "funny_description": data.get("funny_description", ""),
        "funny_timestamps": data.get("funny_timestamps", ""),
        "visual_index": data.get("visual_index", []),
        "snapshot_stats": live_stats
    }
    
    db[video_id]["versions"].append(new_version)
    db[video_id]["active_version"] = new_version_id
    db[video_id]["last_updated"] = datetime.now().isoformat()
    
    # For backward compatibility and easy lookup, keep active title/desc/index in top-level too
    db[video_id]["funny_title"] = data.get("funny_title", "")
    db[video_id]["funny_description"] = data.get("funny_description", "")
    db[video_id]["funny_timestamps"] = data.get("funny_timestamps", "")
    db[video_id]["visual_index"] = data.get("visual_index", [])
    db[video_id]["published_at"] = data.get("published_at") or db[video_id].get("published_at") or ""
    db[video_id]["category_id"] = data.get("category_id") or db[video_id].get("category_id") or "20"
    
    save_library(db)


def cmd_list(args):
    """Lists the latest videos from channel, automatically indexing/updating them in local database"""
    youtube = get_youtube_client()
    print("📺 Fetching latest videos from your channel...")
    
    try:
        # Get channel's upload playlist ID
        channel_resp = youtube.channels().list(mine=True, part="contentDetails").execute()
        uploads_playlist = channel_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # List playlist items
        playlist_items = youtube.playlistItems().list(
            playlistId=uploads_playlist,
            part="snippet",
            maxResults=args.limit
        ).execute()
        
        db = load_library()
        updated_count = 0
        
        print("\n| Video ID | Title | Published At | Status |")
        print("| :--- | :--- | :--- | :--- |")
        for item in playlist_items.get("items", []):
            video_id = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"]["title"]
            pub_at = item["snippet"]["publishedAt"][:10]
            desc = item["snippet"].get("description", "")
            
            is_new = video_id not in db
            if is_new or db[video_id].get("original_title") != title:
                db[video_id] = db.get(video_id, {})
                db[video_id].update({
                    "video_id": video_id,
                    "original_title": title,
                    "original_description": desc,
                    "published_at": item["snippet"]["publishedAt"],
                    "indexed_at": datetime.now().isoformat()
                })
                updated_count += 1
                
            status_icon = "🟢 Optimized" if db[video_id].get("funny_title") else "⚪ Raw"
            print(f"| `{video_id}` | {title} | {pub_at} | {status_icon} |")
        
        if updated_count > 0:
            save_library(db)
            print(f"\n📂 Automatically indexed/updated {updated_count} videos in the local asset library.")
        else:
            print("\n📂 Local asset library is already up to date.")
        print()
    except Exception as e:
        print(f"❌ Failed to list videos: {e}")

def generate_and_upload_multilingual_subtitles(youtube, video_id, funny_title, funny_desc, funny_timestamps, visual_index, duration_iso="PT5M"):
    """Automatically generates sarcastic Traditional Chinese subtitles and translates/uploads to 7 languages"""
    print("\n✍️ Generating automatically timed Traditional Chinese AI Narrator Subtitles...")
    
    prompt = f"""
    You are a professional, sarcastic, and extremely humorous Taiwanese YouTube narrator for gaming channels.
    Based on the following video metadata:
    - Title: {funny_title}
    - Description: {funny_desc}
    - Highlight timestamps: {funny_timestamps}
    - Video Duration (ISO 8601 format): {duration_iso}
    
    Generate a complete, fully formed subtitle track in SRT format representing a hilarious, sarcastic narrator play-by-play commentary.
    The narrator should sound mystical, witty, and extremely funny, talking directly to the audience (in Traditional Chinese (Taiwan)).
    
    CRITICAL REQUIREMENTS:
    1. Output ONLY the raw SRT text. Do not wrap in markdown code blocks or backticks.
    2. Write between 8 to 15 subtitle blocks spaced logically across the timeline from 00:00:00,000 to the end of the video.
    3. Ensure the SRT timestamps are formatted correctly: HH:MM:SS,mmm --> HH:MM:SS,mmm
    4. Ensure all Chinese terminology strictly uses Traditional Chinese (Taiwan).
    5. The subtitles should feel like a cohesive, hilarious narration of the gameplay.
    """
    
    try:
        base_srt = call_gemini(prompt, response_mime_type="text/plain")
        # Strip any leading/trailing markdown code block fences and extra whitespace
        import re
        base_srt = re.sub(r"^```[a-zA-Z]*\s*", "", base_srt)
        base_srt = re.sub(r"\s*```$", "", base_srt)
        base_srt = base_srt.strip()
        
        # Validate that the response looks like an SRT file
        if "-->" not in base_srt:
            print("⚠️ Generated subtitle content did not follow SRT format. Skipping subtitle upload.")
            return
            
        # Define languages to translate and upload
        languages = [
            {"code": "zh-TW", "name": "繁體中文 (AI 搞笑版)", "local_name": "Traditional Chinese"},
            {"code": "en", "name": "English (AI Sarcastic)", "local_name": "English"},
            {"code": "es", "name": "Español (AI Sarcástico)", "local_name": "Spanish"},
            {"code": "ja", "name": "日本語 (AI ツッコミ)", "local_name": "Japanese"},
            {"code": "ko", "name": "한국어 (AI 풍자)", "local_name": "Korean"},
            {"code": "de", "name": "Deutsch (AI Sarkastisch)", "local_name": "German"},
            {"code": "fr", "name": "Français (AI Sarcastique)", "local_name": "French"}
        ]
        
        # Fetch existing captions to avoid 409 conflict and cleanly overwrite
        existing_captions = []
        try:
            captions_resp = youtube.captions().list(part="snippet", videoId=video_id).execute()
            existing_captions = captions_resp.get("items", [])
        except Exception as list_err:
            print(f"⚠️ Warning: Could not fetch existing captions: {list_err}")
            
        from googleapiclient.http import MediaFileUpload
        import tempfile
        
        for lang in languages:
            lang_code = lang["code"]
            lang_name = lang["name"]
            
            if lang_code == "zh-TW":
                srt_content = base_srt
            else:
                print(f"🌎 Translating AI Subtitles to {lang['local_name']}...")
                trans_prompt = f"""
                Translate the following Traditional Chinese SRT subtitle file into {lang['local_name']}.
                
                CRITICAL REQUIREMENTS:
                1. Output ONLY the raw translated SRT text. Do not wrap in markdown or backticks.
                2. Keep all timestamps, sequence numbers, and formatting EXACTLY the same.
                3. Ensure the translated language sounds natural, funny, and captures the original sarcastic gamer vibe!
                
                SRT Content:
                {base_srt}
                """
                srt_content = call_gemini(trans_prompt, response_mime_type="text/plain")
                srt_content = re.sub(r"^```[a-zA-Z]*\s*", "", srt_content)
                srt_content = re.sub(r"\s*```$", "", srt_content)
                srt_content = srt_content.strip()
            
            # Write to a temporary file
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".srt", delete=False, encoding="utf-8") as temp_file:
                temp_file.write(srt_content)
                temp_file_path = temp_file.name
                
            # Check if this exact track already exists and delete it to prevent 409
            existing_track_id = None
            for track in existing_captions:
                track_snippet = track.get("snippet", {})
                if track_snippet.get("language") == lang_code and track_snippet.get("name") == lang_name:
                    existing_track_id = track.get("id")
                    break
                    
            if existing_track_id:
                try:
                    print(f"🗑️ Deleting old {lang['local_name']} caption track '{existing_track_id}' to prevent conflict...")
                    youtube.captions().delete(id=existing_track_id).execute()
                except Exception as del_err:
                    print(f"⚠️ Warning: Could not delete old caption track: {del_err}")
            
            try:
                print(f"🔤 Uploading {lang['local_name']} subtitles to video '{video_id}'...")
                media = MediaFileUpload(temp_file_path, mimetype="application/octet-stream", resumable=True)
                request = youtube.captions().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "language": lang_code,
                            "name": lang_name,
                            "isDraft": False
                        }
                    },
                    media_body=media
                )
                
                response = None
                while response is None:
                    status, response = request.next_chunk()
                print(f"✅ {lang['local_name']} subtitles uploaded successfully!")
            except Exception as upload_err:
                print(f"⚠️ Failed to upload {lang['local_name']} subtitles: {upload_err}")
            finally:
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Failed to generate or process subtitles: {e}")

def cmd_process(args):
    """Rewrites title/description with AI, adds funny timestamps, updates YouTube, and indexes result"""
    youtube = get_youtube_client()
    video_id = args.video_id
    
    print(f"🔍 Fetching metadata & live statistics for video: {video_id}...")
    try:
        # Request snippet, statistics, and contentDetails in a single call to save latency and quota!
        video_resp = youtube.videos().list(part="snippet,statistics,contentDetails", id=video_id).execute()
        if not video_resp.get("items"):
            print(f"❌ Error: Video '{video_id}' not found!")
            return
            
        video_item = video_resp["items"][0]
        snippet = video_item["snippet"]
        orig_title = snippet["title"]
        orig_desc = snippet.get("description", "")
        orig_category = snippet.get("categoryId", "20") # default to gaming (20)
        
        # Extract precise ISO 8601 duration
        duration_iso = video_item.get("contentDetails", {}).get("duration", "PT5M")
        
        # Capture a live metrics snapshot at this transition point!
        statistics = video_item.get("statistics", {})
        live_stats = {
            "views": int(statistics.get("viewCount", 0)),
            "likes": int(statistics.get("likeCount", 0)),
            "comments": int(statistics.get("commentCount", 0)),
            "favorites": int(statistics.get("favoriteCount", 0))
        }
        print(f"📊 Live Metrics Snapshot Captured: Views={live_stats['views']}, Likes={live_stats['likes']}, Comments={live_stats['comments']}")
        print(f"📝 Original Title: {orig_title}")
        
        # Download video to local /tmp using yt-dlp
        video_path = download_lowres_video(video_id)
        if not video_path:
            # Fallback path
            print("🤖 Invoking Google Gemini 2.5 Flash for pure-text semantic analysis (Fallback)...")
            ai_data = generate_funny_metadata(orig_title, orig_desc)
            funny_title = ai_data["funny_title"]
            funny_desc = ai_data["funny_description"]
            timestamps = ai_data["funny_timestamps"]
            visual_index = []
        else:
            print("🤖 Invoking Google Gemini 2.5 Flash for multi-modal visual analysis...")
            ai_data = analyze_video_multimodal(video_path, orig_title, orig_desc, video_id=video_id)
            if not ai_data:
                print("❌ Error: Gemini failed to visually analyze the gameplay video!")
                return
            funny_title = ai_data["funny_title"]
            funny_desc = ai_data["funny_description"]
            timestamps = ai_data["funny_timestamps"]
            visual_index = ai_data.get("visual_index", [])
            
        # Combine funny description with timestamps and archive the original title/timestamp
        combined_desc = f"{funny_desc}\n\n🎬 【本期精彩亮點】\n{timestamps}\n\n📌 【原始記錄存檔】\n原標題：{orig_title}"
        
        print("\n=== ✨ AI GENERATED PREVIEW ===")
        print(f"🏆 NEW TITLE: {funny_title}")
        print(f"📝 NEW DESCRIPTION:\n{combined_desc}")
        if visual_index:
            print("\n📂 VISUAL INDEX LOGGED TO MATERIAL LIBRARY:")
            for highlight in visual_index:
                print(f"  🎬 [{highlight['time']}] {highlight['event']}")
        print("===============================\n")
        
        # Save to local library (Always record visual index to Material Bank!)
        file_hash = calculate_file_hash(video_path) if video_path else None
        duration = get_video_duration(video_path) if video_path else None
        
        update_library_entry(video_id, {
            "video_id": video_id,
            "original_title": orig_title,
            "original_description": orig_desc,
            "funny_title": funny_title,
            "funny_description": funny_desc,
            "funny_timestamps": timestamps,
            "visual_index": visual_index,
            "category_id": orig_category,
            "optimized_at": datetime.now().isoformat()
        }, file_hash=file_hash, duration=duration, live_stats=live_stats)
        print("📂 Successfully indexed gameplay video and visual segments into local Material Bank (video_library.json)!")
        
        # Optionally publish to YouTube
        should_update = True
        if not args.yes:
            confirm = input("❓ Push these funny metadata updates live to YouTube? (y/N): ")
            if confirm.lower() != "y":
                print("❌ Skipped live YouTube sync. Local material index is preserved!")
                should_update = False
                
        if should_update:
            print("🚀 Syncing updates to YouTube...")
            update_resp = youtube.videos().update(
                part="snippet",
                body={
                    "id": video_id,
                    "snippet": {
                        "title": funny_title,
                        "description": combined_desc,
                        "categoryId": orig_category
                    }
                }
            ).execute()
            print(f"✅ Live YouTube video '{video_id}' successfully updated!")
            
            # Automatically generate and upload multilingual subtitles
            if not getattr(args, "no_subtitles", False):
                generate_and_upload_multilingual_subtitles(
                    youtube=youtube,
                    video_id=video_id,
                    funny_title=funny_title,
                    funny_desc=funny_desc,
                    funny_timestamps=timestamps,
                    visual_index=visual_index,
                    duration_iso=duration_iso
                )
        
        # Playlist assignment
        target_playlist_ids = []
        if args.playlist_id:
            target_playlist_ids.append(args.playlist_id)
        
        # If user did not supply a specific playlist ID but synced to YouTube, activate Smart Playlist selector!
        if not target_playlist_ids and should_update:
            print("\n🧠 Activating AI Smart Playlist classification...")
            # Sleep 2 seconds to let Gemini API rate limits cool down from back-to-back calls
            import time
            time.sleep(2)
            
            decision = match_or_create_playlist_with_ai(youtube, funny_title, funny_desc)
            matches = decision.get("matches", [])
            for match in matches:
                if match.get("match_found"):
                    pid = match.get("playlist_id")
                    ptitle = match.get("playlist_title")
                    print(f"🎯 AI matched this video to existing playlist: '{ptitle}' (ID: {pid})")
                    print(f"💡 Reason: {match.get('reason')}")
                    target_playlist_ids.append(pid)
                else:
                    new_title = match.get("playlist_title", "精選影片庫")
                    print(f"🆕 AI recommended creating a new playlist: '{new_title}'")
                    print(f"💡 Reason: {match.get('reason')}")
                    try:
                        create_resp = youtube.playlists().insert(
                            part="snippet,status",
                            body={
                                "snippet": {
                                    "title": new_title,
                                    "description": "Auto-created by Smart YouTube AI Manager",
                                    "defaultLanguage": "zh-TW"
                                },
                                "status": {
                                    "privacyStatus": "public"
                                }
                            }
                        ).execute()
                        new_pid = create_resp["id"]
                        print(f"✅ Successfully created playlist '{new_title}' (ID: {new_pid})!")
                        target_playlist_ids.append(new_pid)
                    except Exception as ex:
                        print(f"⚠️ Failed to create new playlist: {ex}")
        
        if target_playlist_ids and should_update:
            for pid in target_playlist_ids:
                print(f"➕ Adding video to playlist '{pid}'...")
                try:
                    youtube.playlistItems().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "playlistId": pid,
                                "resourceId": {
                                    "kind": "youtube#video",
                                    "videoId": video_id
                                }
                            }
                        }
                    ).execute()
                    print(f"✅ Added to playlist '{pid}' successfully!")
                except Exception as ex:
                    print(f"⚠️ Failed to add video to playlist '{pid}': {ex}")
            
    except Exception as e:
        print(f"❌ Operation failed: {e}")

def cmd_library(args):
    """Subcommand to query, list, or search the local asset library"""
    db = load_library()
    if not db:
        print("📂 Local video library is empty. Please run 'list' or 'process' to index videos first!")
        return

    if args.subcommand == "list":
        print(f"📂 Local Asset Library: {len(db)} indexed videos")
        print("\n| Video ID | Title | Status | Versions | Duration | Last Updated |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for video_id, item in db.items():
            title = item.get("funny_title") or item.get("original_title")
            if len(title) > 30:
                title = title[:27] + "..."
            status = "🟢 Optimized" if item.get("funny_title") else "⚪ Raw"
            versions_count = len(item.get("versions", []))
            if versions_count == 0:
                versions_count = 1 if item.get("funny_title") else 0
                
            dur_sec = item.get("duration_seconds")
            if dur_sec:
                m, s = divmod(int(dur_sec), 60)
                h, m = divmod(m, 60)
                dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            else:
                dur_str = "--"
                
            last_up = item.get("last_updated", item.get("indexed_at", ""))[:19].replace("T", " ")
            print(f"| `{video_id}` | {title} | {status} | {versions_count} | {dur_str} | {last_up} |")
        print()

    elif args.subcommand == "search":
        query = args.query.lower()
        print(f"🔍 Searching local asset library for: '{args.query}'...\n")
        results = []
        for video_id, item in db.items():
            in_orig_title = query in item.get("original_title", "").lower()
            in_orig_desc = query in item.get("original_description", "").lower()
            in_funny_title = query in item.get("funny_title", "").lower() if item.get("funny_title") else False
            in_funny_desc = query in item.get("funny_description", "").lower() if item.get("funny_description") else False
            in_ts = query in item.get("funny_timestamps", "").lower() if item.get("funny_timestamps") else False
            
            # Check visual index highlights
            in_vi = False
            matching_events = []
            for highlight in item.get("visual_index", []):
                if query in highlight.get("event", "").lower() or query in highlight.get("time", "").lower():
                    in_vi = True
                    matching_events.append(highlight)
            
            if in_orig_title or in_orig_desc or in_funny_title or in_funny_desc or in_ts or in_vi:
                results.append((video_id, item, matching_events))
                
        if not results:
            print("❌ No matching video assets found.")
            return
            
        print(f"🎉 Found {len(results)} matching video assets:\n")
        for idx, (video_id, item, matching_events) in enumerate(results, 1):
            is_opt = "funny_title" in item
            title = item.get("funny_title") or item.get("original_title")
            print(f"{idx}. [{is_opt and '🟢' or '⚪'}] {title} (ID: `{video_id}`)")
            print(f"   📅 Published At: {item.get('published_at')[:10]}")
            
            versions_count = len(item.get("versions", []))
            if versions_count == 0:
                versions_count = 1 if item.get("funny_title") else 0
                
            dur_sec = item.get("duration_seconds")
            if dur_sec:
                m, s = divmod(int(dur_sec), 60)
                h, m = divmod(m, 60)
                dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            else:
                dur_str = "--"
                
            print(f"   📊 Version Control: Active Version: v{item.get('active_version', 1)} / Total Versions: {versions_count} | Duration: {dur_str}")
            if item.get("file_hash"):
                print(f"   🔒 SHA-256 Hash: {item.get('file_hash')[:16]}...")
            
            if matching_events:
                print("   🎯 Matching Visual Highlights:")
                for event in matching_events:
                    print(f"      🎬 [{event['time']}] {event['event']}")
                    
            if is_opt:
                print(f"   ✨ Funny Title: {item.get('funny_title')}")
                print(f"   🎬 Timestamps:\n" + "\n".join("      " + line for line in item.get("funny_timestamps", "").splitlines()))
            else:
                print(f"   📝 Original Description: {item.get('original_description')[:120]}...")
            print("-" * 50)

    elif args.subcommand == "clip":
        video_id = args.video_id
        start_time = args.start_time
        duration = args.duration
        
        # Convert start_time (MM:SS or HH:MM:SS) to seconds
        try:
            parts = start_time.split(":")
            if len(parts) == 3:
                start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                start_sec = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 1:
                start_sec = int(parts[0])
            else:
                raise ValueError
        except ValueError:
            print("❌ Invalid start_time format. Please use MM:SS (e.g., 00:11) or raw seconds.")
            return
            
        end_sec = start_sec + duration
        
        # Format times for yt-dlp section selector (HH:MM:SS)
        def format_sec(s):
            m, sec = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{sec:02d}"
            
        start_fmt = format_sec(start_sec)
        end_fmt = format_sec(end_sec)
        
        print(f"🎬 Clipping segment from video '{video_id}'...")
        print(f"⏱️ Time Range: {start_time} to {format_sec(end_sec)[3:]} ({duration}s duration)")
        
        # Create clips directory if it doesn't exist
        os.makedirs("clips", exist_ok=True)
        
        cookies_opts = ""
        if os.path.exists("cookies.txt"):
            cookies_opts = "--cookies cookies.txt"
        elif os.path.exists("/home/ubuntu/youtube-ai-manager/cookies.txt"):
            cookies_opts = "--cookies /home/ubuntu/youtube-ai-manager/cookies.txt"
            
        output_path = f"clips/{video_id}_clip_{start_time.replace(':', '_')}.%(ext)s"
        
        # Download the full low-res MP4 locally first to bypass range bot-detection
        print("📥 Downloading video file from YouTube (using progressive stream bypass)...")
        temp_path = f"/tmp/clip_temp_{video_id}.mp4"
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        download_cmd = (
            f"yt-dlp {cookies_opts} --js-runtimes node --remote-components ejs:github "
            f"-f '18/worst[ext=mp4]/worst' -o '{temp_path}' "
            f"https://www.youtube.com/watch?v={video_id}"
        )
        ret = os.system(download_cmd)
        if ret != 0:
            print("⚠️ Primary download blocked. Retrying worst format bypass...")
            download_cmd_fallback = (
                f"yt-dlp {cookies_opts} --js-runtimes node --remote-components ejs:github "
                f"-f '18/worst' -o '{temp_path}' "
                f"https://www.youtube.com/watch?v={video_id}"
            )
            ret = os.system(download_cmd_fallback)
            
        if ret != 0 or not os.path.exists(temp_path):
            print("\n❌ Failed to download source video from YouTube for clipping.")
            return
            
        # Cut the clip locally using ffmpeg
        print("✂️ Clipping segment locally using ffmpeg...")
        output_file_name = f"clips/{video_id}_clip_{start_time.replace(':', '_')}.mp4"
        
        ffmpeg_cmd = f"ffmpeg -y -ss {start_sec} -t {duration} -i '{temp_path}' -c copy '{output_file_name}' >/dev/null 2>&1"
        ffmpeg_ret = os.system(ffmpeg_cmd)
        
        # Clean up temporary download file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if ffmpeg_ret == 0 and os.path.exists(output_file_name):
            print(f"\n🎉 Success! The segment clip has been saved to: {output_file_name}")
        else:
            print("\n❌ Failed to extract segment clip locally using ffmpeg.")

def get_channel_playlists(youtube):
    """Fetches all playlists for the authenticated channel"""
    playlists = []
    try:
        request = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50
        )
        while request:
            response = request.execute()
            for item in response.get("items", []):
                playlists.append({
                    "id": item["id"],
                    "title": item["snippet"]["title"],
                    "description": item["snippet"].get("description", "")
                })
            request = youtube.playlists().list_next(request, response)
    except Exception as e:
        print(f"⚠️ Error fetching playlists: {e}")
    return playlists

def match_or_create_playlist_with_ai(youtube, funny_title, funny_desc):
    """Uses Gemini 2.5 Flash to automatically match video to existing playlists or suggest a new one to create (multi-matching)"""
    playlists = get_channel_playlists(youtube)
    
    # Format current playlists for Gemini prompt
    playlists_str = ""
    if playlists:
        playlists_str = "\n".join([f"- ID: {p['id']} | Title: '{p['title']}' | Desc: {p['description'][:60]}" for p in playlists])
    else:
        playlists_str = "(No playlists exist yet)"
        
    prompt = f"""
You are a brilliant YouTube Operations AI. Your job is to classify this new gameplay video into the most suitable YouTube Playlist(s).
A video can be added to multiple playlists if it fits them perfectly.

NEW VIDEO DETAILS:
- Title: "{funny_title}"
- Description: "{funny_desc}"

CURRENT CHANNEL PLAYLISTS:
{playlists_str}

CRITICAL RULES FOR DIABLO IV PLAYLIST MATCHING:
1. If the video title, original title, or description is about "暗黑破壞神 IV" (Diablo IV) S13 / DLC2 Campaign (Vessel of Hatred / 憎恨之王 / campaign quests like "視外安寧" or "開頭動畫"), you MUST classify it into the "暗黑破壞神 IV DLC2 - 憎恨之王" playlist (ID: PLf8YBO_7cL_Dg4AjLOPl7rJA-RoZJxufR)!
2. This "暗黑破壞神 IV DLC2 - 憎恨之王" playlist is the user's primary campaign showcase. Matching this playlist is the absolute highest priority.
3. If fits exist, set "match_found" to true and provide the matching "playlist_id" and "playlist_title" inside the "matches" list.
4. Do not suggest creating a new playlist if "暗黑破壞神 IV DLC2 - 憎恨之王" matches the game series.

TASKS:
1. Scan the list of CURRENT CHANNEL PLAYLISTS.
2. Identify all playlists that are a great fit for the video (match based on game names, genres, or thematic content). A video can match MULTIPLE playlists (typically 1 to 3).
3. If fits exist, set "match_found" to true and provide the matching "playlist_id" and "playlist_title" inside the "matches" list.
4. If the video represents a brand new game or thematic category not covered by existing playlists, you can suggest 1 brand new, creative playlist in "playlist_title" (with "match_found" set to false) to be created.
5. Provide a short, logical explanation in "reason" (in Traditional Chinese) for each matched or recommended playlist.

Respond ONLY with a valid JSON block of this schema:
{{
  "matches": [
    {{
      "match_found": true,
      "playlist_id": "string",
      "playlist_title": "string",
      "reason": "string"
    }}
  ]
}}
"""
    api_key = load_gemini_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    import time
    max_retries = 6
    backoff = 3
    for attempt in range(max_retries):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, context=ctx) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text_resp = res_data["candidates"][0]["content"]["parts"][0]["text"]
                decision = json.loads(text_resp)
                return decision
        except urllib.error.HTTPError as e:
            if e.code in [500, 503, 429] and attempt < max_retries - 1:
                print(f"⚠️ Playlist AI returned {e.code}. Retrying in {backoff} seconds (Attempt {attempt+1}/{max_retries})...")
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"⚠️ Error running Smart Playlist AI Decision: HTTP Error {e.code}")
            break
        except Exception as e:
            print(f"⚠️ Error running Smart Playlist AI Decision: {e}")
            break
            
    return {"matches": [{"match_found": False, "playlist_id": None, "playlist_title": "精選影片庫", "reason": "Fallback due to API error"}]}

def cmd_playlists(args):
    """Lists current playlists or creates a new one"""
    youtube = get_youtube_client()
    
    if args.create:
        print(f"📁 Creating new playlist: '{args.create}'...")
        try:
            resp = youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": args.create,
                        "description": "Auto-organized by YouTube AI Manager",
                        "defaultLanguage": "zh-TW"
                    },
                    "status": {
                        "privacyStatus": "public"
                    }
                }
            ).execute()
            print(f"✅ Playlist created successfully! ID: `{resp['id']}`")
        except Exception as e:
            print(f"❌ Failed to create playlist: {e}")
        return

    print("📁 Fetching your channel playlists...")
    try:
        resp = youtube.playlists().list(part="snippet", mine=True).execute()
        print("\n| Playlist ID | Title | Description |")
        print("| :--- | :--- | :--- |")
        for item in resp.get("items", []):
            p_id = item["id"]
            title = item["snippet"]["title"]
            desc = item["snippet"].get("description", "")
            if len(desc) > 30:
                desc = desc[:27] + "..."
            print(f"| `{p_id}` | {title} | {desc} |")
        print()
    except Exception as e:
        print(f"❌ Failed to list playlists: {e}")

def cmd_caption(args):
    """Uploads subtitles (SRT/VTT) to a video"""
    youtube = get_youtube_client()
    video_id = args.video_id
    srt_path = args.file
    
    if not os.path.exists(srt_path):
        print(f"❌ Subtitle file not found: {srt_path}")
        return
        
    print(f"🔤 Uploading subtitles '{srt_path}' to video '{video_id}'...")
    try:
        from googleapiclient.http import MediaFileUpload
        
        media = MediaFileUpload(srt_path, mimetype="application/octet-stream", resumable=True)
        request = youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": args.lang,
                    "name": args.name,
                    "isDraft": False
                }
            },
            media_body=media
        )
        
        # Upload with progress bar
        response = None
        pbar = tqdm(total=100, desc="Uploading caption")
        while response is None:
            status, response = request.next_chunk()
            if status:
                pbar.update(int(status.progress() * 100) - pbar.n)
        pbar.close()
        
        print("✅ Caption file uploaded successfully!")
    except Exception as e:
        print(f"❌ Caption upload failed: {e}")

# ==========================================
# 🏁 MAIN ENTRY POINT
# ==========================================
def main():
    parser = argparse.ArgumentParser(
        description="🎬 YouTube AI Manager: Auto-Optimize, Humorize, and Auto-Playlist your YouTube Channel!",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--channel",
        help="Target YouTube channel profile name (e.g. gamelife, virtualworld). Saves credentials to token_<channel>.json"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    
    # 1. Login
    subparsers.add_parser("login", help="Authenticate with your YouTube account")
    
    # 2. List Videos
    parser_list = subparsers.add_parser("list", help="List recent videos from your channel")
    parser_list.add_argument("--limit", type=int, default=10, help="Maximum number of videos to display (default: 10)")
    
    # 3. Process Video
    parser_process = subparsers.add_parser("process", help="Optimize a video with funny title, description, and timestamps")
    parser_process.add_argument("video_id", help="Target YouTube Video ID")
    parser_process.add_argument("--playlist-id", help="Optional Playlist ID to add the video to")
    parser_process.add_argument("--yes", "-y", action="store_true", help="Auto-apply changes without asking for confirmation")
    parser_process.add_argument("--no-subtitles", action="store_true", help="Disable automatic generation and upload of multilingual subtitles")

    
    # 4. Playlists
    parser_playlists = subparsers.add_parser("playlists", help="List or create playlists")
    parser_playlists.add_argument("--create", help="Create a new playlist with the specified title")
    
    # 5. Caption Upload
    parser_caption = subparsers.add_parser("caption", help="Upload a SRT/VTT subtitle file to a video")
    parser_caption.add_argument("video_id", help="Target YouTube Video ID")
    parser_caption.add_argument("file", help="Path to .srt or .vtt subtitle file")
    parser_caption.add_argument("--lang", default="zh-TW", help="Subtitle language code (default: zh-TW)")
    parser_caption.add_argument("--name", default="繁體中文 (AI 搞笑版)", help="Display name for the subtitle track")
    
    # 6. Local Library Subcommand
    parser_library = subparsers.add_parser("library", help="Query, list, or search the local asset library")
    library_sub = parser_library.add_subparsers(dest="subcommand", required=True, help="Library actions")
    
    # 6a. library list
    library_sub.add_parser("list", help="List all indexed video assets")
    
    # 6b. library search
    parser_search = library_sub.add_parser("search", help="Search the local asset database by keyword")
    parser_search.add_argument("query", help="Keyword to search in titles, descriptions, and timestamps")
    
    # 6c. library clip
    parser_clip = library_sub.add_parser("clip", help="Extract and download a specific segment clip of a video")
    parser_clip.add_argument("video_id", help="Target YouTube Video ID")
    parser_clip.add_argument("start_time", help="Start time in MM:SS format (e.g. 00:11)")
    parser_clip.add_argument("--duration", type=int, default=15, help="Clip duration in seconds (default: 15)")

    args = parser.parse_args()
    
    global TOKEN_FILE
    if args.channel:
        TOKEN_FILE = f"token_{args.channel}.json"
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    if args.command == "login":
        cmd_login(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "process":
        cmd_process(args)
    elif args.command == "playlists":
        cmd_playlists(args)
    elif args.command == "caption":
        cmd_caption(args)
    elif args.command == "library":
        cmd_library(args)

if __name__ == "__main__":
    main()
