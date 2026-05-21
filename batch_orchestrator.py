#!/usr/bin/env python3
"""
🎬 YouTube AI Batch Orchestrator
High-level campaign scheduler, state manager, and performance tracker.
Decoupled from youtube_ai_manager.py.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime

STATE_FILE = "batch_state.json"

def get_youtube_client(channel_name=None):
    """
    Dynamically loads credentials and returns an authenticated YouTube client.
    Imports from youtube_ai_manager to reuse the OAuth flow!
    """
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import youtube_ai_manager
    if channel_name:
        youtube_ai_manager.TOKEN_FILE = f"token_{channel_name}.json"
    return youtube_ai_manager.get_youtube_client()

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"campaign_name": "Diablo IV", "created_at": datetime.now().isoformat(), "queue": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def cmd_init(args):
    """Initializes campaign queue based on date/keyword filters or specific starting video"""
    channel = args.channel
    start_id = args.start_id
    filter_keyword = args.filter
    since_date = args.since
    
    youtube = get_youtube_client(channel)
    print(f"📺 Querying channel upload history to initialize campaign queue...")
    if since_date:
        print(f"📅 Time-Anchor Active: Filtering videos published on or after: {since_date} (S13 Season)")
    if filter_keyword:
        print(f"🔍 Topic Filter Active: Filtering videos matching keyword: '{filter_keyword}'")
    if start_id:
        print(f"📌 Starting ID Lock: Sequence starts at specific video ID: `{start_id}`")
        
    try:
        channel_resp = youtube.channels().list(mine=True, part="contentDetails").execute()
        uploads_playlist = channel_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        video_pool = []
        next_page_token = None
        found_end_by_date = False
        found_start_id = False
        
        while True:
            playlist_items = youtube.playlistItems().list(
                playlistId=uploads_playlist,
                part="snippet",
                maxResults=50,
                pageToken=next_page_token
            ).execute()
            
            items = playlist_items.get("items", [])
            if not items:
                break
                
            for item in items:
                vid = item["snippet"]["resourceId"]["videoId"]
                title = item["snippet"]["title"]
                pub_at = item["snippet"]["publishedAt"]
                
                # If since_date is set, and this video is older than since_date, stop fetching!
                # (Since uploads list is returned newest first)
                if since_date and pub_at[:10] < since_date:
                    found_end_by_date = True
                    break
                    
                video_pool.append({
                    "video_id": vid,
                    "original_title": title,
                    "published_at": pub_at
                })
                
                if start_id and vid == start_id:
                    found_start_id = True
                    break
            
            if found_end_by_date:
                break
            if start_id and found_start_id:
                break
            if not playlist_items.get("nextPageToken"):
                break
            next_page_token = playlist_items["nextPageToken"]
            
        if start_id and not found_start_id and not found_end_by_date:
            print(f"❌ Error: Starting Video ID '{start_id}' was not found in the fetched history.")
            return
            
        # Reconstruct sequence chronologically from oldest (earliest) to newest!
        raw_sequence = list(reversed(video_pool))
        
        # Apply title keyword filter
        filtered_sequence = []
        for vid_info in raw_sequence:
            match = True
            if filter_keyword:
                if filter_keyword.lower() not in vid_info["original_title"].lower():
                    match = False
            if match:
                filtered_sequence.append(vid_info)
                
        if not filtered_sequence:
            print("❌ No matching videos found with the given filters!")
            return
            
        # Initialize the state file
        state = {
            "campaign_name": filter_keyword or "Diablo IV Sequence",
            "initialized_at": datetime.now().isoformat(),
            "channel_profile": channel or "default",
            "queue": []
        }
        
        # Query current stats for all targeted videos in bulk to capture precise pre-optimization baselines!
        video_ids = [v["video_id"] for v in filtered_sequence]
        stats_map = {}
        # Chunk into groups of 50 (YouTube API limit)
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i+50]
            chunk_str = ",".join(chunk)
            stats_resp = youtube.videos().list(part="statistics", id=chunk_str).execute()
            for item in stats_resp.get("items", []):
                vid = item["id"]
                stats = item.get("statistics", {})
                stats_map[vid] = {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0))
                }
            
        for idx, vid_info in enumerate(filtered_sequence):
            vid = vid_info["video_id"]
            baseline = stats_map.get(vid, {"views": 0, "likes": 0, "comments": 0})
            state["queue"].append({
                "sequence_index": idx + 1,
                "video_id": vid,
                "title": vid_info["original_title"],
                "published_at": vid_info["published_at"],
                "status": "pending",
                "optimized_at": None,
                "baseline_stats": baseline,
                "current_stats": baseline
            })
            
        save_state(state)
        print(f"\n🎉 Successfully initialized batch campaign queue in '{STATE_FILE}'!")
        print(f"📋 Loaded {len(state['queue'])} videos targeting game topic: '{state['campaign_name']}'")
        cmd_status(args)
    except Exception as e:
        print(f"❌ Initialization failed: {e}")

def cmd_status(args):
    """Displays a gorgeous campaign status table with baseline vs current metrics"""
    state = load_state()
    queue = state.get("queue", [])
    if not queue:
        print("📂 No batch campaign initialized. Run 'init' to start a campaign queue!")
        return
        
    print(f"\n📊 Campaign: {state.get('campaign_name')} | Profile: {state.get('channel_profile')}")
    print(f"---------------------------------------------------------------------------------------------------")
    print(f"| Idx | Video ID    | Title                      | Status      | Baseline Views | Current Views | Growth |")
    print(f"| :-- | :---------- | :------------------------- | :---------- | :------------- | :------------ | :----- |")
    
    for item in queue:
        title = item["title"]
        if len(title) > 26:
            title = title[:23] + "..."
            
        status = item["status"]
        if status == "optimized":
            status_str = "🟢 Optimized"
        elif status == "in_progress":
            status_str = "🟡 Processing"
        else:
            status_str = "⚪ Pending"
            
        base_views = item["baseline_stats"].get("views", 0)
        curr_views = item["current_stats"].get("views", 0)
        growth = curr_views - base_views
        growth_str = f"+{growth}" if growth > 0 else "0"
        
        print(f"| {item['sequence_index']:3d} | `{item['video_id']}` | {title:26s} | {status_str:10s} | {base_views:14d} | {curr_views:13d} | {growth_str:6s} |")
    print(f"---------------------------------------------------------------------------------------------------")
    print(f"💡 Run 'update-stats' to refresh current views and see real-time growth!")
    print()

def cmd_update_stats(args):
    """Updates the current statistics of all videos in the queue to show real-time growth"""
    state = load_state()
    queue = state.get("queue", [])
    if not queue:
        print("📂 No batch campaign initialized. Run 'init' first.")
        return
        
    channel = state.get("channel_profile", "default")
    youtube = get_youtube_client(channel)
    print("🔄 Querying live statistics to refresh growth metrics...")
    
    try:
        video_ids = [item["video_id"] for item in queue]
        # Chunk into groups of 50 (YouTube API limit)
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i+50]
            chunk_str = ",".join(chunk)
            stats_resp = youtube.videos().list(part="statistics", id=chunk_str).execute()
            
            stats_map = {}
            for item in stats_resp.get("items", []):
                vid = item["id"]
                stats = item.get("statistics", {})
                stats_map[vid] = {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0))
                }
                
            for item in queue:
                vid = item["video_id"]
                if vid in stats_map:
                    item["current_stats"] = stats_map[vid]
                    
        save_state(state)
        print("✅ Statistics successfully refreshed!")
        cmd_status(args)
    except Exception as e:
        print(f"❌ Failed to update statistics: {e}")

def calculate_dynamic_interval(last_optimized, default_interval):
    """Dynamically calculates pacing interval based on view growth performance of the last optimized video"""
    baseline_views = last_optimized.get("baseline_stats", {}).get("views", 0)
    current_views = last_optimized.get("current_stats", {}).get("views", 0)
    growth = max(0, current_views - baseline_views)
    
    print(f"\n📊 [Dynamic Pacing Guard] Analyzing performance of last optimized video:")
    print(f"   Video ID: {last_optimized['video_id']} | Title: {last_optimized['title'][:40]}...")
    print(f"   Baseline Views: {baseline_views} | Current Views: {current_views} | Growth: +{growth} views")
    
    if growth == 0:
        dyn_interval = max(0.5, default_interval * 0.25)
        reason = "No view growth detected. Shortening interval to push updates faster and revive channel activity!"
    elif growth <= 10:
        dyn_interval = max(1.0, default_interval * 0.5)
        reason = "Slow growth detected. Pacing interval shortened to maintain active channel presence."
    elif growth <= 100:
        dyn_interval = default_interval
        reason = "Healthy growth detected. Maintaining standard pacing interval."
    elif growth <= 500:
        dyn_interval = default_interval * 2.0
        reason = "Strong traction detected! Extending interval to let this video compound organic views without disruption."
    else:
        dyn_interval = default_interval * 4.0
        reason = "🔥 Viral growth detected! Maximizing interval to let views compound and avoid content collision!"
        
    print(f"   💡 Pacing Decision: {reason}")
    print(f"   Dynamic Pacing Interval: {dyn_interval:.1f} hours (Standard: {default_interval} hours)")
    return dyn_interval

def cmd_run(args):
    """Runs a single pending item or starts a pacing cycle based on scheduling rules"""
    state = load_state()
    queue = state.get("queue", [])
    if not queue:
        print("📂 No batch campaign queue found. Run 'init' first.")
        return
        
    channel = state.get("channel_profile", "default")
    interval_hours = args.interval
    max_to_process = args.limit
    
    # Check if there are pending videos
    pending_items = [item for item in queue if item["status"] == "pending"]
    if not pending_items:
        print("🎉 All videos in this campaign queue have already been successfully optimized!")
        return
        
    # Check if we should enforce time-pacing relative to the last optimized item!
    optimized_items = [item for item in queue if item["status"] == "optimized" and item.get("optimized_at")]
    if optimized_items and (interval_hours > 0 or args.dynamic_pacing):
        # Get the most recently optimized item
        last_optimized = max(optimized_items, key=lambda x: x["optimized_at"])
        last_time = datetime.fromisoformat(last_optimized["optimized_at"].replace("Z", ""))
        elapsed_seconds = (datetime.now() - last_time).total_seconds()
        elapsed_hours = elapsed_seconds / 3600.0
        
        # If dynamic pacing is active, fetch live stats and compute dynamic interval
        if args.dynamic_pacing:
            print("🔄 [Dynamic Pacing] Fetching live stats for last optimized video from YouTube...")
            try:
                youtube = get_youtube_client(channel)
                video_resp = youtube.videos().list(part="statistics", id=last_optimized["video_id"]).execute()
                if video_resp.get("items"):
                    curr_views = int(video_resp["items"][0].get("statistics", {}).get("viewCount", 0))
                    last_optimized["current_stats"]["views"] = curr_views
                    save_state(state)
            except Exception as e:
                print(f"⚠️ Warning: Could not fetch real-time stats: {e}")
                
            default_base = args.interval if args.interval > 0.0 else 4.0
            interval_hours = calculate_dynamic_interval(last_optimized, default_base)
            
        if elapsed_hours < interval_hours:
            remaining_hours = interval_hours - elapsed_hours
            print(f"⏳ Pacing Guard Active: The last video `{last_optimized['video_id']}` was optimized {elapsed_hours:.1f} hours ago.")
            print(f"   Required interval is {interval_hours:.1f} hours. Please wait {remaining_hours:.1f} more hours.")
            print(f"   (You can bypass this by running with '--interval 0')")
            return
            
    processed_count = 0
    for target in pending_items:
        if max_to_process and processed_count >= max_to_process:
            print(f"\n🛑 Reached batch execution limit of {max_to_process} videos in this run. Stopping cycle gracefully.")
            break
            
        print(f"\n======================================================================")
        print(f"🚀 [Orchestrator] TRIGGERING AI OPTIMIZATION ON VIDEO: `{target['video_id']}`")
        print(f"   Original Title: {target['title']}")
        print(f"======================================================================")
        
        target["status"] = "in_progress"
        save_state(state)
        
        # Invoke low-level youtube_ai_manager via subprocess shell execution
        cmd = ["python3", "youtube_ai_manager.py"]
        if channel and channel != "default":
            cmd.extend(["--channel", channel])
        cmd.extend(["process", target["video_id"], "--yes"])
        if getattr(args, "no_subtitles", False):
            cmd.append("--no-subtitles")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(result.stdout)
            
            # Retrieve latest live statistics right after update
            youtube = get_youtube_client(channel)
            stats_resp = youtube.videos().list(part="statistics", id=target["video_id"]).execute()
            if stats_resp.get("items"):
                stats = stats_resp["items"][0].get("statistics", {})
                latest_stats = {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0))
                }
                target["baseline_stats"] = latest_stats
                target["current_stats"] = latest_stats
                
            target["status"] = "optimized"
            target["optimized_at"] = datetime.now().isoformat()
            save_state(state)
            processed_count += 1
            print(f"✅ Video `{target['video_id']}` successfully optimized and logged!")
            
            # If there are more items to process, and user set multiple runs in one go, sleep a small cooldown
            if processed_count < len(pending_items) and (not max_to_process or processed_count < max_to_process):
                print(f"⏳ Sleeping for 15 seconds cooldown before processing the next item...")
                time.sleep(15)
                
        except subprocess.CalledProcessError as e:
            target["status"] = "pending"
            save_state(state)
            print(f"❌ Subprocess failed to optimize video: {e}")
            print(f"   Error Output:\n{e.stderr}")
            break
            
    print("\n🎉 Orchestrator execution run finished!")
    cmd_status(args)

def main():
    parser = argparse.ArgumentParser(
        description="🎮 Diablo IV Batch Orchestrator: Stateful Periodic Campaigns & Pacing Guard",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Orchestration actions")
    
    # 1. init
    parser_init = subparsers.add_parser("init", help="Initialize a batch queue based on date or starting video ID")
    parser_init.add_argument("--start-id", help="Optional starting YouTube Video ID to begin the batch sequence from")
    parser_init.add_argument("--channel", help="YouTube profile name (e.g. gamelife, virtualworld)")
    parser_init.add_argument("--filter", default="暗黑破壞神", help="Title keyword filter to isolate specific series (default: 暗黑破壞神)")
    parser_init.add_argument("--since", default="2026-04-28", help="ISO publish date filter (e.g. 2026-04-28 for S13) (default: 2026-04-28)")
    
    # 2. status
    subparsers.add_parser("status", help="Show current campaign progression and metrics growth")
    
    # 3. update-stats
    subparsers.add_parser("update-stats", help="Refresh current YouTube stats to track viewer engagement growth")
    
    # 4. run
    parser_run = subparsers.add_parser("run", help="Execute AI optimizations on scheduled pending queue items")
    parser_run.add_argument(
        "--interval", 
        type=float, 
        default=0.0, 
        help="Pacing Guard: Minimum hours required between video updates (default: 0.0 - process instantly)"
    )
    parser_run.add_argument(
        "--limit", 
        type=int, 
        default=1, 
        help="Maximum number of videos to optimize in this single scheduler run (default: 1)"
    )
    parser_run.add_argument(
        "--dynamic-pacing",
        action="store_true",
        help="Dynamic Pacing: Scale pacing interval based on real-time view growth of the last optimized video"
    )
    parser_run.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Disable automatic generation and upload of multilingual subtitles for this run"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    if args.command == "init":
        cmd_init(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "update-stats":
        cmd_update_stats(args)
    elif args.command == "run":
        cmd_run(args)

if __name__ == "__main__":
    main()
