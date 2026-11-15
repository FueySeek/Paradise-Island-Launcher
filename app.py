import os, sys, json, uuid, hashlib, zipfile, platform, shutil, threading, subprocess, re, secrets, urllib.parse, time, shlex, webbrowser, socket
from concurrent.futures import ThreadPoolExecutor
import requests
from flask import Flask, request, jsonify, send_from_directory, redirect, send_file, session as flask_session

APP_NAME = "Paradise Island Launcher"
APP_VERSION = "2.3"
try:
    PORT = int(os.environ.get("PIL_PORT", "10131"))
except ValueError:
    PORT = 10131

# 单文件 exe 使用 --windowed 时没有控制台，sys.stdout/stderr 为 None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = sys.stdout

# 单文件 exe 运行时：静态资源来自解包目录，用户数据（minecraft 目录）放在 exe 旁边
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = BUNDLE_DIR
STATIC_DIR = os.path.join(BUNDLE_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "images")
MC_DIR = os.path.join(BASE_DIR, "minecraft")
VERSIONS_DIR = os.path.join(MC_DIR, "versions")
LIBS_DIR = os.path.join(MC_DIR, "libraries")
ASSETS_DIR = os.path.join(MC_DIR, "assets")
JAVA_DIR = os.path.join(MC_DIR, "runtimes")
BG_DIR = os.path.join(MC_DIR, "backgrounds")
CONFIG_PATH = os.path.join(MC_DIR, "launcher_config.json")
DEFAULT_ICON = os.path.join(IMAGES_DIR, "icon.png")
DEFAULT_AVATAR = os.path.join(IMAGES_DIR, "avatar.png")
ROOT_INDEX = os.path.join(BASE_DIR, "index.html")
STATIC_INDEX = os.path.join(STATIC_DIR, "index.html")

for _d in (MC_DIR, VERSIONS_DIR, LIBS_DIR, ASSETS_DIR, JAVA_DIR, BG_DIR, STATIC_DIR, IMAGES_DIR):
    os.makedirs(_d, exist_ok=True)

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
BMCLAPI_MANIFEST = "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"
RESOURCES_OFFICIAL = "https://resources.download.minecraft.net"
RESOURCES_BMCLAPI = "https://bmclapi2.bangbang93.com/assets"

MICROSOFT_AUTH_URL = "https://login.live.com/oauth20_authorize.srf"
MICROSOFT_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
XBL_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_AUTH_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

OS_NAME = {"Windows": "windows", "Darwin": "osx"}.get(platform.system(), "linux")
ARCH = "x64" if sys.maxsize > 2**32 else "x86"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": f"{APP_NAME}/{APP_VERSION}"})

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")

_progress = {"status": "idle", "message": "", "percent": 0, "stage": ""}
_progress_lock = threading.Lock()
_active_proc = {"proc": None}
_config_cache = None
_manifest_cache = {"data": None, "src": None, "ts": 0}

EXTERNAL_LAUNCHER_PATHS = {
    "windows": [
        {"name": "Minecraft Launcher", "paths": [
            r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe",
            r"C:\Program Files\Minecraft Launcher\MinecraftLauncher.exe",
            os.path.expanduser(r"~\AppData\Roaming\.minecraft\launcher\minecraft-launcher.exe"),
        ]},
        {"name": "HMCL", "paths": ["HMCL.exe", os.path.expanduser(r"~\Desktop\HMCL.exe"), os.path.expanduser(r"~\Downloads\HMCL.exe")]},
        {"name": "PCL2", "paths": ["Plain Craft Launcher 2.exe", os.path.expanduser(r"~\Desktop\Plain Craft Launcher 2.exe"), os.path.expanduser(r"~\Downloads\Plain Craft Launcher 2.exe")]},
        {"name": "BakaXL", "paths": ["BakaXL.exe", os.path.expanduser(r"~\Desktop\BakaXL.exe")]},
    ],
    "osx": [{"name": "Minecraft Launcher", "paths": ["/Applications/Minecraft.app/Contents/MacOS/launcher"]}],
    "linux": [],
}


SUPPORTED_LANGS = ("zh-CN", "zh-TW", "en", "ja", "ko", "ru", "es", "fr", "de", "pt-BR")
_LANG_ALIASES = {"zh": "zh-CN", "en": "en", "zh-cn": "zh-CN", "zh-tw": "zh-TW", "pt": "pt-BR"}


def load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    defaults = {
        "download_source": "bmclapi", "version_isolation": True, "java_path": "",
        "max_memory": 4096, "min_memory": 512, "last_version": "", "last_username": "Steve",
        "accounts": [], "active_account": "", "microsoft_client_id": "",
        "theme": "dark", "language": "zh-CN", "current_background": 0,
        "custom_background": "", "custom_launchers": [], "secret_key": "",
        "jvm_args": "", "auto_open_log": False,
    }
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    lang = defaults.get("language")
    lang = _LANG_ALIASES.get(str(lang).lower(), str(lang))
    defaults["language"] = lang if lang in SUPPORTED_LANGS else "en"
    _config_cache = defaults
    return defaults


def save_config(cfg):
    global _config_cache
    _config_cache = cfg
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_secret_key():
    cfg = load_config()
    if not cfg.get("secret_key"):
        cfg["secret_key"] = secrets.token_hex(32)
        save_config(cfg)
    return cfg["secret_key"]


app.secret_key = get_secret_key()


def set_progress(status, message, percent, stage=""):
    with _progress_lock:
        _progress.update(status=status, message=message, percent=int(percent), stage=stage)


def get_progress():
    with _progress_lock:
        return dict(_progress)


def read_instance_cfg(vid):
    p = os.path.join(VERSIONS_DIR, vid, "instance.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def write_instance_cfg(vid, data):
    p = os.path.join(VERSIONS_DIR, vid, "instance.json")
    cur = read_instance_cfg(vid)
    cur.update(data)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    return cur


def game_dir_for(vid, isolate=None):
    inst = read_instance_cfg(vid)
    if isolate is None:
        isolate = inst.get("version_isolation")
    if isolate is None:
        isolate = load_config().get("version_isolation", True)
    if isolate:
        d = os.path.join(VERSIONS_DIR, vid, "game")
        os.makedirs(d, exist_ok=True)
        for sub in ("mods", "saves", "config", "resourcepacks", "shaderpacks", "logs", "crash-reports"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        return d
    return MC_DIR


def file_digest(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch_to(url, tmp):
    with SESSION.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)


def download(url, path, sha1=None, size=None, source=None, sha256=None):
    expected = sha256 or sha1
    algo = "sha256" if sha256 else "sha1"
    if os.path.exists(path):
        if size is not None and os.path.getsize(path) == size:
            if not expected or file_digest(path, algo) == expected:
                return
        elif expected and file_digest(path, algo) == expected:
            return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    actual_url = url
    if source == "bmclapi":
        actual_url = url.replace("https://piston-meta.mojang.com", "https://bmclapi2.bangbang93.com")
        actual_url = actual_url.replace("https://launchermeta.mojang.com", "https://bmclapi2.bangbang93.com")
        actual_url = actual_url.replace("https://launcher.mojang.com", "https://bmclapi2.bangbang93.com")
        actual_url = actual_url.replace("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven")
        actual_url = actual_url.replace("https://resources.download.minecraft.net", RESOURCES_BMCLAPI)
    candidates = [actual_url]
    if source == "bmclapi" and actual_url != url:
        candidates.append(url)  # 镜像失败时回退官方源
    last_err = None
    for candidate in candidates:
        for attempt in range(3):
            try:
                _fetch_to(candidate, tmp)
                if expected and file_digest(tmp, algo) != expected:
                    raise RuntimeError("文件校验失败: " + os.path.basename(path))
                os.replace(tmp, path)
                return
            except Exception as e:
                last_err = e
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                if "文件校验失败" in str(e):
                    break  # 内容不对，重试同一个地址没有意义
                time.sleep(0.5 * (attempt + 1))
    raise last_err or RuntimeError("下载失败: " + os.path.basename(path))


def rule_ok(rules):
    if not rules:
        return True
    allow = False
    for rule in rules:
        os_rule = rule.get("os", {})
        if os_rule.get("name") and os_rule["name"] != OS_NAME:
            continue
        if os_rule.get("arch") and os_rule["arch"] != ARCH:
            continue
        if rule.get("features"):
            continue
        allow = rule.get("action") == "allow"
    return allow


def natives_entry(lib):
    natives = lib.get("natives")
    if not natives:
        return None
    key = natives.get(OS_NAME)
    if not key:
        return None
    key = key.replace("${arch}", "64" if ARCH == "x64" else "32")
    return lib.get("downloads", {}).get("classifiers", {}).get(key)


def fetch_manifest(source=None):
    cfg = load_config()
    src = source or cfg.get("download_source", "bmclapi")
    now = time.time()
    if _manifest_cache["data"] and _manifest_cache["src"] == src and now - _manifest_cache["ts"] < 600:
        return _manifest_cache["data"]
    url = BMCLAPI_MANIFEST if src == "bmclapi" else MANIFEST_URL
    try:
        r = SESSION.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception:
        r = SESSION.get(MANIFEST_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
    _manifest_cache.update({"data": data, "src": src, "ts": now})
    return data


def fetch_version_json(vid, source=None):
    manifest = fetch_manifest(source)
    for v in manifest["versions"]:
        if v["id"] == vid:
            return SESSION.get(v["url"], timeout=30).json()
    raise RuntimeError("版本不存在: " + vid)


def extract_natives_dir(ndir):
    """把目录里的 natives 压缩包解压到同一个目录（忽略 META-INF）。"""
    if not os.path.isdir(ndir):
        return
    for fn in os.listdir(ndir):
        p = os.path.join(ndir, fn)
        if fn.lower().endswith(".jar") and os.path.isfile(p):
            try:
                with zipfile.ZipFile(p) as z:
                    for member in z.namelist():
                        if member.startswith("META-INF/"):
                            continue
                        z.extract(member, ndir)
            except (zipfile.BadZipFile, OSError):
                pass


def has_native_binaries(ndir):
    try:
        return any(fn.lower().endswith((".dll", ".so", ".dylib")) for fn in os.listdir(ndir))
    except OSError:
        return False


def extract_natives(vid):
    ndir = os.path.join(VERSIONS_DIR, vid, "natives")
    os.makedirs(ndir, exist_ok=True)
    extract_natives_dir(ndir)
    return ndir


def valid_version_id(vid):
    """版本目录名白名单校验，避免路径穿越（如 .. / 绝对路径）。"""
    if not isinstance(vid, str):
        return False
    if vid != vid.strip() or not vid or len(vid) > 100:
        return False
    if vid in (".", ".."):
        return False
    if any(c in vid for c in ("/", "\\", ":", "*", "?", '"', "<", ">", "|", "\0")):
        return False
    return os.path.basename(vid) == vid


def load_version_chain(vid):
    """沿 inheritsFrom 从子版本到父版本加载 JSON（用于 Forge/Fabric 等加载器版本）。"""
    chain, seen, cur = [], set(), vid
    while cur and cur not in seen and valid_version_id(cur):
        seen.add(cur)
        p = os.path.join(VERSIONS_DIR, cur, cur + ".json")
        if not os.path.isfile(p):
            break
        try:
            with open(p, encoding="utf-8") as f:
                vj = json.load(f)
        except Exception:
            break
        vj.setdefault("id", cur)
        chain.append(vj)
        cur = vj.get("inheritsFrom")
    return chain


def _lib_key(lib):
    parts = (lib.get("name") or "").split(":")
    if len(parts) >= 3:
        return ":".join([parts[0], parts[1]] + parts[3:])
    return lib.get("name") or ""


def merge_version_chain(chain):
    """把继承链合并成一份可启动的版本描述，子版本优先。"""
    if not chain:
        return {}
    merged = json.loads(json.dumps(chain[0]))
    for parent in chain[1:]:
        for key in ("assetIndex", "assets", "javaVersion", "downloads", "type",
                    "releaseTime", "time", "minimumLauncherVersion"):
            if not merged.get(key) and parent.get(key):
                merged[key] = parent[key]
        if not merged.get("mainClass"):
            merged["mainClass"] = parent.get("mainClass")

        libs = list(merged.get("libraries") or [])
        known = {_lib_key(lib) for lib in libs}
        for lib in parent.get("libraries") or []:
            key = _lib_key(lib)
            if key not in known:
                libs.append(lib)
                known.add(key)
        merged["libraries"] = libs

        parent_args = parent.get("arguments")
        if parent_args:
            args = merged.get("arguments")
            if not args:
                merged["arguments"] = json.loads(json.dumps(parent_args))
            else:
                for kind in ("game", "jvm"):
                    if parent_args.get(kind):
                        args[kind] = list(args.get(kind) or []) + list(parent_args[kind])
        if not merged.get("minecraftArguments") and parent.get("minecraftArguments"):
            merged["minecraftArguments"] = parent["minecraftArguments"]
    return merged


def prepare_natives(chain):
    """保证 natives 已解压，返回 -Djava.library.path 应指向的目录。"""
    dirs = []
    for vj in chain:
        vid = vj.get("id")
        if not vid:
            continue
        ndir = os.path.join(VERSIONS_DIR, vid, "natives")
        if os.path.isdir(ndir):
            dirs.append(ndir)
    if not dirs:
        ndir = os.path.join(VERSIONS_DIR, chain[0].get("id") or "", "natives")
        os.makedirs(ndir, exist_ok=True)
        return ndir
    for ndir in dirs:
        if not has_native_binaries(ndir):
            extract_natives_dir(ndir)
    for ndir in dirs:
        if has_native_binaries(ndir):
            return ndir
    return dirs[0]


def java_major_for_mc(vid):
    for vj in load_version_chain(vid):
        jv = vj.get("javaVersion") or {}
        if jv.get("majorVersion"):
            return int(jv["majorVersion"])
    vj = None
    try:
        vj = fetch_version_json(vid)
    except Exception:
        pass
    if vj and "javaVersion" in vj:
        return int(vj["javaVersion"]["majorVersion"])
    m = re.match(r"1\.(\d+)", vid)
    if m:
        minor = int(m.group(1))
        if minor <= 16:
            return 8
        if minor <= 17:
            return 16
        if minor <= 19:
            return 17
        return 21
    return 17


_java_info_cache = {}


def java_version_string(exe):
    """调用 java -version 读取真实版本号（结果缓存）。"""
    if not exe:
        return ""
    if exe in _java_info_cache:
        return _java_info_cache[exe]
    ver = ""
    try:
        flags = subprocess.CREATE_NO_WINDOW if OS_NAME == "windows" else 0
        proc = subprocess.run([exe, "-version"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=10, creationflags=flags)
        text = (proc.stderr or "") + (proc.stdout or "")
        m = re.search(r'version "([^"]+)"', text)
        ver = m.group(1) if m else ""
    except Exception:
        ver = ""
    _java_info_cache[exe] = ver
    return ver


def java_major_from_version(ver):
    if not ver:
        return None
    if ver.startswith("1."):
        m = re.match(r"1\.(\d+)", ver)
        return int(m.group(1)) if m else None
    m = re.match(r"(\d+)", ver)
    return int(m.group(1)) if m else None


def scan_installed_javas():
    results = []
    seen = set()

    def add(path, major, source):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        ver = java_version_string(path)
        if major is None:
            major = java_major_from_version(ver)
        results.append({"path": path, "major": major, "version": ver, "source": source})

    if os.path.isdir(JAVA_DIR):
        for d in sorted(os.listdir(JAVA_DIR)):
            sub = os.path.join(JAVA_DIR, d)
            if not os.path.isdir(sub):
                continue
            found = False
            for root, _, files in os.walk(sub):
                for fn in files:
                    if fn == ("java.exe" if OS_NAME == "windows" else "java"):
                        major = None
                        m = re.search(r"jdk-?(\d+)", d)
                        if m:
                            major = int(m.group(1))
                        add(os.path.join(root, fn), major, "launcher")
                        found = True
                        break
                if found:
                    break
    system_java = shutil.which("java")
    if system_java:
        add(system_java, None, "system")
    return results


def find_java_binary(major=None):
    cfg = load_config()
    if cfg.get("java_path") and os.path.isfile(cfg["java_path"]):
        return cfg["java_path"]
    if major and os.path.isdir(JAVA_DIR):
        jdir = os.path.join(JAVA_DIR, f"jdk{major}")
        if os.path.isdir(jdir):
            for root, _, files in os.walk(jdir):
                for fn in files:
                    if fn == ("java.exe" if OS_NAME == "windows" else "java"):
                        return os.path.join(root, fn)
    for item in scan_installed_javas():
        if major is None:
            return item["path"]
        if item["major"] == major:
            return item["path"]
    if OS_NAME == "windows":
        for base in (r"C:\Program Files\Java", r"C:\Program Files\Eclipse Adoptium", r"C:\Program Files\Microsoft", r"C:\Program Files\Zulu"):
            if os.path.isdir(base):
                for d in sorted(os.listdir(base), reverse=True):
                    exe = os.path.join(base, d, "bin", "java.exe")
                    if os.path.isfile(exe):
                        return exe
    elif OS_NAME == "osx":
        if os.path.isfile("/usr/bin/java"):
            return "/usr/bin/java"
    return "java"


def ensure_java(major):
    existing = find_java_binary(major)
    if existing != "java":
        return existing
    api = f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot?architecture={ARCH}&image_type=jdk&os={OS_NAME}&vendor=eclipse"
    try:
        r = SESSION.get(api, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            return "java"
        pkg = data[0]["binary"]["package"]
        link = pkg["link"]
        name = pkg["name"]
        dest = os.path.join(JAVA_DIR, name)
        set_progress("running", "", 5, "java")
        download(link, dest, size=pkg.get("size"), sha256=pkg.get("checksum"))
        extract_dir = os.path.join(JAVA_DIR, f"jdk{major}")
        os.makedirs(extract_dir, exist_ok=True)
        if name.endswith(".zip"):
            with zipfile.ZipFile(dest) as z:
                z.extractall(extract_dir)
        elif name.endswith(".tar.gz"):
            import tarfile
            with tarfile.open(dest) as t:
                t.extractall(extract_dir)
        try:
            os.remove(dest)
        except Exception:
            pass
        return find_java_binary(major)
    except Exception as e:
        print(f"Java {major} 安装失败: {e}")
        return "java"


def do_install_vanilla(vid):
    cfg = load_config()
    src = cfg.get("download_source", "bmclapi")
    set_progress("running", "", 1, "meta")
    vj = fetch_version_json(vid, src)
    vdir = os.path.join(VERSIONS_DIR, vid)
    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, vid + ".json"), "w", encoding="utf-8") as f:
        json.dump(vj, f, indent=2, ensure_ascii=False)

    client = vj.get("downloads", {}).get("client")
    if client:
        set_progress("running", "", 4, "client")
        download(client["url"], os.path.join(vdir, vid + ".jar"), client.get("sha1"), client.get("size"), src)

    libs = [l for l in vj.get("libraries", []) if rule_ok(l.get("rules"))]
    total = max(len(libs), 1)
    for i, lib in enumerate(libs):
        art = lib.get("downloads", {}).get("artifact")
        if art:
            download(art["url"], os.path.join(LIBS_DIR, art["path"]), art.get("sha1"), art.get("size"), src)
        nat = natives_entry(lib)
        if nat:
            download(nat["url"], os.path.join(VERSIONS_DIR, vid, "natives", os.path.basename(nat["path"])), nat.get("sha1"), nat.get("size"), src)
        set_progress("running", f"{i+1}/{total}", 4 + int(56 * (i+1) / total), "libraries")

    set_progress("running", "", 62, "assets")
    asset_failures = {}
    idx = vj.get("assetIndex")
    if idx:
        idx_path = os.path.join(ASSETS_DIR, "indexes", idx["id"] + ".json")
        download(idx["url"], idx_path, idx.get("sha1"), idx.get("size"),
                 "bmclapi" if src == "bmclapi" else None)
        with open(idx_path, encoding="utf-8") as f:
            objects = json.load(f).get("objects", {})
        items = list(objects.items())
        counter = {"n": 0}
        lock = threading.Lock()

        def task(item):
            _, obj = item
            h = obj["hash"]
            target = os.path.join(ASSETS_DIR, "objects", h[:2], h)
            # url 用官方地址，source=bmclapi 时下载函数会先走镜像、失败再回退官方
            try:
                download(RESOURCES_OFFICIAL + "/" + h[:2] + "/" + h, target, h, obj.get("size"),
                         src if src == "bmclapi" else None)
            except Exception:
                with lock:
                    asset_failures[h] = obj.get("size")
            with lock:
                counter["n"] += 1
                if counter["n"] % 10 == 0 or counter["n"] == len(items):
                    set_progress("running", f"{counter['n']}/{len(items)}", 62 + int(36 * counter["n"] / max(len(items), 1)), "assets")

        if items:
            with ThreadPoolExecutor(max_workers=16) as ex:
                list(ex.map(task, items))

        # 并发下载失败的资源再串行重试一轮，通常可以恢复镜像抖动导致的失败
        if asset_failures:
            print(f"[assets] 并发下载失败 {len(asset_failures)} 个，开始串行重试...")
            for h, size in list(asset_failures.items()):
                target = os.path.join(ASSETS_DIR, "objects", h[:2], h)
                try:
                    download(RESOURCES_OFFICIAL + "/" + h[:2] + "/" + h, target, h, size,
                             src if src == "bmclapi" else None)
                    asset_failures.pop(h, None)
                except Exception:
                    pass

    extract_natives(vid)
    game_dir_for(vid)
    if asset_failures:
        print(f"[assets] {len(asset_failures)} 个资源下载失败")
        set_progress("done", f"warn:{len(asset_failures)}", 100, "done")
    else:
        set_progress("done", "", 100, "done")


def get_json_first(urls, timeout=30):
    """依次尝试多个地址，返回第一个可用的 JSON。"""
    last_err = None
    for url in urls:
        try:
            r = SESSION.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
    raise RuntimeError(f"请求失败: {last_err}")


def ensure_launcher_profiles():
    """Forge/NeoForge 安装器要求目标目录里存在 launcher_profiles.json。"""
    p = os.path.join(MC_DIR, "launcher_profiles.json")
    if not os.path.isfile(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"profiles": {}, "settings": {}, "version": 3}, f, indent=2)
    return p


def run_installer(jar, args, vid, label):
    java = ensure_java(java_major_for_mc(vid))
    ensure_launcher_profiles()
    cmd = [java, "-jar", jar] + args
    set_progress("running", label, 70, "loader")
    try:
        proc = subprocess.run(cmd, cwd=MC_DIR, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1200)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{label} 安装超时")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"{label} 安装失败: {detail}")
    key = label.lower()
    found = False
    for d in os.listdir(VERSIONS_DIR):
        if d == vid or not valid_version_id(d):
            continue
        if key in d.lower() and os.path.isfile(os.path.join(VERSIONS_DIR, d, d + ".json")):
            found = True
            break
    if not found:
        detail = (proc.stdout or "")[-800:]
        raise RuntimeError(f"{label} 安装未生成版本文件。{detail}")
    set_progress("done", "", 100, "done")


def install_forge(vid, forge_version=None):
    cfg = load_config()
    src = cfg.get("download_source", "bmclapi")
    base = "https://bmclapi2.bangbang93.com/maven" if src == "bmclapi" else "https://maven.minecraftforge.net"
    if not forge_version:
        promo = get_json_first([
            "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
            "https://bmclapi2.bangbang93.com/maven/net/minecraftforge/forge/promotions_slim.json",
        ])
        promos = promo.get("promos", {})
        ver = promos.get(vid + "-latest") or promos.get(vid + "-recommended")
        if not ver:
            raise RuntimeError("找不到该版本的 Forge")
        forge_version = vid + "-" + ver
    installer = f"forge-{forge_version}-installer.jar"
    url = f"{base}/net/minecraftforge/forge/{forge_version}/{installer}"
    dest = os.path.join(MC_DIR, installer)
    download(url, dest)
    try:
        run_installer(dest, ["--installClient", MC_DIR], vid, "Forge")
    finally:
        if os.path.isfile(dest):
            os.remove(dest)


def install_neoforge(vid, neo_version=None):
    cfg = load_config()
    src = cfg.get("download_source", "bmclapi")
    base = "https://bmclapi2.bangbang93.com/maven" if src == "bmclapi" else "https://maven.neoforged.net/releases"
    if not neo_version:
        r = SESSION.get(f"{base}/net/neoforged/neoforge/maven-metadata.xml", timeout=30)
        r.raise_for_status()
        cands = re.findall(r"<version>(.*?)</version>", r.text)
        # NeoForge 1.20.1 使用 47.1.x 版本号，其余版本号前缀与 MC 版本对应
        prefix = "47.1." if vid == "1.20.1" else re.sub(r"^1\.", "", vid) + "."
        cands = [v for v in cands if v.startswith(prefix) and "-" not in v and "+" not in v]
        if not cands:
            raise RuntimeError("找不到该版本的 NeoForge")
        # 元数据里的顺序并不保证是最新在前，按版本号数值排序后取最新
        cands.sort(key=lambda v: [int(x) if x.isdigit() else -1 for x in v.split(".")])
        neo_version = cands[-1]
    installer = f"neoforge-{neo_version}-installer.jar"
    url = f"{base}/net/neoforged/neoforge/{neo_version}/{installer}"
    dest = os.path.join(MC_DIR, installer)
    download(url, dest)
    try:
        run_installer(dest, ["--installClient", MC_DIR], vid, "NeoForge")
    finally:
        if os.path.isfile(dest):
            os.remove(dest)


def pick_loader_version(data):
    """优先选择稳定版加载器（跳过 -beta 等预发布版本）。"""
    for item in data:
        ver = (item.get("loader") or {}).get("version") or ""
        if ver and "-" not in ver:
            return ver
    return data[0]["loader"]["version"]


def install_fabric(vid, loader_version=None, install_api=True):
    cfg = load_config()
    src = cfg.get("download_source", "bmclapi")
    bases = (["https://bmclapi2.bangbang93.com/fabric-meta", "https://meta.fabricmc.net"]
             if src == "bmclapi" else ["https://meta.fabricmc.net"])
    if not loader_version:
        data = get_json_first([f"{b}/v2/versions/loader/{vid}" for b in bases])
        loader_version = pick_loader_version(data)
    inst = get_json_first([f"{b}/v2/versions/installer" for b in bases])[0]
    jar_name = f"fabric-installer-{inst['version']}.jar"
    jar_path = os.path.join(MC_DIR, jar_name)
    download(inst["url"], jar_path)
    try:
        run_installer(jar_path, ["client", "-dir", MC_DIR, "-mcversion", vid, "-loader", loader_version, "-noprofile"], vid, "Fabric")
        if install_api:
            try:
                api_meta = SESSION.get(f"https://api.modrinth.com/v2/project/fabric-api/version?game_versions=[\"{vid}\"]&loaders=[\"fabric\"]", timeout=30).json()
                if api_meta:
                    for f in api_meta[0]["files"]:
                        if f.get("primary"):
                            mods_dir = os.path.join(game_dir_for(vid), "mods")
                            os.makedirs(mods_dir, exist_ok=True)
                            download(f["url"], os.path.join(mods_dir, f["filename"]), f.get("hashes", {}).get("sha1"))
                            break
            except Exception:
                pass
    finally:
        if os.path.isfile(jar_path):
            os.remove(jar_path)


def install_quilt(vid, loader_version=None):
    cfg = load_config()
    src = cfg.get("download_source", "bmclapi")
    bases = (["https://bmclapi2.bangbang93.com/quilt-meta", "https://meta.quiltmc.org"]
             if src == "bmclapi" else ["https://meta.quiltmc.org"])
    if not loader_version:
        data = get_json_first([f"{b}/v3/versions/loader/{vid}" for b in bases])
        loader_version = pick_loader_version(data)
    inst = get_json_first([f"{b}/v3/versions/installer" for b in bases])[0]
    jar_name = f"quilt-installer-{inst['version']}.jar"
    jar_path = os.path.join(MC_DIR, jar_name)
    download(inst["url"], jar_path)
    try:
        run_installer(jar_path, ["install", "client", vid, "--loader", loader_version, "--install-dir", MC_DIR], vid, "Quilt")
    finally:
        if os.path.isfile(jar_path):
            os.remove(jar_path)


def do_install(vid, loader="vanilla"):
    try:
        if not valid_version_id(vid):
            raise RuntimeError("无效的版本名")
        do_install_vanilla(vid)
        if loader == "forge":
            install_forge(vid)
        elif loader == "neoforge":
            install_neoforge(vid)
        elif loader == "fabric":
            install_fabric(vid)
        elif loader == "quilt":
            install_quilt(vid)
        game_dir_for(vid)
        save_config(load_config())
    except Exception as e:
        set_progress("error", "安装失败: " + str(e), 0, "error")


def substitute(text, ctx):
    for k, v in ctx.items():
        text = text.replace("${" + k + "}", str(v))
    return text


def split_user_args(text):
    """拆分用户填写的 JVM 参数，支持引号包裹、保留反斜杠路径。"""
    if not text:
        return []
    parts = re.findall(r'"([^"]*)"|\'([^\']*)\'|(\S+)', text)
    out = []
    for a, b, c in parts:
        token = a or b or c
        if token:
            out.append(token)
    return out


def get_active_account():
    cfg = load_config()
    active = cfg.get("active_account", "")
    if not active:
        return None
    for a in cfg.get("accounts", []):
        if a["uuid"] == active:
            return a
    return None


def build_command(vid, memory=None, java_path=None, offline_username=None):
    if not valid_version_id(vid):
        raise RuntimeError("无效的版本名")
    cfg = load_config()
    inst = read_instance_cfg(vid)
    isolate = inst.get("version_isolation")
    if isolate is None:
        isolate = cfg.get("version_isolation", True)
    gdir = game_dir_for(vid, isolate)
    chain = load_version_chain(vid)
    if not chain:
        raise RuntimeError("版本文件不存在: " + vid)
    vj = merge_version_chain(chain)

    classpath_parts = []
    for lib in vj.get("libraries", []):
        if not rule_ok(lib.get("rules")):
            continue
        art = lib.get("downloads", {}).get("artifact")
        if art:
            classpath_parts.append(os.path.join(LIBS_DIR, art["path"]))
    # 客户端 jar 可能属于父版本（Forge/Fabric 等加载器版本自身没有 jar）
    client_jar = None
    for cvj in chain:
        cid = cvj.get("id") or ""
        if not valid_version_id(cid):
            continue
        candidate = os.path.join(VERSIONS_DIR, cid, cid + ".jar")
        if os.path.isfile(candidate):
            client_jar = candidate
            break
    if not client_jar:
        raise RuntimeError("缺少客户端 jar，请重新安装该版本")
    classpath_parts.append(client_jar)
    classpath = os.pathsep.join(classpath_parts)

    natives_dir = prepare_natives(chain)

    idx_id = vj.get("assetIndex", {}).get("id") or vj.get("assets", "legacy")

    account = get_active_account()
    if account and account.get("type") == "microsoft":
        username = account["name"]
        access_token = account.get("access_token", "0")
        auth_uuid = account["uuid"].replace("-", "")
        user_type = "msa"
    else:
        if account and account.get("type") == "offline" and account.get("name"):
            username = account["name"]
        else:
            username = (offline_username or cfg.get("last_username") or "Steve").strip() or "Steve"
        access_token = "0"
        auth_uuid = str(uuid.UUID(hashlib.md5(username.encode()).hexdigest())).replace("-", "")
        user_type = "legacy"

    ctx = {
        "auth_player_name": username, "version_name": vid, "game_directory": gdir,
        "assets_root": ASSETS_DIR, "game_assets": os.path.join(ASSETS_DIR, "virtual", "legacy"),
        "assets_index_name": idx_id, "auth_uuid": auth_uuid, "auth_access_token": access_token,
        "auth_session": access_token, "user_type": user_type, "user_properties": "{}",
        "version_type": vj.get("type", "release"), "classpath": classpath,
        "natives_directory": natives_dir, "launcher_name": APP_NAME.replace(" ", ""),
        "launcher_version": APP_VERSION, "clientid": "", "auth_xuid": "",
    }

    jvm_args = []
    if "arguments" in vj:
        for a in vj["arguments"].get("jvm", []):
            if isinstance(a, str):
                jvm_args.append(a)
            elif rule_ok(a.get("rules")):
                vals = a["value"] if isinstance(a["value"], list) else [a["value"]]
                jvm_args.extend(vals)
    jvm_args = [substitute(x, ctx) for x in jvm_args]
    jvm_args = [a for a in jvm_args if not a.startswith("-Xm") and not a.startswith("-Djava.library.path")]
    if "-cp" not in jvm_args and "-classpath" not in jvm_args:
        jvm_args = ["-cp", classpath] + jvm_args

    mem = inst.get("max_memory") or memory or cfg.get("max_memory", 4096)
    min_mem = inst.get("min_memory") or cfg.get("min_memory", 512)
    java = inst.get("java_path") or java_path or find_java_binary(java_major_for_mc(vid))
    cmd = [java, f"-Xmx{mem}M", f"-Xms{min_mem}M", "-Djava.library.path=" + natives_dir,
           f"-Dminecraft.launcher.brand={APP_NAME.replace(' ', '')}",
           f"-Dminecraft.launcher.version={APP_VERSION}",
           "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8"]
    cmd.extend(jvm_args)
    extra_jvm = (inst.get("jvm_args") or cfg.get("jvm_args") or "").strip()
    if extra_jvm:
        cmd.extend(split_user_args(extra_jvm))
    cmd.append(vj["mainClass"])

    if "arguments" in vj:
        for a in vj["arguments"].get("game", []):
            if isinstance(a, str):
                cmd.append(substitute(a, ctx))
            elif rule_ok(a.get("rules")):
                vals = a["value"] if isinstance(a["value"], list) else [a["value"]]
                for v in vals:
                    cmd.append(substitute(v, ctx))
    else:
        # 先按空格拆分模板再替换变量，避免含空格的路径被拆成多个参数
        for token in str(vj.get("minecraftArguments") or "").split():
            cmd.append(substitute(token, ctx))

    return cmd, gdir


def list_instances():
    cfg = load_config()
    out = []
    if not os.path.isdir(VERSIONS_DIR):
        return out
    for d in os.listdir(VERSIONS_DIR):
        j = os.path.join(VERSIONS_DIR, d, d + ".json")
        jar = os.path.join(VERSIONS_DIR, d, d + ".jar")
        if not os.path.isfile(j) or not valid_version_id(d):
            continue
        loader = "vanilla"
        vj = {}
        try:
            with open(j, encoding="utf-8") as f:
                vj = json.load(f)
            lid = (vj.get("id") or "").lower()
            if "forge" in lid and "neoforge" not in lid:
                loader = "forge"
            elif "neoforge" in lid:
                loader = "neoforge"
            elif "fabric" in lid:
                loader = "fabric"
            elif "quilt" in lid:
                loader = "quilt"
        except Exception:
            pass
        base = vj.get("inheritsFrom")
        installed = os.path.isfile(jar)
        if not installed and base and valid_version_id(base):
            installed = os.path.isfile(os.path.join(VERSIONS_DIR, base, base + ".jar"))
        inst = read_instance_cfg(d)
        isolate = inst.get("version_isolation")
        if isolate is None:
            isolate = cfg.get("version_isolation", True)
        gdir = game_dir_for(d, isolate)
        mods_dir = os.path.join(gdir, "mods")
        out.append({
            "id": d, "installed": installed, "loader": loader,
            "game_dir": gdir, "isolated": isolate,
            "has_mods": os.path.isdir(mods_dir),
            "mod_count": len([f for f in os.listdir(mods_dir) if f.endswith(".jar")]) if os.path.isdir(mods_dir) else 0,
            "has_custom_icon": os.path.isfile(os.path.join(gdir, "icon.png")),
            "display_name": inst.get("display_name") or d,
            "max_memory": inst.get("max_memory"),
            "java_path": inst.get("java_path"),
            "type": vj.get("type") or "release",
            "last_launched": inst.get("last_launched") or 0,
            "jvm_args": inst.get("jvm_args") or "",
        })
    return sorted(out, key=lambda x: x["id"], reverse=True)


def microsoft_oauth_url(state):
    cfg = load_config()
    client_id = (cfg.get("microsoft_client_id") or "").strip()
    if not client_id:
        return None
    redirect_uri = f"http://127.0.0.1:{PORT}/api/auth/microsoft/callback"
    params = {
        "client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
        "scope": "XboxLive.signin offline_access", "state": state, "prompt": "select_account",
    }
    return MICROSOFT_AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_microsoft_code(code):
    cfg = load_config()
    client_id = cfg.get("microsoft_client_id", "")
    redirect_uri = f"http://127.0.0.1:{PORT}/api/auth/microsoft/callback"
    token_data = SESSION.post(MICROSOFT_TOKEN_URL, data={
        "client_id": client_id, "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri, "scope": "XboxLive.signin offline_access",
    }, timeout=30).json()
    if "access_token" not in token_data:
        raise RuntimeError(str(token_data))
    return token_data


def chain_to_minecraft(ms_access, ms_refresh):
    xbl_resp = SESSION.post(XBL_AUTH_URL, json={
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + ms_access},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT",
    }, timeout=30).json()
    if "Token" not in xbl_resp:
        raise RuntimeError(str(xbl_resp))
    xbl_token = xbl_resp["Token"]
    uhs = xbl_resp["DisplayClaims"]["xui"][0]["uhs"]
    xsts_resp = SESSION.post(XSTS_URL, json={
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT",
    }, timeout=30).json()
    if "Token" not in xsts_resp:
        raise RuntimeError(str(xsts_resp))
    xsts_token = xsts_resp["Token"]
    mc_resp = SESSION.post(MC_AUTH_URL, json={"identityToken": "XBL3.0 x=" + uhs + ";" + xsts_token}, timeout=30).json()
    if "access_token" not in mc_resp:
        raise RuntimeError(str(mc_resp))
    mc_access = mc_resp["access_token"]
    profile = SESSION.get(MC_PROFILE_URL, headers={"Authorization": "Bearer " + mc_access}, timeout=30).json()
    if "id" not in profile:
        raise RuntimeError("该账户没有 Minecraft 所有权")
    return {"uuid": profile["id"], "name": profile["name"], "type": "microsoft", "access_token": mc_access, "refresh_token": ms_refresh}


def detect_external_launchers():
    detected = []
    for launcher in EXTERNAL_LAUNCHER_PATHS.get(OS_NAME, []):
        for p in launcher["paths"]:
            if os.path.isfile(p):
                detected.append({"name": launcher["name"], "path": p})
                break
    return detected


@app.route("/favicon.ico")
def favicon():
    p = os.path.join(IMAGES_DIR, "icon.png")
    if os.path.isfile(p):
        return send_file(p, mimetype="image/png")
    return "", 204


@app.route("/api/debug/files")
def api_debug_files():
    checks = {
        "index.html (root)": ROOT_INDEX,
        "index.html (static)": STATIC_INDEX,
        "images/icon.png": os.path.join(IMAGES_DIR, "icon.png"),
        "images/background.png": os.path.join(IMAGES_DIR, "background.png"),
        "images/mouse.png": os.path.join(IMAGES_DIR, "mouse.png"),
    }
    result = {}
    for name, p in checks.items():
        result[name] = {"path": p, "exists": os.path.isfile(p),
                        "size": os.path.getsize(p) if os.path.isfile(p) else 0}
    return jsonify({"ok": True, "base_dir": BASE_DIR, "files": result})


@app.route("/")
def index():
    for p in (ROOT_INDEX, STATIC_INDEX):
        if os.path.isfile(p):
            return send_file(p)
    return "Paradise Island Launcher - index.html not found. 请把 index.html 放在 app.py 同目录。"


@app.route("/api/info")
def api_info():
    return jsonify({"ok": True, "name": APP_NAME, "version": APP_VERSION, "port": PORT})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        cfg = load_config()
        allowed = ("download_source", "version_isolation", "java_path", "max_memory", "min_memory",
                   "last_version", "last_username", "microsoft_client_id", "theme", "language",
                   "current_background", "active_account", "jvm_args", "auto_open_log")
        for k in allowed:
            if k not in data:
                continue
            if k == "language" and data[k] not in SUPPORTED_LANGS:
                continue
            if k == "theme" and data[k] not in ("dark", "light", "system"):
                continue
            if k in ("max_memory", "min_memory"):
                try:
                    data[k] = int(data[k])
                except (TypeError, ValueError):
                    continue
            cfg[k] = data[k]
        save_config(cfg)
        return jsonify({"ok": True, "config": cfg})
    return jsonify({"ok": True, "config": load_config(), "java": find_java_binary(),
                    "os": OS_NAME, "arch": ARCH, "name": APP_NAME, "version": APP_VERSION,
                    "frozen": FROZEN, "langs": list(SUPPORTED_LANGS), "port": PORT,
                    "data_dir": MC_DIR})


@app.route("/api/backgrounds")
def api_backgrounds():
    cfg = load_config()
    has_custom = bool(cfg.get("custom_background") and os.path.isfile(cfg["custom_background"]))
    items = []
    for i in range(4):
        p = os.path.join(IMAGES_DIR, f"background_{i}.png")
        if i == 0:
            if has_custom:
                items.append({"id": 0, "name": "custom", "url": "/api/background/custom"})
            elif os.path.isfile(p):
                items.append({"id": 0, "name": "default", "url": "/static/images/background_0.png"})
            continue
        if os.path.isfile(p):
            items.append({"id": i, "name": f"bg{i}", "url": f"/static/images/background_{i}.png"})
    if not items:
        items.append({"id": 0, "name": "default", "url": "/static/images/background.png"})
    return jsonify({"ok": True, "backgrounds": items, "current": cfg.get("current_background", 0)})


@app.route("/api/background/custom")
def api_background_custom():
    cfg = load_config()
    if cfg.get("custom_background") and os.path.isfile(cfg["custom_background"]):
        return send_file(cfg["custom_background"])
    return "", 404


@app.route("/api/background/upload", methods=["POST"])
def api_background_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "没有文件"})
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        return jsonify({"ok": False, "error": "格式不支持"})
    cfg = load_config()
    old = cfg.get("custom_background", "")
    if old and os.path.isfile(old) and os.path.dirname(old) == BG_DIR:
        try:
            os.remove(old)
        except Exception:
            pass
    dest = os.path.join(BG_DIR, "custom" + ext)
    f.save(dest)
    cfg["custom_background"] = dest
    cfg["current_background"] = 0
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/background/reset", methods=["POST"])
def api_background_reset():
    cfg = load_config()
    old = cfg.get("custom_background", "")
    if old and os.path.isfile(old) and os.path.dirname(old) == BG_DIR:
        try:
            os.remove(old)
        except Exception:
            pass
    cfg["custom_background"] = ""
    cfg["current_background"] = 0
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/java/list")
def api_java_list():
    return jsonify({"ok": True, "installed": scan_installed_javas(), "system": find_java_binary()})


@app.route("/api/java/install", methods=["POST"])
def api_java_install():
    data = request.get_json(force=True) or {}
    major = int(data.get("major", 17))

    def worker():
        try:
            result = ensure_java(major)
            if result == "java":
                set_progress("error", f"Java {major}", 0, "java")
            else:
                set_progress("done", "", 100, "java")
        except Exception as e:
            set_progress("error", str(e), 0, "java")

    if get_progress()["status"] == "running":
        return jsonify({"ok": False, "error": "已有任务运行中"})
    set_progress("running", "", 0, "java")
    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/external_launchers")
def api_external_launchers():
    cfg = load_config()
    return jsonify({"ok": True, "detected": detect_external_launchers(), "custom": cfg.get("custom_launchers", [])})


@app.route("/api/external_launchers/open", methods=["POST"])
def api_external_launchers_open():
    data = request.get_json(force=True)
    path = data.get("path", "")
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "文件不存在"})
    try:
        flags = subprocess.CREATE_NO_WINDOW if OS_NAME == "windows" else 0
        subprocess.Popen([path], creationflags=flags)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/external_launchers/add", methods=["POST"])
def api_external_launchers_add():
    data = request.get_json(force=True)
    path = (data.get("path") or "").strip()
    name = (data.get("name") or "").strip() or os.path.basename(path)
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "文件不存在"})
    cfg = load_config()
    custom = [c for c in cfg.get("custom_launchers", []) if c.get("path") != path]
    custom.append({"name": name, "path": path})
    cfg["custom_launchers"] = custom
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/external_launchers/remove", methods=["POST"])
def api_external_launchers_remove():
    data = request.get_json(force=True)
    path = data.get("path", "")
    cfg = load_config()
    cfg["custom_launchers"] = [c for c in cfg.get("custom_launchers", []) if c.get("path") != path]
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/auth/accounts")
def api_auth_accounts():
    cfg = load_config()
    accounts = [{"uuid": a["uuid"], "name": a["name"], "type": a["type"]} for a in cfg.get("accounts", [])]
    return jsonify({"ok": True, "accounts": accounts, "active": cfg.get("active_account", "")})


@app.route("/api/auth/set_active", methods=["POST"])
def api_auth_set_active():
    data = request.get_json(force=True)
    uid = data.get("uuid", "")
    cfg = load_config()
    if uid and uid not in [a["uuid"] for a in cfg.get("accounts", [])]:
        return jsonify({"ok": False, "error": "账户不存在"})
    cfg["active_account"] = uid
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/auth/offline/add", methods=["POST"])
def api_auth_offline_add():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name or ""):
        return jsonify({"ok": False, "error": "用户名需为 3-16 位字母、数字或下划线"})
    uid = str(uuid.UUID(hashlib.md5(name.encode()).hexdigest()))
    cfg = load_config()
    accounts = [a for a in cfg.get("accounts", []) if a.get("uuid") != uid]
    accounts.append({"uuid": uid, "name": name, "type": "offline"})
    cfg["accounts"] = accounts
    cfg["active_account"] = uid
    cfg["last_username"] = name
    save_config(cfg)
    return jsonify({"ok": True, "uuid": uid})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    data = request.get_json(force=True) or {}
    uid = data.get("uuid", "")
    cfg = load_config()
    cfg["accounts"] = [a for a in cfg.get("accounts", []) if a["uuid"] != uid]
    if cfg.get("active_account") == uid:
        cfg["active_account"] = cfg["accounts"][0]["uuid"] if cfg["accounts"] else ""
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/auth/microsoft/login")
def api_auth_microsoft_login():
    state = secrets.token_urlsafe(16)
    flask_session["ms_state"] = state
    url = microsoft_oauth_url(state)
    if not url:
        return redirect("/?auth_error=no_client_id")
    return redirect(url)


@app.route("/api/auth/microsoft/callback")
def api_auth_microsoft_callback():
    error = request.args.get("error")
    if error:
        return redirect("/?auth_error=" + urllib.parse.quote(error))
    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        return redirect("/?auth_error=no_code")
    if state != flask_session.get("ms_state"):
        return redirect("/?auth_error=state_mismatch")
    try:
        token_data = exchange_microsoft_code(code)
        account = chain_to_minecraft(token_data["access_token"], token_data.get("refresh_token", ""))
        cfg = load_config()
        cfg["accounts"] = [a for a in cfg.get("accounts", []) if a["uuid"] != account["uuid"]]
        cfg["accounts"].append(account)
        cfg["active_account"] = account["uuid"]
        save_config(cfg)
        return redirect("/?auth_success=1")
    except Exception as e:
        return redirect("/?auth_error=" + urllib.parse.quote(str(e)))


@app.route("/api/versions")
def api_versions():
    try:
        manifest = fetch_manifest()
        inst = {i["id"]: i for i in list_instances()}
        versions = []
        for v in manifest["versions"]:
            item = {"id": v["id"], "type": v["type"], "releaseTime": v.get("releaseTime", "")}
            item.update(inst.get(v["id"], {"installed": False, "loader": "vanilla", "isolated": False}))
            versions.append(item)
        return jsonify({"ok": True, "versions": versions, "latest": manifest.get("latest", {}), "java": find_java_binary()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "versions": []})


@app.route("/api/install", methods=["POST"])
def api_install():
    data = request.get_json(force=True)
    vid = data.get("version")
    loader = data.get("loader", "vanilla")
    if not vid:
        return jsonify({"ok": False, "error": "缺少版本号"})
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    if get_progress()["status"] == "running":
        return jsonify({"ok": False, "error": "已有安装任务"})
    set_progress("running", "", 0, "meta")
    threading.Thread(target=do_install, args=(vid, loader), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/progress")
def api_progress():
    return jsonify(get_progress())


@app.route("/api/instances")
def api_instances():
    return jsonify({"ok": True, "instances": list_instances()})


@app.route("/api/instance/icon/<vid>")
def api_instance_icon(vid):
    if not valid_version_id(vid):
        return "", 404
    gdir = game_dir_for(vid)
    icon = os.path.join(gdir, "icon.png")
    if os.path.isfile(icon):
        return send_file(icon, mimetype="image/png")
    if os.path.isfile(DEFAULT_ICON):
        return send_file(DEFAULT_ICON, mimetype="image/png")
    return "", 404


@app.route("/api/instance/icon/upload", methods=["POST"])
def api_instance_icon_upload():
    vid = request.form.get("version")
    f = request.files.get("file")
    if not vid or not f:
        return jsonify({"ok": False, "error": "参数缺失"})
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    gdir = game_dir_for(vid)
    dest = os.path.join(gdir, "icon.png")
    f.save(dest)
    return jsonify({"ok": True})


@app.route("/api/instance/icon/reset", methods=["POST"])
def api_instance_icon_reset():
    data = request.get_json(force=True)
    vid = data.get("version")
    if not vid:
        return jsonify({"ok": False, "error": "缺少版本号"})
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    p = os.path.join(game_dir_for(vid), "icon.png")
    if os.path.isfile(p):
        try:
            os.remove(p)
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/instance/settings/<vid>", methods=["GET", "POST"])
def api_instance_settings(vid):
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    if request.method == "POST":
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "参数错误"})
        cur = write_instance_cfg(vid, data)
        return jsonify({"ok": True, "settings": cur})
    return jsonify({"ok": True, "settings": read_instance_cfg(vid)})


OPEN_SUBDIRS = ("mods", "saves", "config", "logs", "crash-reports", "resourcepacks", "shaderpacks")


def open_in_explorer(path):
    if OS_NAME == "windows":
        os.startfile(path)
    elif OS_NAME == "osx":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


@app.route("/api/instance/open_folder", methods=["POST"])
def api_instance_open_folder():
    data = request.get_json(force=True) or {}
    vid = data.get("version")
    sub = (data.get("sub") or "").strip()
    if not vid:
        return jsonify({"ok": False, "error": "缺少版本号"})
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    target = game_dir_for(vid)
    if sub in OPEN_SUBDIRS:
        target = os.path.join(target, sub)
        os.makedirs(target, exist_ok=True)
    try:
        open_in_explorer(target)
        return jsonify({"ok": True, "path": target})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/open_path", methods=["POST"])
def api_open_path():
    """打开启动器相关目录（白名单）。"""
    data = request.get_json(force=True) or {}
    kind = data.get("kind") or "minecraft"
    mapping = {
        "minecraft": MC_DIR, "versions": VERSIONS_DIR, "libraries": LIBS_DIR,
        "assets": ASSETS_DIR, "runtimes": JAVA_DIR, "backgrounds": BG_DIR,
        "logfile": os.path.join(MC_DIR, "launcher.log"),
    }
    target = mapping.get(kind)
    if not target:
        return jsonify({"ok": False, "error": "未知目录"})
    if kind != "logfile":
        os.makedirs(target, exist_ok=True)
    try:
        open_in_explorer(target)
        return jsonify({"ok": True, "path": target})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def mods_dir_for(vid):
    d = os.path.join(game_dir_for(vid), "mods")
    os.makedirs(d, exist_ok=True)
    return d


@app.route("/api/instance/mods")
def api_instance_mods():
    vid = request.args.get("version", "")
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    d = mods_dir_for(vid)
    mods = []
    for fn in sorted(os.listdir(d), key=str.lower):
        p = os.path.join(d, fn)
        if not os.path.isfile(p):
            continue
        low = fn.lower()
        if not (low.endswith(".jar") or low.endswith(".jar.disabled")):
            continue
        mods.append({"name": fn, "size": os.path.getsize(p), "enabled": low.endswith(".jar")})
    return jsonify({"ok": True, "mods": mods, "dir": d})


@app.route("/api/instance/mods/toggle", methods=["POST"])
def api_instance_mods_toggle():
    data = request.get_json(force=True) or {}
    vid = data.get("version")
    name = os.path.basename(data.get("name") or "")
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    p = os.path.join(mods_dir_for(vid), name)
    if not name or not os.path.isfile(p):
        return jsonify({"ok": False, "error": "文件不存在"})
    if name.lower().endswith(".jar.disabled"):
        target = p[:-len(".disabled")]
    elif name.lower().endswith(".jar"):
        target = p + ".disabled"
    else:
        return jsonify({"ok": False, "error": "不是 mod 文件"})
    try:
        os.replace(p, target)
        return jsonify({"ok": True, "name": os.path.basename(target)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/instance/mods/delete", methods=["POST"])
def api_instance_mods_delete():
    data = request.get_json(force=True) or {}
    vid = data.get("version")
    name = os.path.basename(data.get("name") or "")
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    p = os.path.join(mods_dir_for(vid), name)
    if not name or not os.path.isfile(p):
        return jsonify({"ok": False, "error": "文件不存在"})
    try:
        os.remove(p)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/instance/mods/import", methods=["POST"])
def api_instance_mods_import():
    vid = request.form.get("version")
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    files = request.files.getlist("files") or request.files.getlist("file")
    d = mods_dir_for(vid)
    saved = 0
    for f in files:
        name = os.path.basename(f.filename or "")
        if not name.lower().endswith(".jar"):
            continue
        f.save(os.path.join(d, name))
        saved += 1
    return jsonify({"ok": True, "saved": saved})


@app.route("/api/instance/delete", methods=["POST"])
def api_instance_delete():
    data = request.get_json(force=True)
    vid = data.get("version")
    if not vid:
        return jsonify({"ok": False, "error": "缺少版本号"})
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    p = os.path.join(VERSIONS_DIR, vid)
    if not os.path.isdir(p):
        return jsonify({"ok": False, "error": "实例不存在"})
    try:
        shutil.rmtree(p)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/launch", methods=["POST"])
def api_launch():
    data = request.get_json(force=True)
    vid = data.get("version")
    username = data.get("username") or ""
    try:
        memory = int(data.get("memory") or load_config().get("max_memory", 4096))
    except (TypeError, ValueError):
        memory = int(load_config().get("max_memory", 4096) or 4096)
    java = data.get("java") or ""
    if not vid:
        return jsonify({"ok": False, "error": "未选择版本"})
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    if not os.path.isfile(os.path.join(VERSIONS_DIR, vid, vid + ".json")):
        return jsonify({"ok": False, "error": "未找到合适的版本"})
    try:
        cmd, gdir = build_command(vid, memory, java, username)
    except Exception as e:
        return jsonify({"ok": False, "error": "构建命令失败: " + str(e)})

    log_path = os.path.join(MC_DIR, "launcher.log")
    try:
        log_file = open(log_path, "w", encoding="utf-8", errors="replace")
        flags = subprocess.CREATE_NO_WINDOW if OS_NAME == "windows" else 0
        # 工作目录必须是游戏目录，否则存档/日志会写到启动器根目录，版本隔离失效
        proc = subprocess.Popen(cmd, cwd=gdir, stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "找不到 Java，请检查 Java 路径或前往 Java 页面安装"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    _active_proc["proc"] = proc
    cfg = load_config()
    cfg["last_version"] = vid
    if username:
        cfg["last_username"] = username
    save_config(cfg)
    try:
        write_instance_cfg(vid, {"last_launched": int(time.time())})
    except Exception:
        pass

    time.sleep(2.5)
    exit_code = proc.poll()
    if exit_code is not None:
        try:
            log_file.close()
        except Exception:
            pass
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                err = f.read()[-2000:]
        except Exception:
            err = ""
        return jsonify({"ok": False, "error": "游戏进程立即退出(code=" + str(exit_code) + ")。\n" + err})

    return jsonify({"ok": True, "pid": proc.pid, "game_dir": gdir, "command": " ".join(cmd), "log": log_path})


@app.route("/api/log")
def api_log():
    log_path = os.path.join(MC_DIR, "launcher.log")
    if not os.path.isfile(log_path):
        return jsonify({"ok": True, "text": "", "path": log_path})
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return jsonify({"ok": True, "text": f.read()[-50000:], "path": log_path})


@app.route("/api/instance/log")
def api_instance_log():
    """读取实例最近一次的游戏日志；没有 latest.log 时回退到启动器日志。"""
    vid = request.args.get("version", "")
    if not valid_version_id(vid):
        return jsonify({"ok": False, "error": "无效的版本名"})
    gdir = game_dir_for(vid)
    candidates = [os.path.join(gdir, "logs", "latest.log")]
    logs_dir = os.path.join(gdir, "logs")
    if os.path.isdir(logs_dir):
        found = [os.path.join(logs_dir, f) for f in os.listdir(logs_dir)
                 if f.lower().endswith(".log") or f.lower().endswith(".txt")]
        found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        candidates.extend(found)
    candidates.append(os.path.join(MC_DIR, "launcher.log"))
    launcher_log = os.path.normcase(os.path.join(MC_DIR, "launcher.log"))
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    return jsonify({"ok": True, "text": f.read()[-80000:], "path": p,
                                    "fallback": os.path.normcase(p) == launcher_log})
            except OSError:
                continue
    return jsonify({"ok": True, "text": "", "path": "", "fallback": False})


@app.route("/api/quit", methods=["POST"])
def api_quit():
    """关闭启动器（单文件 exe 没有控制台，需要有个退出入口）。"""
    def _shutdown():
        time.sleep(0.4)
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return jsonify({"ok": True})


def browser_url():
    return f"http://127.0.0.1:{PORT}/"


def already_running():
    try:
        r = SESSION.get(browser_url() + "api/info", timeout=2)
        return r.status_code == 200 and r.json().get("name") == APP_NAME
    except Exception:
        return False


def port_available(port):
    """用独占方式探测端口（Windows 上能发现被残留句柄占用的端口）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def choose_port():
    """默认端口不可用时自动改用后续端口，避免残留监听导致启动失败。"""
    global PORT
    for candidate in range(PORT, PORT + 30):
        if port_available(candidate):
            if candidate != PORT:
                print(f"端口 {PORT} 被占用，改用 {candidate}")
            PORT = candidate
            return PORT
    return PORT


def close_splash():
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass


def open_when_ready(url, timeout=90):
    """等待服务真正开始监听后再打开浏览器（onefile 首次启动需要解压）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.6):
                close_splash()
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.3)


def main():
    no_browser = "--no-browser" in sys.argv
    if already_running():
        print("启动器已在运行，直接打开页面")
        if not no_browser:
            webbrowser.open(browser_url())
        return
    choose_port()
    print("=" * 60)
    print(f"{APP_NAME} v{APP_VERSION}")
    print(f"BASE_DIR : {BASE_DIR}")
    print(f"BUNDLE   : {BUNDLE_DIR}")
    print(f"STAT_IDX : {'OK' if os.path.isfile(STATIC_INDEX) else 'MISS'}  {STATIC_INDEX}")
    for rel in ("icon.png", "avatar.png", "background_0.png"):
        p = os.path.join(IMAGES_DIR, rel)
        print(f"  [{'OK' if os.path.isfile(p) else 'MISS'}] static/images/{rel}")
    print("=" * 60)
    print(browser_url())
    if no_browser:
        close_splash()
    else:
        threading.Thread(target=open_when_ready, args=(browser_url(),), daemon=True).start()
    try:
        app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
    except OSError as e:
        print("启动失败:", e)
        if not no_browser:
            webbrowser.open(browser_url())


if __name__ == "__main__":
    main()