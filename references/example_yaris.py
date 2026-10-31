"""Project file for filmkit: Yaris farewell (20-21 Sep 2025). The worked example of the skill.

build: python filmkit.py C:/Data/yaris-video/project.py [--no-media]
"""
import subprocess

SRC = "C:/Users/<you>/Videos/250920_Yaris_farewell"
OUT = "C:/Data/yaris-video/film"
NEW = SRC + "/icloud_new"      # Live Photos unpacked from the iCloud zips (tyre shop, 4 Sep)
TRANSCRIPTS = "C:/Data/yaris-video/transcripts"
MUSIC_DIR = "C:/Users/<you>/Music"
FILM_NAME = "yaris_farewell"
FILM_TITLE = "Yaris farewell"

# Camera roll per car, measured with roll_lr.py (left/right halves cancel perspective)
ROLL_OLD_YARIS = 4.0   # MAH04457..65
ROLL_NEW_YARIS = 2.0   # MAH04466..76


def roll_for(road):
    return ROLL_OLD_YARIS if int(road[3:8]) <= 4465 else ROLL_NEW_YARIS


# --- edit decision list ------------------------------------------------------
# ("talk", [(clip, from_s, to_s[, "keep"]) ...])   "keep" = no jump cuts inside
# ("road", road_clip, at_s, len_s, music_key)
# ("roads", [(road_clip, at_s, len_s) ...], music_key)   several road pieces, one insert
# ("card", road_clip, at_s, len_s, music_key, title, subtitle)
# ("photo", photo_name, len_s, music_key, title, subtitle)   still photo, slow zoom, caption
#     photo_name is an iPhone photo in SRC, or a still made by make_stills() (absolute path)
# ("clip", iphone_clip, at_s, len_s, music_key, title, subtitle)   iPhone footage under music
# ("end", road_clip, at_s, len_s, music_key, title, subtitle)   like "card", text at the top (end screen)
# ("anim", sdr_movie, len_s, music_key)   ready-made SDR animation (route maps), converted to HLG
HOOK = [("IMG_0083", 10.95, 20.45), ("IMG_0084", 27.90, 32.70), ("IMG_0084", 35.3, 39.4),
        ("IMG_0088", 62.00, 67.00),
        ("IMG_0108", 86.95, 90.66), ("IMG_0108", 427.40, 433.20)]

EDL = [
    ("talk", [(c, a, b, "keep") for c, a, b in HOOK]),
    ("card", "MAH04459", 60.0, 8.0, "p1", "Прощавай, Yaris", "Остання подорож Toyota Yaris 2013"),
    # Part 1: outbound in the old Yaris, 20 Sep
    ("talk", [("IMG_0083", 1.4, 166.9)]),                                   # intro, the car, 2000 km
    ("anim", OUT + "/route_out_sdr.mkv", 10.0, "p1"),                        # route map, see route/make_route.py
    ("road", "MAH04457", 138.0, 5.0, "p1"),                                 # edge of Starogard
    ("talk", [("IMG_0083", 166.9, 191.4)]),                                 # oil, brakes
    ("photo", NEW + "/IMG_0009.HEIC", 4.5, "p1", "Задні гальмівні барабани",
     "павутиння після двох років стоянки, 4 вересня 2025"),
    ("photo", NEW + "/IMG_0012.HEIC", 4.5, "p1", "Передні гальмівні диски", "наліт іржі після простою"),
    ("talk", [("IMG_0083", 231.1, 247.4)]),                                 # stood 2 years, new tyres
    ("photo", OUT + "/still_tyres.png", 6.0, "p1", "Нові шини NEXEN N'Blue HD Plus",
     "175/65R14 82T, 2025 року  ·  зчеплення на мокрому A, економія пального C"),
    ("talk", [("IMG_0083", 247.5, 258.7)]),                                 # "today I'll be tired"
    ("photo", "IMG_0082", 6.0, "p1", "Заправка перед виїздом", "13,28 л × 5,99 zł = 79,55 zł"),
    ("talk", [("IMG_0083", 265.9, 317.7), ("IMG_0083", 319.7, 323.5),
              ("IMG_0083", 337.9, 341.5), ("IMG_0083", 354.8, 371.5)]),       # engine load, fuel, price
    ("road", "MAH04458", 210.0, 5.0, "p1"),
    ("talk", [("IMG_0083", 388.4, 410.4)]),                                 # inspection: "check it on the stand"
    ("clip", "IMG_0017", 3.0, 6.0, "p1", "Перевірка на стенді", "станція техогляду, 4 вересня 2025"),
    ("photo", OUT + "/still_stand.png", 7.0, "p1", "Результати стенду",
     "робоче гальмо 60 %  ·  стоянкове не міряли  ·  підвіска в нормі"),
    # the old transcript puts "не їздила" at 434.6-435.0, but it runs to ~436.3; 434.1-434.4 is a slip
    ("talk", [("IMG_0083", 410.6, 433.72), ("IMG_0083", 434.74, 436.35, "keep"),
              ("IMG_0083", 438.5, 443.5)]),                                 # "good condition", "we drive"
    ("road", "MAH04459", 116.0, 5.0, "p1"),
    ("talk", [("IMG_0084", 2.6, 63.2), ("IMG_0084", 66.0, 87.9)]),          # slow, torque, noise
    ("road", "MAH04460", 21.0, 5.0, "p1"),
    ("talk", [("IMG_0084", 98.0, 134.8), ("IMG_0084", 142.4, 175.9),
              ("IMG_0084", 178.4, 208.8)]),                                 # mats, stop plan, weather
    ("road", "MAH04463", 51.0, 9.0, "p1"),                                  # exit sign, slip road into the Orlen MOP
    ("talk", [("IMG_0085", 0.4, 23.9)]),                                    # stopped: 357 km
    ("photo", "IMG_0086", 5.0, "p1", "Orlen на автостраді, 357 км від дому", "32,24 л × 6,49 zł = 209,24 zł"),
    ("road", "MAH04464", 0.0, 10.0, "p1"),                                  # out of the MOP, back onto the A1
    ("talk", [("IMG_0087", 1.2, 79.2), ("IMG_0087", 80.1, 122.6)]),         # fresh fuel, LTFT
    ("photo", OUT + "/still_torque.png", 8.0, "p1", "Паливна корекція LTFT1, запис Torque",
     "за годину дороги до +25 %   ·   до нуля ще до заправки Orlen"),
    # the old transcript ends the phrase at 25.1, but "...не 144, а 147" runs to 26.3
    ("talk", [("IMG_0088", 1.0, 17.0), ("IMG_0088", 17.3, 26.45, "keep"),
              ("IMG_0088", 27.3, 67.0)]),                                   # speedometer lies
    ("road", "MAH04465", 204.0, 8.0, "p1"),                                 # into the airport car park, terminal ahead
    # the odometer line is read slowly with long pauses (31.8-41.4 s); the old transcript ends it at 37
    ("talk", [("IMG_0089", 0.6, 29.4), ("IMG_0091", 2.7, 31.6), ("IMG_0091", 31.6, 41.7, "keep"),
              ("IMG_0089", 30.6, 40.3, "keep")]),                           # arrival, stats, to Sumy
    ("card", "MAH04466", 400.0, 6.0, "p2", "Дорога назад", "Орендований Yaris Hybrid, 900 км за день"),
    ("clip", "IMG_0096", 0.0, 10.9, "p2", "Беру Yaris в оренду", "аеропорт Катовіце, 20 вересня ввечері"),
    ("photo", "IMG_0097", 5.0, "p2", "Орендований Yaris Hybrid: 102 321 км", "повний бак, 20 вересня, 18:29"),
    ("anim", OUT + "/route_back_sdr.mkv", 12.0, "p2"),
    # Part 2: return in the new Yaris
    ("talk", [("IMG_0108", 2.5, 84.5), ("IMG_0108", 85.6, 125.5)]),         # tired, new Yaris systems
    ("road", "MAH04467", 116.0, 5.0, "p2"),
    ("talk", [("IMG_0108", 150.8, 231.9),                                   # + "refuel again, check the computer"
              ("IMG_0108", 242.7, 275.6)]),                                 # rattle, CarPlay, autopilot
    ("road", "MAH04469", 305.0, 5.0, "p2"),
    ("talk", [("IMG_0109", 1.3, 49.0, "keep")]),                            # engine roar: keep the pauses
    ("roads", [("MAH04471", 235.5, 6.4), ("MAH04472", 9.0, 5.0)], "p2"),    # night stop at Orlen
    ("photo", "IMG_0101", 5.0, "p2", "Нічна заправка Orlen", "28,84 л × 5,94 zł = 171,31 zł"),
    # "...але 450 - це автобаном" runs to 324.3 and the trip home (394.5-425) was left out; the old
    # transcript has both too short, so the 450 line is kept whole
    ("talk", [("IMG_0108", 276.8, 304.6), ("IMG_0108", 306.1, 316.3), ("IMG_0108", 316.3, 324.45, "keep"),
              ("IMG_0108", 326.6, 347.1), ("IMG_0108", 352.0, 363.9),
              ("IMG_0108", 365.3, 425.2)]),                                 # noise, range anxiety, near miss
    ("road", "MAH04473", 305.0, 3.0, "p2"),
    ("photo", "IMG_0110", 5.0, "p2", "Долив перед поверненням машини", "6,15 л × 5,94 zł = 36,53 zł"),
    ("talk", [("IMG_0108", 436.7, 450.3), ("IMG_0112", 1.0, 16.9), ("IMG_0114", 1.9, 8.8),
              ("IMG_0115", 0.2, 8.8), ("IMG_0116", 2.8, 12.1)]),            # tank, mats, dents
    ("photo", OUT + "/still_stats.png", 10.0, "p2", "", ""),
    ("talk", [("IMG_0108", 503.2, 545.9), ("IMG_0108", 549.7, 558.5),
              ("IMG_0108", 565.6, 596.6)]),                                 # verdict, subscribe
    # 20 s for the YouTube end screen: text at the top, the middle left free for video tiles
    ("end", "MAH04476", 60.0, 20.0, "p2", "Дякую за перегляд!",
     "Яріс поїхав до Сум\nКупуєте Теслу? Реферальне посилання: ts.la/volodymyr15420"),
]

MUSIC = {"p1": ("Highway Nocturne - National Sweetheart.mp3", 20.0),
         "p2": ("Big Sky Elegy - National Sweetheart.mp3", 10.0)}


CLIP_FRAME = {"IMG_0017": "crop=1080:608:0:0,scale=1920:1080:flags=lanczos"}   # car on the rollers, top
# portrait talk clips shown full-frame: where the 16:9 band sits, 0 = top, 1 = bottom (1.8x zoom, a bit soft)
PORTRAIT_BAND = {"IMG_0114": 0.6, "IMG_0116": 0.5}   # mat stain, bumper scratches
CLIP_SPEED = {"IMG_0096": 2.0}   # walk round the rental car: 22 s of footage in 11


def make_stills():
    """Composite stills: four Torque screens (LTFT rise and fall on the old tank) and the fuel tally."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = 3840, 2160
    # the recording ends at 17:39:58, so it starts ~13:46; the Orlen stop is at ~2:47 into it.
    # LTFT1 jumps from -1.6 to +25 within 30 s at ~2860 s and is back near zero by ~7400 s
    torque = "%s/Screen_Recording_20250920_173958_Torque.mp4" % SRC
    canvas = Image.new("RGB", (W, H), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    font_l = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 60)
    labels = [(1500, "на початку дороги"), (2875, "через годину"), (6000, "повільно спадає"),
              (7362, "за 45 хв до заправки")]
    for k, (t, label) in enumerate(labels):
        png = "%s/torque_%d.png" % (OUT, t)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", torque, "-frames:v", "1", png],
                       check=True)
        shot = Image.open(png).convert("RGB").crop((0, 0, 1080, 1450))
        shot = shot.resize((1080 * 1150 // 1450, 1150), Image.LANCZOS)
        gap = (W - 4 * shot.width) // 5
        x = gap + k * (shot.width + gap)
        canvas.paste(shot, (x, 110))
        tw = draw.textlength(label, font=font_l)
        draw.text((x + (shot.width - tw) / 2, 1300), label, font=font_l, fill=(235, 235, 235))
    canvas.save("%s/still_torque.png" % OUT)

    # fuel tally over a darkened, blurred road frame
    png = "%s/stats_bg.png" % OUT
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "74", "-i", "%s/Road/MAH04474_fast.mp4" % SRC,
                    "-frames:v", "1", "-vf", "scale=3840:2160", png], check=True)
    img = Image.open(png).convert("RGB").filter(ImageFilter.GaussianBlur(24)).point(lambda v: int(v * 0.35))
    draw = ImageDraw.Draw(img)
    f_title = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 150)
    f_head = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 92)
    f_body = ImageFont.truetype("C:/Windows/Fonts/segoeuil.ttf", 92)
    f_small = ImageFont.truetype("C:/Windows/Fonts/segoeuil.ttf", 66)
    white, grey, accent = (240, 240, 240), (185, 185, 185), (255, 196, 120)
    rows = [
        (f_title, "Паливо за подорож", white, 240),
        (f_head, "Туди: старий Yaris 2013, 357 км до заправки", accent, 560),
        (f_body, "32,24 л  ·  209,24 zł  ·  ≈ 9,0 л/100 км", white, 690),
        (f_head, "Назад: орендований Yaris Hybrid, 516 км", accent, 880),
        (f_body, "34,99 л  ·  207,84 zł  ·  ≈ 6,8 л/100 км за чеками", white, 1010),
        (f_small, "бортовий комп'ютер показував 5,5 л/100 км", grey, 1135),
        (f_head, "Разом у дорозі: 67,23 л  ·  417,08 zł", white, 1360),
        (f_small, "і ще 79,55 zł - долив до повного бака перед виїздом", grey, 1495),
        (f_small, "оренда Yaris Hybrid на добу з повним страхуванням: 222,40 zł", grey, 1600),
        (f_small, "ціни вересня 2025 року, відтоді пальне подорожчало", accent, 1790),
    ]
    for font, text, color, y in rows:
        tw = draw.textlength(text, font=font)
        draw.text(((3840 - tw) / 2, y), text, font=font, fill=color)
    img.save("%s/still_stats.png" % OUT)

    # new tyres: the Allegro order (tyre picture and EU label), side by side
    canvas = Image.new("RGB", (W, H), (24, 24, 24))
    shots = [Image.open("%s/%s.PNG" % (SRC, n)).convert("RGB").crop((72, 703, 1108, 1690))   # above "1 / 5"
             for n in ("IMG_3459", "IMG_3460")]
    shots = [s.resize((s.width * 1500 // s.height, 1500), Image.LANCZOS) for s in shots]
    gap = (W - sum(s.width for s in shots)) // 3
    x = gap
    for s in shots:
        canvas.paste(s, (x, 150))
        x += s.width + gap
    canvas.save("%s/still_tyres.png" % OUT)

    # inspection stand results: the screen above the caption band, so the caption covers none of it
    from PIL import ImageOps
    import pillow_heif
    pillow_heif.register_heif_opener()
    shot = ImageOps.exif_transpose(Image.open("%s/IMG_0019.HEIC" % NEW)).convert("RGB")
    shot = shot.crop((200, 450, 3900, 2450))
    shot = shot.resize((shot.width * 1640 // shot.height, 1640), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), (24, 24, 24))
    canvas.paste(shot, ((W - shot.width) // 2, 40))
    canvas.save("%s/still_stand.png" % OUT)

