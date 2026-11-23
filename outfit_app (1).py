"""
나만의 옷장 코디 추천기 (날씨 연동)
- 설치: pip install requests pillow
- 실행: python outfit_app.py
- 옷 사진은 wardrobe_images 폴더에, 옷 정보는 wardrobe.json 에 저장됩니다.
"""

import json
import os
import random
import shutil
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import requests
from PIL import Image, ImageOps, ImageTk

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "wardrobe_images")
DATA_FILE = os.path.join(BASE_DIR, "wardrobe.json")

CATEGORIES = ["모자", "상의", "하의", "아우터", "신발", "기타"]
WARMTH_GUIDE = "1 민소매·반팔 / 2 얇은 긴팔 / 3 가디건·맨투맨 / 4 자켓·니트 / 5 패딩·코트"

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


# ------------------------------------------------------------------
# 옷장 데이터 (저장 / 불러오기)
# ------------------------------------------------------------------
def load_wardrobe():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_wardrobe(items):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_item(items, src_path, name, category, warmth, rain_ok):
    """사진을 wardrobe_images 폴더로 복사하고 옷 정보를 추가"""
    os.makedirs(IMG_DIR, exist_ok=True)
    ext = os.path.splitext(src_path)[1].lower()
    new_name = f"{uuid.uuid4().hex}{ext}"
    shutil.copy(src_path, os.path.join(IMG_DIR, new_name))
    item = {
        "id": uuid.uuid4().hex,
        "name": name,
        "category": category,
        "warmth": int(warmth),
        "rain_ok": bool(rain_ok),
        "image": new_name,
    }
    items.append(item)
    save_wardrobe(items)
    return item


def delete_item(items, item_id):
    for it in items:
        if it["id"] == item_id:
            path = os.path.join(IMG_DIR, it["image"])
            if os.path.exists(path):
                os.remove(path)
            items.remove(it)
            break
    save_wardrobe(items)


# ------------------------------------------------------------------
# 날씨
# ------------------------------------------------------------------
def get_location(city_name):
    params = {"name": city_name, "count": 1, "language": "ko"}
    res = requests.get(GEOCODE_URL, params=params, timeout=10)
    res.raise_for_status()
    results = res.json().get("results")
    if not results:
        return None
    p = results[0]
    return p["latitude"], p["longitude"], p["name"]


def get_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,precipitation,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Seoul",
        "forecast_days": 1,
    }
    res = requests.get(WEATHER_URL, params=params, timeout=10)
    res.raise_for_status()
    d = res.json()
    return {
        "temp": d["current"]["temperature_2m"],
        "feels": d["current"]["apparent_temperature"],
        "rain_now": d["current"]["precipitation"],
        "wind": d["current"]["wind_speed_10m"],
        "t_max": d["daily"]["temperature_2m_max"][0],
        "t_min": d["daily"]["temperature_2m_min"][0],
        "rain_prob": d["daily"]["precipitation_probability_max"][0] or 0,
    }


# ------------------------------------------------------------------
# 코디 추천 로직
# ------------------------------------------------------------------
def target_warmth(feels):
    """체감온도 -> 목표 따뜻함 단계(1~5)"""
    if feels >= 27:
        return 1
    if feels >= 22:
        return 2
    if feels >= 17:
        return 3
    if feels >= 10:
        return 4
    return 5


def is_rainy(w):
    return w["rain_prob"] >= 60 or w["rain_now"] > 0


def pick_item(items, category, target, rainy):
    """카테고리에서 목표 따뜻함에 가까운 옷을 (약간의 랜덤을 섞어) 고름"""
    candidates = [i for i in items if i["category"] == category]
    if not candidates:
        return None, False

    # 비 오는 날은 방수/비 맞아도 되는 옷 우선
    if rainy:
        rain_ok = [i for i in candidates if i["rain_ok"]]
        if rain_ok:
            candidates = rain_ok

    close = [i for i in candidates if abs(i["warmth"] - target) <= 1]
    if close:
        weights = [3 if i["warmth"] == target else 1 for i in close]
        return random.choices(close, weights=weights)[0], True

    # 딱 맞는 게 없으면 가장 가까운 옷
    best = min(candidates, key=lambda i: abs(i["warmth"] - target))
    return best, False


def recommend_outfit(items, w, use_hat=True, use_misc=False):
    """결과: ({카테고리: 옷}, [안내 메시지])"""
    target = target_warmth(w["feels"])
    rainy = is_rainy(w)
    outfit, notes = {}, []

    need = ["상의", "하의", "신발"]
    if target >= 3 or rainy:  # 쌀쌀하거나 비 오면 아우터
        need.append("아우터")
    if use_hat:
        need.append("모자")
    if use_misc:
        need.append("기타")

    for cat in need:
        item, matched = pick_item(items, cat, target, rainy)
        if item is None:
            if cat in ("상의", "하의", "신발", "아우터"):
                notes.append(f"'{cat}' 옷이 등록되어 있지 않아요.")
            continue
        outfit[cat] = item
        if not matched:
            notes.append(f"'{cat}'은(는) 오늘 날씨에 딱 맞는 옷이 없어서 가장 비슷한 옷으로 골랐어요.")

    if rainy:
        notes.append("☔ 비 소식이 있어요. 우산을 챙기세요!")
    if w["wind"] >= 25:
        notes.append("💨 바람이 강해요. 바람막이나 목도리가 좋아요.")
    if w["t_max"] - w["t_min"] >= 10:
        notes.append("🌡️ 일교차가 커요. 겉옷을 꼭 챙기세요.")
    return outfit, notes


# ------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------
def load_thumb(filename, size):
    path = os.path.join(IMG_DIR, filename)
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (size, size))
    return ImageTk.PhotoImage(img)


class OutfitApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("나만의 옷장 코디 추천기")
        self.geometry("820x640")

        self.items = load_wardrobe()
        self.weather = None
        self.selected_path = None
        self.preview_img = None
        self.tree_imgs = []
        self.outfit_imgs = []

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_add = ttk.Frame(nb)
        self.tab_closet = ttk.Frame(nb)
        self.tab_rec = ttk.Frame(nb)
        nb.add(self.tab_add, text="① 옷 등록")
        nb.add(self.tab_closet, text="② 내 옷장")
        nb.add(self.tab_rec, text="③ 오늘의 코디")

        self.build_add_tab()
        self.build_closet_tab()
        self.build_rec_tab()
        self.refresh_closet()

    # ---------- 탭 1: 옷 등록 ----------
    def build_add_tab(self):
        f = self.tab_add
        ttk.Button(f, text="📷 사진 선택", command=self.choose_photo).grid(
            row=0, column=0, padx=10, pady=10, sticky="w")
        self.preview = ttk.Label(f, text="(사진 미리보기)")
        self.preview.grid(row=1, column=0, rowspan=6, padx=10, pady=5)

        ttk.Label(f, text="이름").grid(row=1, column=1, sticky="e", padx=5)
        self.name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.name_var, width=28).grid(row=1, column=2, sticky="w")

        ttk.Label(f, text="종류").grid(row=2, column=1, sticky="e", padx=5)
        self.cat_var = tk.StringVar(value=CATEGORIES[1])
        ttk.Combobox(f, textvariable=self.cat_var, values=CATEGORIES,
                     state="readonly", width=10).grid(row=2, column=2, sticky="w", pady=6)

        ttk.Label(f, text="따뜻함(1~5)").grid(row=3, column=1, sticky="e", padx=5)
        self.warm_var = tk.IntVar(value=3)
        ttk.Scale(f, from_=1, to=5, orient="horizontal", length=160,
                  command=lambda v: self.warm_var.set(round(float(v)))).grid(
            row=3, column=2, sticky="w")
        ttk.Label(f, textvariable=self.warm_var).grid(row=3, column=3, sticky="w")
        ttk.Label(f, text=WARMTH_GUIDE, foreground="gray").grid(
            row=4, column=1, columnspan=3, sticky="w", padx=5)

        self.rain_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="비 오는 날 입어도 됨 (방수/비 맞아도 OK)",
                        variable=self.rain_var).grid(row=5, column=1, columnspan=3,
                                                    sticky="w", padx=5, pady=6)

        ttk.Button(f, text="💾 옷장에 저장", command=self.save_item).grid(
            row=6, column=1, columnspan=2, pady=12)

    def choose_photo(self):
        path = filedialog.askopenfilename(
            title="옷 사진 선택",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not path:
            return
        self.selected_path = path
        self.name_var.set(os.path.splitext(os.path.basename(path))[0])
        try:
            img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            img = ImageOps.fit(img, (220, 220))
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview.config(image=self.preview_img, text="")
        except OSError:
            messagebox.showerror("오류", "이미지를 열 수 없어요.")
            self.selected_path = None

    def save_item(self):
        if not self.selected_path:
            messagebox.showwarning("알림", "먼저 사진을 선택해 주세요.")
            return
        name = self.name_var.get().strip() or "이름 없음"
        add_item(self.items, self.selected_path, name, self.cat_var.get(),
                 self.warm_var.get(), self.rain_var.get())
        self.refresh_closet()
        messagebox.showinfo("저장 완료", f"'{name}' 을(를) 옷장에 저장했어요!")
        self.selected_path = None
        self.preview.config(image="", text="(사진 미리보기)")
        self.name_var.set("")

    # ---------- 탭 2: 내 옷장 ----------
    def build_closet_tab(self):
        f = self.tab_closet
        style = ttk.Style()
        style.configure("Closet.Treeview", rowheight=72)
        cols = ("category", "warmth", "rain")
        self.tree = ttk.Treeview(f, columns=cols, style="Closet.Treeview",
                                 selectmode="browse")
        self.tree.heading("#0", text="사진 / 이름")
        self.tree.heading("category", text="종류")
        self.tree.heading("warmth", text="따뜻함")
        self.tree.heading("rain", text="비 OK")
        self.tree.column("#0", width=300)
        self.tree.column("category", width=90, anchor="center")
        self.tree.column("warmth", width=80, anchor="center")
        self.tree.column("rain", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Button(f, text="🗑 선택한 옷 삭제", command=self.delete_selected).pack(pady=(0, 8))

    def refresh_closet(self):
        self.tree.delete(*self.tree.get_children())
        self.tree_imgs = []
        for it in self.items:
            try:
                thumb = load_thumb(it["image"], 64)
            except (OSError, FileNotFoundError):
                thumb = None
            if thumb:
                self.tree_imgs.append(thumb)
            self.tree.insert("", "end", iid=it["id"], text="  " + it["name"],
                             image=thumb if thumb else "",
                             values=(it["category"], it["warmth"],
                                     "O" if it["rain_ok"] else "X"))

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("알림", "삭제할 옷을 선택해 주세요.")
            return
        if messagebox.askyesno("확인", "정말 삭제할까요?"):
            delete_item(self.items, sel[0])
            self.refresh_closet()

    # ---------- 탭 3: 오늘의 코디 ----------
    def build_rec_tab(self):
        f = self.tab_rec
        top = ttk.Frame(f)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="도시").pack(side="left")
        self.city_var = tk.StringVar(value="구미")
        ttk.Entry(top, textvariable=self.city_var, width=12).pack(side="left", padx=5)
        ttk.Button(top, text="날씨 불러오기", command=self.fetch_weather).pack(side="left")

        self.hat_var = tk.BooleanVar(value=True)
        self.misc_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="모자 포함", variable=self.hat_var).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="기타 포함", variable=self.misc_var).pack(side="left")

        self.weather_label = ttk.Label(f, text="먼저 날씨를 불러와 주세요.")
        self.weather_label.pack(anchor="w", padx=10)

        ttk.Button(f, text="👕 오늘의 코디 추천 (다시 누르면 새 조합)",
                   command=self.make_outfit).pack(pady=8)

        self.outfit_frame = ttk.Frame(f)
        self.outfit_frame.pack(fill="both", expand=True, padx=8)
        self.note_label = ttk.Label(f, text="", wraplength=760, justify="left")
        self.note_label.pack(anchor="w", padx=10, pady=8)

    def fetch_weather(self):
        city = self.city_var.get().strip()
        if not city:
            return
        try:
            loc = get_location(city)
            if loc is None:
                messagebox.showwarning("알림", "도시를 찾을 수 없어요.")
                return
            lat, lon, name = loc
            self.weather = get_weather(lat, lon)
        except requests.RequestException:
            messagebox.showerror("오류", "날씨 정보를 가져오지 못했어요.\n인터넷 연결을 확인해 주세요.")
            return
        w = self.weather
        self.weather_label.config(
            text=(f"📍 {name}  |  현재 {w['temp']}°C (체감 {w['feels']}°C)  |  "
                  f"최저/최고 {w['t_min']}/{w['t_max']}°C  |  강수확률 {w['rain_prob']}%"))

    def make_outfit(self):
        if self.weather is None:
            messagebox.showinfo("알림", "먼저 날씨를 불러와 주세요.")
            return
        if not self.items:
            messagebox.showinfo("알림", "옷장에 등록된 옷이 없어요. ①탭에서 옷을 등록해 주세요.")
            return

        outfit, notes = recommend_outfit(
            self.items, self.weather, self.hat_var.get(), self.misc_var.get())

        for child in self.outfit_frame.winfo_children():
            child.destroy()
        self.outfit_imgs = []

        order = ["모자", "아우터", "상의", "하의", "신발", "기타"]
        col = 0
        for cat in order:
            if cat not in outfit:
                continue
            it = outfit[cat]
            box = ttk.Frame(self.outfit_frame)
            box.grid(row=0, column=col, padx=6, pady=4)
            try:
                img = load_thumb(it["image"], 120)
                self.outfit_imgs.append(img)
                ttk.Label(box, image=img).pack()
            except (OSError, FileNotFoundError):
                ttk.Label(box, text="(사진 없음)").pack()
            ttk.Label(box, text=cat, font=("", 10, "bold")).pack()
            ttk.Label(box, text=it["name"], wraplength=110).pack()
            col += 1

        self.note_label.config(text="\n".join(notes))


if __name__ == "__main__":
    OutfitApp().mainloop()