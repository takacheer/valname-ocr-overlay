import mss
import cv2
import numpy as np
import easyocr
import keyboard
import time
import difflib
import threading
import os
import uuid
import json
from flask import Flask, jsonify, render_template_string, send_from_directory, request

# ==========================================
# 1. Global States & Initial Settings
# ==========================================

CONFIG_FILE = "config.json"

MONITOR_INDEX = 1
OBS_REGION = {"top": 966, "left": 531, "width": 200, "height": 25}
NON_OBS_REGION = {"top": 820, "left": 117, "width": 295, "height": 30}

INTERVAL_CHOICES = [1.0, 0.5, 0.33, 0.25, 0.2, 0.1]
INTERVAL = 0.5
MATCH_CUTOFF = 0.3

# flags
is_capturing = False
is_obs_mode = False
is_debug_mode = False
latest_valid_match = ""
dummy_player_index = 0

players_data = []

TARGET_WORDS = []
ALLOWED_CHARS = " "

def load_config():
    global players_data, MONITOR_INDEX, INTERVAL, is_obs_mode, MATCH_CUTOFF
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                players_data = data.get("players", players_data)
                s = data.get("settings", {})
                MONITOR_INDEX = s.get("monitor_index", MONITOR_INDEX)
                INTERVAL = s.get("interval", INTERVAL)
                is_obs_mode = s.get("is_obs_mode", is_obs_mode)
                MATCH_CUTOFF = s.get("match_cutoff", MATCH_CUTOFF)
            print("[System] Loaded configuration from config.json")
        except Exception as e:
            print(f"[Error] Failed to load config.json: {e}")

def save_config_to_file():
    data = {
        "players": players_data,
        "settings": {
            "monitor_index": MONITOR_INDEX,
            "interval": INTERVAL,
            "is_obs_mode": is_obs_mode,
            "match_cutoff": MATCH_CUTOFF
        }
    }
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Error] Failed to save config.json: {e}")

def update_ocr_targets():
    global TARGET_WORDS, ALLOWED_CHARS
    active_players = [p for p in players_data if p.get("active")][:10]
    TARGET_WORDS = [p["detect_name"] for p in active_players if p.get("detect_name")]
    
    chars = "".join(set("".join(TARGET_WORDS))) + " "
    ALLOWED_CHARS = chars if chars.strip() else " " 

load_config()
update_ocr_targets()

print("[System] Initializing OCR Engine...")
reader = easyocr.Reader(['en', 'ja'], gpu=True)

# ==========================================
# 2. Web Server & HTML Templates
# ==========================================
app = Flask(__name__)

HTML_OBS = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>VALORANT Name OCR - OBS</title>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { background-color: transparent; color: #ECE8E1; font-family: 'IBM Plex Sans JP', sans-serif; margin: 0; padding-bottom: 120px; overflow: hidden; display: flex; justify-content: center; align-items: flex-end; height: 100vh; box-sizing: border-box; }
        #profile-container { display: flex; align-items: center; background-color: rgba(15, 25, 35, 0.9); border: 1px solid rgba(236, 232, 225, 0.2); border-left: 6px solid #b0a37d; padding: 0 24px 0 0; height: 90px; box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.6); width: 400px; position: relative; overflow: hidden; opacity: 0; transform: translateX(-40px); transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        #profile-container.visible { opacity: 1; transform: translateX(0); }
        @keyframes updateAnim { 0% { opacity: 0; transform: translateY(8px); } 100% { opacity: 1; transform: translateY(0); } }
        .animate-update { animation: updateAnim 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards; }
        #dynamic-wrapper { display: flex; align-items: center; width: 100%; height: 100%; position: relative; }
        #rank-icon { position: absolute; right: -70px; top: 50%; transform: translateY(-50%); width: 180px; height: 180px; object-fit: contain; opacity: 0.5; pointer-events: none; z-index: 0; }
        #player-icon { height: 100%; width: 120px; object-fit: cover; border: none; margin-right: 12px; flex-shrink: 0; z-index: 1; -webkit-mask-image: linear-gradient(to right, rgba(0,0,0,1) 40%, rgba(0,0,0,0) 100%); mask-image: linear-gradient(to right, rgba(0,0,0,1) 40%, rgba(0,0,0,0) 100%); }
        .text-container { display: flex; flex-direction: column; justify-content: center; align-items: flex-start; flex-grow: 1; z-index: 1; min-width: 0; padding-right: 80px; overflow: hidden; }
        #player-name { font-size: 2.2rem; font-weight: 600; letter-spacing: 1px; text-shadow: 2px 2px 0px rgba(0, 0, 0, 0.8); margin: 0; line-height: 1.1; white-space: nowrap; transform-origin: left center; display: inline-block; }
        #player-subtext { font-size: 1.1rem; font-weight: 400; color: #b0a37d; letter-spacing: 1.5px; margin-top: 4px; text-transform: uppercase; white-space: nowrap; transform-origin: left center; display: inline-block; }
    </style>
    <script>
        function squeezeTextIfOverflow(element) {
            element.style.transform = 'scaleX(1)';
            void element.offsetWidth;
            const parentWidth = element.parentElement.clientWidth;
            const textWidth = element.scrollWidth;
            if (textWidth > parentWidth && parentWidth > 0) {
                element.style.transform = `scaleX(${parentWidth / textWidth})`;
            }
        }
        setInterval(async () => {
            try {
                const response = await fetch('/data');
                const data = await response.json();
                const container = document.getElementById('profile-container');
                const wrapperEl = document.getElementById('dynamic-wrapper');
                const nameEl = document.getElementById('player-name');
                const iconEl = document.getElementById('player-icon');
                const subtextEl = document.getElementById('player-subtext');
                const rankIconEl = document.getElementById('rank-icon');

                if (data.display_name !== "") {
                    if (nameEl.innerText !== data.display_name) {
                        wrapperEl.classList.remove('animate-update');
                        void wrapperEl.offsetWidth; 
                        nameEl.innerText = data.display_name;
                        iconEl.src = data.icon || "";
                        iconEl.style.display = data.icon ? "block" : "none";
                        rankIconEl.src = data.rank_icon || "";
                        if (data.subtext && data.subtext.trim() !== "") {
                            subtextEl.innerText = data.subtext;
                            subtextEl.style.display = "inline-block";
                        } else {
                            subtextEl.innerText = "";
                            subtextEl.style.display = "none";
                        }
                        requestAnimationFrame(() => {
                            squeezeTextIfOverflow(nameEl);
                            if (subtextEl.style.display !== "none") squeezeTextIfOverflow(subtextEl);
                        });
                        wrapperEl.classList.add('animate-update');
                    }
                    container.classList.add('visible');
                } else {
                    container.classList.remove('visible');
                }
            } catch (err) {}
        }, 200);
    </script>
</head>
<body>
    <div id="profile-container">
        <div id="dynamic-wrapper">
            <img id="rank-icon" src="" alt="rank">
            <img id="player-icon" src="" alt="icon">
            <div class="text-container">
                <div id="player-name"></div>
                <div id="player-subtext"></div>
            </div>
        </div>
    </div>
</body>
</html>
"""

HTML_CONTROL = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>VALORANT OCR Control Panel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'IBM Plex Sans JP', sans-serif; background-color: #111827; color: #f3f4f6; }
        .preview-box {
            background-image: linear-gradient(45deg, #1f2937 25%, transparent 25%), linear-gradient(-45deg, #1f2937 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #1f2937 75%), linear-gradient(-45deg, transparent 75%, #1f2937 75%);
            background-size: 20px 20px;
            background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
        }
        .v-profile { display: flex; align-items: center; background-color: rgba(15, 25, 35, 0.9); border: 1px solid rgba(236, 232, 225, 0.2); border-left: 6px solid #b0a37d; padding: 0 24px 0 0; height: 90px; box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.6); width: 400px; position: relative; overflow: hidden; color: #ECE8E1;}
        .v-rank { position: absolute; right: -70px; top: 50%; transform: translateY(-50%); width: 180px; height: 180px; object-fit: contain; opacity: 0.5; pointer-events: none; z-index: 0; }
        .v-icon { height: 100%; width: 120px; object-fit: cover; margin-right: 12px; flex-shrink: 0; z-index: 1; -webkit-mask-image: linear-gradient(to right, rgba(0,0,0,1) 40%, rgba(0,0,0,0) 100%); }
        .v-text-col { display: flex; flex-direction: column; justify-content: center; align-items: flex-start; z-index: 1; padding-right: 80px; white-space: nowrap; overflow: hidden;}
        .v-name { font-size: 2.2rem; font-weight: 600; text-shadow: 2px 2px 0px rgba(0, 0, 0, 0.8); margin: 0; line-height: 1.1; }
        .v-sub { font-size: 1.1rem; color: #b0a37d; margin-top: 4px; text-transform: uppercase; }
    </style>
</head>
<body>
    <div id="app" class="max-w-6xl mx-auto p-6">
        <h1 class="text-3xl font-bold mb-6 text-red-500">VALORANT OCR Control Panel</h1>
        
        <div class="flex border-b border-gray-700 mb-6">
            <button @click="currentTab = 'players'" :class="{'border-red-500 text-red-500': currentTab === 'players'}" class="px-4 py-2 border-b-2 border-transparent hover:text-red-400">Players</button>
            <button @click="currentTab = 'settings'" :class="{'border-red-500 text-red-500': currentTab === 'settings'}" class="px-4 py-2 border-b-2 border-transparent hover:text-red-400">OCR Settings</button>
        </div>

        <div v-show="currentTab === 'players'" class="flex gap-6">
            <div class="w-1/3 bg-gray-800 rounded-lg p-4 shadow-lg border border-gray-700">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xl font-semibold">Target List</h2>
                    <span class="text-sm text-gray-400">{{ activeCount }} / 10 Active</span>
                </div>
                <div class="space-y-2 max-h-[600px] overflow-y-auto">
                    <div v-for="(p, index) in config.players" :key="p.id" 
                         @click="selectPlayer(index)"
                         class="flex items-center p-3 rounded cursor-pointer transition-colors border"
                         :class="[p.active ? 'border-green-500 bg-gray-700' : 'border-gray-600 bg-gray-800 hover:bg-gray-700', selectedIdx === index ? 'ring-2 ring-red-500' : '']">
                        <input type="checkbox" v-model="p.active" @click.stop @change="saveConfig" :disabled="!p.active && activeCount >= 10" class="mr-3 w-5 h-5 accent-green-500 cursor-pointer">
                        <div class="truncate flex-1">
                            <div class="font-bold truncate" :class="{'text-green-400': p.active}">{{ p.display_name || 'No Name' }}</div>
                            <div class="text-xs text-gray-400 truncate">Detect: {{ p.detect_name }}</div>
                        </div>
                    </div>
                </div>
                <button @click="addNewPlayer" class="mt-4 w-full bg-red-600 hover:bg-red-700 text-white py-2 rounded font-bold transition">＋ Add New Player</button>
            </div>

            <div class="w-2/3 flex flex-col gap-6" v-if="selectedPlayer">
                <div class="bg-gray-800 rounded-lg p-6 shadow-lg border border-gray-700 preview-box flex justify-center py-12">
                    <div class="v-profile">
                        <img class="v-rank" :src="'/rankimg/' + selectedPlayer.rank_icon + '.png'" v-if="selectedPlayer.rank_icon" @error="e => e.target.style.display='none'" @load="e => e.target.style.display='block'">
                        <img class="v-icon" :src="selectedPlayer.icon" v-if="selectedPlayer.icon">
                        <div class="v-text-col">
                            <div class="v-name">{{ selectedPlayer.display_name }}</div>
                            <div class="v-sub" v-if="selectedPlayer.subtext">{{ selectedPlayer.subtext }}</div>
                        </div>
                    </div>
                </div>

                <div class="bg-gray-800 rounded-lg p-6 shadow-lg border border-gray-700">
                    <h2 class="text-xl font-semibold mb-4">Edit Profile</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Riot ID for detection (No tagline)</label>
                            <input type="text" v-model="selectedPlayer.detect_name" class="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Display Name (UI)</label>
                            <input type="text" v-model="selectedPlayer.display_name" class="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Icon URL / Path</label>
                            <input type="text" v-model="selectedPlayer.icon" placeholder="/picons/xxx.png" class="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Rank Icon Name</label>
                            <input type="text" v-model="selectedPlayer.rank_icon" placeholder="asce3" class="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white">
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm text-gray-400 mb-1">Subtext</label>
                            <input type="text" v-model="selectedPlayer.subtext" class="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white">
                        </div>
                    </div>
                    <div class="mt-6 flex justify-end gap-3">
                        <button @click="deletePlayer" class="bg-gray-600 hover:bg-gray-500 px-4 py-2 rounded text-white">Delete</button>
                        <button @click="saveConfig" class="bg-green-600 hover:bg-green-500 px-6 py-2 rounded text-white font-bold">Save Changes</button>
                    </div>
                </div>
            </div>
            <div v-else class="w-2/3 flex items-center justify-center text-gray-500 border border-dashed border-gray-700 rounded-lg">
                Select a player to edit
            </div>
        </div>

        <div v-show="currentTab === 'settings'" class="bg-gray-800 rounded-lg p-6 shadow-lg border border-gray-700 max-w-2xl">
            <div class="space-y-6">
                <div class="flex items-center justify-between border-b border-gray-700 pb-4">
                    <div>
                        <div class="font-bold text-lg">OCR Capturing</div>
                        <div class="text-sm text-gray-400">Enable or disable screen reading</div>
                    </div>
                    <button @click="config.settings.is_capturing = !config.settings.is_capturing; saveConfig()" 
                            :class="config.settings.is_capturing ? 'bg-green-600' : 'bg-red-600'" 
                            class="px-6 py-2 rounded font-bold w-32">
                        {{ config.settings.is_capturing ? 'ON' : 'OFF' }}
                    </button>
                </div>
                
                <div class="flex items-center justify-between border-b border-gray-700 pb-4">
                    <div>
                        <div class="font-bold text-lg">Debug Mode</div>
                        <div class="text-sm text-gray-400">Display dummy UI without OCR (Shift+F11)</div>
                    </div>
                    <button @click="config.settings.is_debug_mode = !config.settings.is_debug_mode; saveConfig()" 
                            :class="config.settings.is_debug_mode ? 'bg-green-600' : 'bg-gray-600'" 
                            class="px-6 py-2 rounded font-bold w-32">
                        {{ config.settings.is_debug_mode ? 'ON' : 'OFF' }}
                    </button>
                </div>

                <div class="grid grid-cols-2 gap-6 pt-2">
                    <div>
                        <label class="block font-bold mb-2">Monitor Index</label>
                        <input type="number" min="1" v-model.number="config.settings.monitor_index" @change="saveConfig" class="w-full bg-gray-900 border border-gray-600 rounded p-2">
                    </div>
                    <div>
                        <label class="block font-bold mb-2">Interval (Seconds)</label>
                        <select v-model.number="config.settings.interval" @change="saveConfig" class="w-full bg-gray-900 border border-gray-600 rounded p-2">
                            <option value="1.0">1.0s</option>
                            <option value="0.5">0.5s</option>
                            <option value="0.33">0.33s</option>
                            <option value="0.25">0.25s</option>
                            <option value="0.2">0.2s</option>
                            <option value="0.1">0.1s</option>
                        </select>
                    </div>
                    <div>
                        <label class="block font-bold mb-2">Capture Region</label>
                        <select v-model="config.settings.is_obs_mode" @change="saveConfig" class="w-full bg-gray-900 border border-gray-600 rounded p-2">
                            <option :value="true">OBS Mode (for custom UI)</option>
                            <option :value="false">Non-OBS Mode (for default UI)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block font-bold mb-2">Match Cutoff (0.0 - 1.0)</label>
                        <div class="flex items-center gap-3">
                            <input type="range" min="0.1" max="0.9" step="0.05" v-model.number="config.settings.match_cutoff" @change="saveConfig" class="w-full">
                            <span class="w-10 text-right">{{ config.settings.match_cutoff }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const { createApp } = Vue
        createApp({
            data() {
                return {
                    currentTab: 'players',
                    config: { players: [], settings: {} },
                    selectedIdx: null
                }
            },
            computed: {
                selectedPlayer() {
                    return this.selectedIdx !== null ? this.config.players[this.selectedIdx] : null;
                },
                activeCount() {
                    return this.config.players.filter(p => p.active).length;
                }
            },
            mounted() {
                this.fetchConfig();
                setInterval(this.fetchConfig, 2000);
            },
            methods: {
                async fetchConfig() {
                    const res = await fetch('/api/config');
                    const data = await res.json();
                    if(this.selectedIdx === null) {
                        this.config = data;
                    } else {
                        this.config.settings = data.settings;
                    }
                },
                async saveConfig() {
                    await fetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.config)
                    });
                    this.fetchConfig();
                },
                selectPlayer(idx) {
                    this.selectedIdx = idx;
                },
                addNewPlayer() {
                    this.config.players.push({
                        id: Date.now().toString(),
                        detect_name: "ZETA blueberry",
                        display_name: "blueberry",
                        icon: "https://static.wikia.nocookie.net/valorant/images/5/56/Miks_icon.png",
                        subtext: "",
                        rank_icon: "",
                        active: false
                    });
                    this.selectedIdx = this.config.players.length - 1;
                    this.saveConfig();
                },
                deletePlayer() {
                    if(confirm("Are you sure?")) {
                        this.config.players.splice(this.selectedIdx, 1);
                        this.selectedIdx = null;
                        this.saveConfig();
                    }
                }
            }
        }).mount('#app')
    </script>
</body>
</html>
"""

# --- Flask Routes ---
@app.route('/')
def index():
    return HTML_OBS

@app.route('/control')
def control_panel():
    return HTML_CONTROL

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        "players": players_data,
        "settings": {
            "is_capturing": is_capturing,
            "monitor_index": MONITOR_INDEX,
            "interval": INTERVAL,
            "is_obs_mode": is_obs_mode,
            "match_cutoff": MATCH_CUTOFF,
            "is_debug_mode": is_debug_mode
        }
    })

@app.route('/api/config', methods=['POST'])
def save_config_api():
    global players_data, is_capturing, MONITOR_INDEX, INTERVAL, is_obs_mode, MATCH_CUTOFF, is_debug_mode
    data = request.json
    
    if "players" in data:
        players_data = data["players"]
        update_ocr_targets()
        
    if "settings" in data:
        s = data["settings"]
        is_capturing = s.get("is_capturing", is_capturing)
        MONITOR_INDEX = s.get("monitor_index", MONITOR_INDEX)
        INTERVAL = s.get("interval", INTERVAL)
        is_obs_mode = s.get("is_obs_mode", is_obs_mode)
        MATCH_CUTOFF = s.get("match_cutoff", MATCH_CUTOFF)
        is_debug_mode = s.get("is_debug_mode", is_debug_mode)

    save_config_to_file()
        
    return jsonify({"status": "ok"})

@app.route('/picons/<filename>')
def serve_picons(filename):
    return send_from_directory('picons', filename)

@app.route('/rankimg/<filename>')
def serve_rankimg(filename):
    return send_from_directory('rankimg', filename)

@app.route('/data')
def data():
    global is_capturing, is_debug_mode, latest_valid_match
    
    if (not is_capturing and not is_debug_mode) or latest_valid_match == "":
        return jsonify({"display_name": "", "icon": "", "subtext": "", "rank_icon": ""})
    
    profile = next((p for p in players_data if p["detect_name"] == latest_valid_match), {})
    
    display_name = profile.get("display_name", latest_valid_match)
    icon_url = profile.get("icon", "")
    subtext = profile.get("subtext", "")
    rank_icon = profile.get("rank_icon", "")
    
    return jsonify({
        "display_name": display_name, 
        "icon": icon_url,
        "subtext": subtext,
        "rank_icon": f"/rankimg/{rank_icon}.png" if rank_icon else ""
    })

def run_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
print("[System] Web Server is running at http://127.0.0.1:5000")
print("[System] Access Control Panel at: http://127.0.0.1:5000/control")

# ==========================================
# 3. Keyboard Callbacks & OCR Loop
# ==========================================
def toggle_capturing():
    global is_capturing, latest_valid_match
    is_capturing = not is_capturing
    state = "STARTED" if is_capturing else "STOPPED"
    print(f"\n[System] CAPTURE {state}")

def toggle_interval():
    global INTERVAL, current_interval_index
    current_interval_index = (current_interval_index + 1) % len(INTERVAL_CHOICES)
    INTERVAL = INTERVAL_CHOICES[current_interval_index]
    save_config_to_file()
    print(f"\n[System] Interval changed to {INTERVAL} seconds")

def toggle_monitor():
    global MONITOR_INDEX
    with mss.mss() as sct:
        num_monitors = len(sct.monitors) - 1
        MONITOR_INDEX += 1
        if MONITOR_INDEX > num_monitors:
            MONITOR_INDEX = 1
    save_config_to_file()
    print(f"\n[System] Now capturing display {MONITOR_INDEX}")

def toggle_mode():
    global is_obs_mode
    is_obs_mode = not is_obs_mode
    mode_name = "OBSERVER MODE" if is_obs_mode else "NON-OBSERVER MODE"
    save_config_to_file()
    print(f"\n[System] Switched capture region to {mode_name}")

def toggle_debug_mode():
    global is_debug_mode, latest_valid_match, dummy_player_index
    is_debug_mode = not is_debug_mode
    if is_debug_mode:
        dummy_player_index = 0
        if TARGET_WORDS:
            latest_valid_match = TARGET_WORDS[dummy_player_index]
            print(f"\n[System] DEBUG MODE ENABLED: [{latest_valid_match}]")
    else:
        latest_valid_match = ""
        print("\n[System] DEBUG MODE DISABLED")

def toggle_dummy_player():
    global dummy_player_index, latest_valid_match, is_debug_mode
    if is_debug_mode and TARGET_WORDS:
        dummy_player_index = (dummy_player_index + 1) % len(TARGET_WORDS)
        latest_valid_match = TARGET_WORDS[dummy_player_index]
        print(f"\n[System] DEBUG: Switched dummy player to [{latest_valid_match}]")

keyboard.add_hotkey('shift+f7', toggle_capturing)
keyboard.add_hotkey('shift+f8', toggle_interval)
keyboard.add_hotkey('shift+f9', toggle_monitor)
keyboard.add_hotkey('shift+f10', toggle_mode)
keyboard.add_hotkey('shift+f11', toggle_debug_mode)
keyboard.add_hotkey('shift+f12', toggle_dummy_player)

print("=== VALORANT NAME OCR ===")
print("- Shift + F7   : START / STOP CAPTURING")
print("- Shift + F8   : SWITCH CAPTURE INTERVAL")
print("- Shift + F9   : SWITCH DISPlAY TO CAPTURE")
print("- Shift + F10  : SWITCH CAPTURE REGION")
print("- Shift + F11  : ENABLE / DISABLE DEBUG MODE (Displays Dummy UI)")
print("- Shift + F12  : SWITCH DUMMY PLAYER (in Debug Mode)")
print("- Ctrl + C     : EXIT PROGRAM")
print("=================================")

try:
    with mss.mss() as sct:
        if MONITOR_INDEX > len(sct.monitors) - 1:
            MONITOR_INDEX = 1

        while True:
            if not TARGET_WORDS:
                time.sleep(1)
                continue

            if is_debug_mode:
                time.sleep(0.1)
                
            elif is_capturing:
                start_time = time.time()
                current_base_region = OBS_REGION if is_obs_mode else NON_OBS_REGION
                monitor = sct.monitors[MONITOR_INDEX]
                capture_region = {
                    "top": monitor["top"] + current_base_region["top"],
                    "left": monitor["left"] + current_base_region["left"],
                    "width": current_base_region["width"],
                    "height": current_base_region["height"]
                }

                screenshot = sct.grab(capture_region)
                img = np.array(screenshot)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
                
                results = reader.readtext(img_rgb, detail=0, allowlist=ALLOWED_CHARS)

                if results:
                    recognized_text = "".join(results).strip()
                    if recognized_text:
                        matches = difflib.get_close_matches(recognized_text, TARGET_WORDS, n=1, cutoff=MATCH_CUTOFF)
                        best_match = matches[0] if matches else "N/A"
                        
                        if best_match != "N/A":
                            latest_valid_match = best_match
                            print(f"[{time.strftime('%H:%M:%S')}] OCR: [ {recognized_text} ] \t-> MATCH: [ {best_match} ]")
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] OCR: [ {recognized_text} ] \t-> MATCH: [ N/A ]")
                    else:
                        latest_valid_match = ""
                else:
                    latest_valid_match = ""
                
                elapsed = time.time() - start_time
                wait_time = max(0, INTERVAL - elapsed)
                time.sleep(wait_time)
            else:
                time.sleep(0.1)

except KeyboardInterrupt:
    print("\n[System] Exiting program...")