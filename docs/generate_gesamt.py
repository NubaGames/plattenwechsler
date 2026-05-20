"""Kombiniertes Word-Dokument: Pi-Doku + Schnittstellen + Anhang (erweiterte Version)."""
import io, math
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Farben ────────────────────────────────────────────────────────────
CR   = "#C8102E"; CD = "#1E2028"; CM = "#2D3142"; CL = "#6C7280"
COK  = "#22C55E"; CWRN = "#F59E0B"; CINF = "#3B82F6"
CBG  = "#F8F9FA"; CW   = "#FFFFFF"


# ════════════════════════════════════════════════════════════════════════
# GRAFIK-WERKZEUGE
# ════════════════════════════════════════════════════════════════════════
def fig_to_stream(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0); plt.close(fig); return buf

def box(ax, x, y, w, h, title, sub="", fc=CM, fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.07",
                                lw=1.2, edgecolor=fc, facecolor=fc))
    ty = y + h/2 + (0.13 if sub else 0)
    ax.text(x+w/2, ty, title, ha="center", va="center",
            color=CW, fontsize=fs, fontweight="bold")
    if sub:
        ax.text(x+w/2, y+h/2-0.19, sub, ha="center", va="center",
                color=CBG, fontsize=6.8, style="italic")

def arr(ax, x1, y1, x2, y2, label="", col=CL, lw=1.4,
        lx=None, ly=None, lfs=7, bidir=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="<|-|>" if bidir else "-|>",
                               color=col, lw=lw, mutation_scale=12))
    if label:
        tx = lx if lx is not None else (x1+x2)/2
        ty = ly if ly is not None else (y1+y2)/2
        ax.text(tx, ty, label, ha="center", va="center", fontsize=lfs,
                color=CD, bbox=dict(boxstyle="round,pad=0.12",
                                    fc=CBG, ec="none", alpha=0.93))


# ════════════════════════════════════════════════════════════════════════
# G1: Systemarchitektur
# ════════════════════════════════════════════════════════════════════════
def make_architektur():
    fig, ax = plt.subplots(figsize=(13, 5.5))
    fig.patch.set_facecolor(CBG)
    ax.set_facecolor(CBG); ax.set_xlim(0,13); ax.set_ylim(0,5.5); ax.axis("off")

    # Pi-Rahmen
    ax.add_patch(FancyBboxPatch((0.15,0.25), 8.8, 4.95,
                                boxstyle="round,pad=0.12", lw=2.2,
                                edgecolor=CR, facecolor="#FFF5F5", zorder=0))
    ax.text(4.55, 5.0, "Raspberry Pi 4", ha="center",
            color=CR, fontsize=11, fontweight="bold")

    BW, BH = 2.0, 0.80
    mods = [
        # x,    y,    title,            sub,               color
        (0.35, 3.80, "Hauptablauf",    "Statemachine",     CR),
        (2.47, 3.80, "ESP-Client",     "UART-Treiber",     CINF),
        (4.59, 3.80, "GPIO-Manager",   "Endschalter/Pins", CM),
        (6.71, 3.80, "HMI / PyQt5",   "Touchscreen",      CWRN),
        (0.35, 2.80, "AuftragsQueue", "FIFO, thread-safe","#64748B"),
        (2.47, 2.80, "FehlerBeh.",    "Fehler & Quit.",    "#DC2626"),
        (4.59, 2.80, "Config",        "YAML R/W",          "#059669"),
        (6.71, 2.80, "Flask Web-App", "Port 5000",         "#0891B2"),
        (0.35, 1.80, "MQTT-Client",   "paho-mqtt",         "#7C3AED"),
        (2.47, 1.80, "Telegram",      "Bot-API",           "#0EA5E9"),
        (4.59, 1.80, "main.py",       "Einstiegspunkt",    "#475569"),
        (6.71, 1.80, "Mock-ESP",      "Test ohne HW",      "#64748B"),
    ]
    for (x,y,t,s,c) in mods:
        box(ax, x, y, BW, BH, t, s, fc=c, fs=8.2)

    # Externe Blöcke
    ext_data = [
        (9.5, 3.90, 3.0, 0.80, "ESP32",        "UART 115200",   CM),
        (9.5, 2.85, 3.0, 0.80, "MQTT-Broker",  "TCP/IP",        "#7C3AED"),
        (9.5, 1.80, 3.0, 0.80, "Telegram",     "HTTPS",         "#0EA5E9"),
        (9.5, 0.70, 3.0, 0.80, "GPIO Hardware","Endschalter/Pins",CD),
    ]
    for (x,y,w,h,t,s,c) in ext_data:
        box(ax, x, y, w, h, t, s, fc=c, fs=9)

    # Pfeile Pi → Extern
    # ESP-Client → ESP32
    arr(ax, 8.85, 4.20, 9.50, 4.30, bidir=True, col=CM, lw=2.0,
        label="UART", lx=9.15, ly=4.55, lfs=7.5)
    # MQTT-Client → Broker
    arr(ax, 8.85, 2.20, 9.50, 3.05, bidir=True, col="#7C3AED", lw=1.5,
        label="TCP", lx=9.15, ly=2.75, lfs=7.5)
    # Telegram → Server
    arr(ax, 8.85, 2.00, 9.50, 2.00, bidir=True, col="#0EA5E9", lw=1.5,
        label="HTTPS", lx=9.15, ly=2.20, lfs=7.5)
    # GPIO-Manager → Hardware
    ax.annotate("", xy=(9.50, 1.10), xytext=(8.85, 3.20),
                arrowprops=dict(arrowstyle="<|-|>", color=CD, lw=1.3,
                               mutation_scale=11))
    ax.text(9.15, 2.05, "GPIO\nIRQ", ha="center", va="center",
            fontsize=6.8, color=CD, style="italic")

    ax.set_title("Systemarchitektur — Raspberry Pi Software",
                 fontsize=12, fontweight="bold", color=CD, pad=8)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# G2: Pi-Statemachine (gerade Pfeile, klare Positionen)
# ════════════════════════════════════════════════════════════════════════
def make_statemachine():
    fig, ax = plt.subplots(figsize=(13, 5.2))
    fig.patch.set_facecolor(CBG)
    ax.set_facecolor(CBG); ax.set_xlim(0,13); ax.set_ylim(0,5.2); ax.axis("off")

    BW, BH, HBW, HBH = 2.7, 0.82, 1.35, 0.41
    S = {
        "INIT":           (1.65, 4.1,  CM),
        "REFERENZFAHRT":  (5.1,  4.1,  CINF),
        "BEREITSCHAFT":   (9.2,  4.1,  COK),
        "PLATTENWECHSEL": (9.2,  2.4,  CR),
        "SERVICE":        (5.1,  2.4,  "#7C3AED"),
        "FEHLER":         (9.2,  0.75, "#DC2626"),
        "NOT_AUS":        (5.1,  0.75, "#991B1B"),
    }
    for name, (cx, cy, col) in S.items():
        box(ax, cx-HBW, cy-HBH, BW, BH, name, fc=col, fs=8.5)

    # Boot-Pfeil
    ax.annotate("", xy=(1.65-HBW, 4.1), xytext=(0.25, 4.1),
                arrowprops=dict(arrowstyle="-|>", color=CD, lw=1.5, mutation_scale=12))
    ax.text(0.2, 4.1, "boot", ha="right", va="center", fontsize=7.5,
            color=CD, style="italic")

    def sa(s1, s2, label, col=CL, offx1=0, offy1=0, offx2=0, offy2=0,
           lx=None, ly=None, lfs=7.0):
        x1,y1,_ = S[s1]; x2,y2,_ = S[s2]
        p1x,p1y = x1+offx1, y1+offy1
        p2x,p2y = x2+offx2, y2+offy2
        _lx = lx if lx is not None else (p1x+p2x)/2
        _ly = ly if ly is not None else (p1y+p2y)/2 + 0.15
        arr(ax, p1x, p1y, p2x, p2y, label=label, col=col,
            lx=_lx, ly=_ly, lfs=lfs)

    # INIT → REFERENZFAHRT
    sa("INIT","REFERENZFAHRT","ESP verbunden",
       offx1=HBW, offx2=-HBW, lx=3.38, ly=4.38)
    # REFERENZFAHRT → BEREITSCHAFT
    sa("REFERENZFAHRT","BEREITSCHAFT","HOME_DONE",
       offx1=HBW, offx2=-HBW, lx=7.15, ly=4.38)
    # BEREITSCHAFT ↔ PLATTENWECHSEL (versetzt)
    sa("BEREITSCHAFT","PLATTENWECHSEL","Auftrag",
       offx1=0.2, offy1=-HBH, offx2=0.2, offy2=HBH, lx=9.8, ly=3.25)
    sa("PLATTENWECHSEL","BEREITSCHAFT","fertig",
       col=COK, offx1=-0.2, offy1=HBH, offx2=-0.2, offy2=-HBH,
       lx=8.6, ly=3.25)
    # BEREITSCHAFT ↔ SERVICE (versetzt)
    sa("BEREITSCHAFT","SERVICE","aktivieren",
       offx1=0, offy1=-HBH, offx2=HBW, offy2=0, lx=7.8, ly=3.1)
    sa("SERVICE","BEREITSCHAFT","verlassen",
       col=COK, offx1=HBW, offy1=0, offx2=0, offy2=-HBH, lx=7.8, ly=2.7)
    # → FEHLER (von PLATTENWECHSEL)
    sa("PLATTENWECHSEL","FEHLER","Fehler",
       col=CR, offy1=-HBH, offy2=HBH, lx=9.8, ly=1.57)
    # → FEHLER (von REFERENZFAHRT, diagonal)
    arr(ax, 5.1+HBW, 4.1, 9.2-HBW, 0.75,
        label="Timeout/\nFehler", col=CR, lx=7.7, ly=2.75, lfs=6.5)
    # FEHLER → REFERENZFAHRT (großer Bogen links)
    ax.annotate("", xy=(5.1-HBW, 4.1), xytext=(9.2-HBW, 0.75),
                arrowprops=dict(arrowstyle="-|>", color=COK, lw=1.4,
                               mutation_scale=12,
                               connectionstyle="arc3,rad=0.38"))
    ax.text(4.3, 2.5, "Quittiert\n+ Reset", ha="center", va="center",
            fontsize=6.5, color=COK,
            bbox=dict(boxstyle="round,pad=0.12", fc=CBG, ec="none", alpha=0.93))
    # FEHLER ↔ NOT_AUS
    sa("FEHLER","NOT_AUS","Not-Aus",
       col=CR, offx1=-HBW, offx2=HBW, offy1=0.1, offy2=0.1,
       lx=7.15, ly=1.08)
    sa("NOT_AUS","FEHLER","Quittiert",
       col=COK, offx1=HBW, offx2=-HBW, offy1=-0.1, offy2=-0.1,
       lx=7.15, ly=0.42)

    ax.set_title("Systemzustände — Raspberry Pi",
                 fontsize=12, fontweight="bold", color=CD, pad=8)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# G3: Kommunikationssequenz (Anhang)
# ════════════════════════════════════════════════════════════════════════
def make_protokoll():
    fig, ax = plt.subplots(figsize=(13, 8.5))
    fig.patch.set_facecolor(CBG)
    ax.set_facecolor(CBG); ax.set_xlim(0,13); ax.set_ylim(0,8.5); ax.axis("off")

    LPI, LESP = 2.8, 10.5

    for x, lbl, col in [(LPI,"Raspberry Pi",CR),(LESP,"ESP32",CM)]:
        ax.plot([x,x],[0.3,7.8], color=col, lw=1.5, ls="--", alpha=0.3)
        ax.add_patch(FancyBboxPatch((x-1.2,7.8), 2.4, 0.55,
                                    boxstyle="round,pad=0.08",
                                    facecolor=col, edgecolor="none"))
        ax.text(x, 8.07, lbl, ha="center", va="center",
                color=CW, fontsize=9.5, fontweight="bold")

    def phase_hdr(y, title, col):
        ax.add_patch(FancyBboxPatch((0.25,y-0.17),12.5,0.29,
                                    boxstyle="round,pad=0.03",
                                    facecolor=col, edgecolor="none", alpha=0.9))
        ax.text((LPI+LESP)/2, y-0.03, title, ha="center", va="center",
                color=CW, fontsize=8.5, fontweight="bold")

    def msg(y, direction, label, col=CINF, note=""):
        x1,x2 = (LPI,LESP) if direction=="→" else (LESP,LPI)
        ax.annotate("", xy=(x2,y), xytext=(x1,y),
                    arrowprops=dict(arrowstyle="-|>", color=col,
                                   lw=1.5, mutation_scale=12))
        bg = "#EFF6FF" if direction=="→" else "#F0FDF4"
        ax.text((LPI+LESP)/2, y+0.11, label, ha="center", va="bottom",
                fontsize=7.0, color=CD, family="monospace",
                bbox=dict(boxstyle="round,pad=0.1", fc=bg, ec="none"))
        if note:
            ax.text(LESP+0.3, y+0.03, note, ha="left", va="center",
                    fontsize=6.4, color=CL, style="italic")

    y = 7.55
    phase_hdr(y, "Referenzfahrt", CM); y -= 0.34
    msg(y,"→","CMD;1;HOME",                          CINF,"Ref.fahrt starten"); y-=0.38
    msg(y,"←","RSP;1;ACK",                           COK);                      y-=0.38
    msg(y,"←","EVT;0;STATE;BUSY_HOMING",             CWRN,"Zustand");           y-=0.38
    msg(y,"→","CMD;2;HOME_SWITCH_HIT;axis=X",        CINF,"X-Endschalter");     y-=0.38
    msg(y,"→","CMD;3;HOME_SWITCH_HIT;axis=Z",        CINF,"Z-Endschalter");     y-=0.38
    msg(y,"←","EVT;1;OK;HOME_DONE",                  COK,"alle 4 Achsen");      y-=0.38
    msg(y,"←","EVT;0;STATE;READY",                   COK);                      y-=0.52

    phase_hdr(y,"Tür öffnen (OPEN_DOOR)",CWRN); y-=0.34
    msg(y,"→","CMD;4;OPEN_DOOR;x_approach=370;z_approach=105;arm_extend=30;radius=150;angle=160;hook_drop=0",
        CWRN); y-=0.38
    msg(y,"←","RSP;4;ACK",                           COK);                      y-=0.38
    msg(y,"←","EVT;0;STATE;BUSY_OPEN_DOOR",          CWRN,"Kreisbogen");        y-=0.38
    msg(y,"←","EVT;4;OK;DOOR_OPEN_DONE",             COK,"Tür offen");          y-=0.52

    phase_hdr(y,"Plattenentnahme + Fehlerfall",CR); y-=0.34
    msg(y,"→","CMD;5;PICKUP;gripper_depth=120;lift_offset=8",
        CINF); y-=0.38
    msg(y,"←","EVT;5;OK;PICKUP_DONE",               COK,"Platte aufg.");        y-=0.38
    msg(y,"→","CMD;6;MOVE_TO;x=500;z=80",           CINF);                      y-=0.38
    msg(y,"←","EVT;0;ERR;OBSTACLE",                 CR,  "Motor gestoppt");     y-=0.38
    msg(y,"→","CMD;7;RESET_ERROR",                  CINF);                      y-=0.38
    msg(y,"←","EVT;7;OK;ERROR_RESET",               COK, "→ NOT_REFERENCED");   y-=0.45
    msg(y,"←","EVT;0;HEARTBEAT;uptime_ms=12000",    CL,  "alle 1000 ms")

    ax.set_title("Kommunikationsprotokoll Pi ↔ ESP32 — typische Sequenzen",
                 fontsize=12, fontweight="bold", color=CD, pad=8)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# G4: ESP-Statemachine (Anhang, kompakt)
# ════════════════════════════════════════════════════════════════════════
def make_esp_states():
    fig, ax = plt.subplots(figsize=(13, 6.5))
    fig.patch.set_facecolor(CBG)
    ax.set_facecolor(CBG); ax.set_xlim(0,13); ax.set_ylim(0,6.5); ax.axis("off")

    BW, BH = 2.4, 0.68
    S = {
        "NOT_REFERENCED": (1.5,  5.85, CL),
        "READY":          (1.5,  4.60, COK),
        "BUSY_HOMING":    (6.5,  5.85, CINF),
        "BUSY_MOVING":    (6.5,  4.90, CINF),
        "BUSY_MOVE_HOME": (6.5,  3.95, CINF),
        "BUSY_SCANNING":  (6.5,  3.00, CINF),
        "BUSY_PICKUP":    (6.5,  2.05, "#7C3AED"),
        "BUSY_DEPOSIT":   (6.5,  1.10, "#7C3AED"),
        "BUSY_OPEN_DOOR": (11.2, 4.90, CWRN),
        "BUSY_CLOSE_DOOR":(11.2, 3.95, CWRN),
        "STOPPED":        (11.2, 2.60, CM),
        "ERROR":          (11.2, 5.85, "#DC2626"),
    }
    for name,(cx,cy,col) in S.items():
        box(ax, cx-BW/2, cy-BH/2, BW, BH, name, fc=col, fs=7.8)

    # Boot
    ax.annotate("", xy=(1.5-BW/2, 5.85), xytext=(0.2,5.85),
                arrowprops=dict(arrowstyle="-|>", color=CD, lw=1.5, mutation_scale=11))
    ax.text(0.15, 5.85, "boot", ha="right", va="center", fontsize=7, color=CD, style="italic")

    def sa(s1,s2,lbl,col=CL,dx1=0,dy1=0,dx2=0,dy2=0,lx=None,ly=None):
        x1,y1,_ = S[s1]; x2,y2,_ = S[s2]
        p1x,p1y = x1+dx1, y1+dy1; p2x,p2y = x2+dx2, y2+dy2
        arr(ax,p1x,p1y,p2x,p2y, label=lbl, col=col,
            lx=lx or (p1x+p2x)/2, ly=ly or (p1y+p2y)/2+0.13, lfs=6.3)

    # NOT_REFERENCED → BUSY_HOMING
    sa("NOT_REFERENCED","BUSY_HOMING","HOME", dx1=BW/2,dx2=-BW/2, ly=6.1)
    # BUSY_HOMING → READY
    sa("BUSY_HOMING","READY","HOME_DONE", col=COK, dx1=-BW/2,dx2=BW/2,
       dy1=-0.15,dy2=0.15, ly=5.25)
    # READY → BUSY_ (rechte Seite)
    targets_r = [
        ("BUSY_HOMING", "HOME",       0.20),
        ("BUSY_MOVING", "MOVE_TO",    0.10),
        ("BUSY_MOVE_HOME","MOVE_HOME",0.0),
        ("BUSY_SCANNING","SCAN",     -0.10),
        ("BUSY_PICKUP","PICKUP",     -0.20),
        ("BUSY_DEPOSIT","DEPOSIT",   -0.30),
    ]
    for (tgt, cmd, dy) in targets_r:
        tx,ty,_ = S[tgt]; rx,ry,_ = S["READY"]
        arr(ax, rx+BW/2, ry+dy, tx-BW/2, ty+dy,
            label=cmd, col=CL, lx=(rx+BW/2+tx-BW/2)/2, ly=ry+dy+0.12, lfs=6)
    # BUSY_ → READY (OK events, rückwärts)
    ok_r = [
        ("BUSY_MOVING",    "MOVE_DONE",     0.08),
        ("BUSY_MOVE_HOME","MOVE_HOME_DONE", 0.0),
        ("BUSY_PICKUP",   "PICKUP_DONE",   -0.08),
        ("BUSY_DEPOSIT",  "DEPOSIT_DONE",  -0.16),
    ]
    for (src, evt, dy) in ok_r:
        sx,sy,_ = S[src]; rx,ry,_ = S["READY"]
        arr(ax, sx-BW/2, sy+dy-0.12, rx+BW/2, ry+dy-0.12,
            label=evt, col=COK, lx=(sx-BW/2+rx+BW/2)/2, ly=sy+dy-0.25, lfs=6)

    # READY → OPEN/CLOSE_DOOR
    sa("READY","BUSY_OPEN_DOOR","OPEN_DOOR",
       dx1=BW/2, dx2=-BW/2, dy1=0.12, dy2=0.12, lx=7.0, ly=4.95)
    sa("READY","BUSY_CLOSE_DOOR","CLOSE_DOOR",
       dx1=BW/2, dx2=-BW/2, dy1=-0.12, dy2=-0.12, lx=7.0, ly=3.75)
    sa("BUSY_OPEN_DOOR","READY","DOOR_OPEN_DONE",
       col=COK, dx1=-BW/2, dx2=BW/2, dy1=0.10, dy2=0.10, lx=7.0, ly=4.56)
    sa("BUSY_CLOSE_DOOR","READY","DOOR_CLOSE_DONE",
       col=COK, dx1=-BW/2, dx2=BW/2, dy1=-0.14, dy2=-0.14, lx=7.0, ly=3.38)

    # STOP → STOPPED
    arr(ax, 8.7,3.3, 11.2-BW/2,2.6,
        label="STOP", col=CWRN, lx=10.1, ly=3.15, lfs=6.5)
    # STOPPED → READY
    arr(ax, 11.2-BW/2, 2.27, 1.5+BW/2, 4.27,
        label="HOME / MOVE_TO / …", col=COK, lx=6.0, ly=3.1, lfs=6.3)
    # BUSY → ERROR
    arr(ax, 8.7, 5.5, 11.2-BW/2, 5.85,
        label="Fehler/Timeout", col="#DC2626", lx=10.0, ly=5.96, lfs=6.3)
    # ERROR → NOT_REFERENCED
    sa("ERROR","NOT_REFERENCED","RESET_ERROR",
       col=COK, dx1=-BW/2, dx2=BW/2, lx=4.0, ly=6.1)

    ax.set_title("ESP32 — Zustandsmaschine (vereinfacht)",
                 fontsize=12, fontweight="bold", color=CD, pad=8)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# WORD-HILFSFUNKTIONEN
# ════════════════════════════════════════════════════════════════════════
def _shd(cell, fill):
    s = OxmlElement("w:shd")
    s.set(qn("w:fill"), fill); s.set(qn("w:val"), "clear")
    cell._tc.get_or_add_tcPr().append(s)

def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    cols = {1: RGBColor(0xC8,0x10,0x2E), 2: RGBColor(0x1E,0x20,0x28),
            3: RGBColor(0x2D,0x31,0x42)}
    for r in h.runs: r.font.color.rgb = cols.get(level, RGBColor(0x1E,0x20,0x28))
    h.paragraph_format.space_before = Pt({1:18,2:12,3:8}.get(level,6))
    h.paragraph_format.space_after  = Pt(5)
    return h

def add_para(doc, text, bold=False, italic=False, size=10.5, indent=0):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold; r.italic = italic
    r.font.size = Pt(size); r.font.color.rgb = RGBColor(0x1E,0x20,0x28)
    p.paragraph_format.space_after  = Pt(5)
    p.paragraph_format.space_before = Pt(2)
    if indent: p.paragraph_format.left_indent = Cm(indent)
    return p

def add_bullet(doc, items, indent=0.4):
    for text in items:
        p = doc.add_paragraph(style="List Bullet")
        r = p.add_run(text)
        r.font.size = Pt(10); r.font.color.rgb = RGBColor(0x1E,0x20,0x28)
        p.paragraph_format.space_after   = Pt(2)
        p.paragraph_format.left_indent   = Cm(indent)

def add_numbered(doc, items):
    for text in items:
        p = doc.add_paragraph(style="List Number")
        r = p.add_run(text)
        r.font.size = Pt(10); r.font.color.rgb = RGBColor(0x1E,0x20,0x28)
        p.paragraph_format.space_after = Pt(2)

def add_mono(doc, text, indent=0.7):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = "Courier New"; r.font.size = Pt(8.2)
    r.font.color.rgb = RGBColor(0x1E,0x20,0x28)
    p.paragraph_format.left_indent = Cm(indent)
    p.paragraph_format.space_after = Pt(1)

def add_table(doc, headers, rows, col_widths=None, mono_cols=None):
    mono_cols = mono_cols or []
    t = doc.add_table(rows=1+len(rows), cols=len(headers))
    t.style = "Table Grid"
    hrow = t.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]; cell.text = h
        _shd(cell, "C8102E")
        for r in cell.paragraphs[0].runs:
            r.bold = True; r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
    for ri, row in enumerate(rows):
        trow = t.rows[ri+1]
        for ci, val in enumerate(row):
            cell = trow.cells[ci]; cell.text = str(val)
            for r in cell.paragraphs[0].runs:
                r.font.size = Pt(8.5)
                if ci in mono_cols:
                    r.font.name = "Courier New"; r.font.size = Pt(8)
        if ri % 2 == 0:
            for ci in range(len(headers)): _shd(trow.cells[ci], "F5F5F5")
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in t.rows: row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t

def add_img(doc, stream, width_cm=15.0, caption=""):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(stream, width=Cm(width_cm))
    if caption:
        cp = doc.add_paragraph(); cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cp.add_run(caption)
        cr.font.size = Pt(8.5); cr.italic = True
        cr.font.color.rgb = RGBColor(0x6C,0x72,0x80)
    doc.add_paragraph()

def info_box(doc, text, bg="DBEAFE", fg=RGBColor(0x1E,0x40,0xAF), prefix="ℹ "):
    """Farbige Info-Box als 1-Zellen-Tabelle."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.cell(0,0); cell.text = prefix + text
    _shd(cell, bg)
    for r in cell.paragraphs[0].runs:
        r.font.size = Pt(9.5); r.font.color.rgb = fg; r.italic = True
    cell.paragraphs[0].paragraph_format.space_before = Pt(4)
    cell.paragraphs[0].paragraph_format.space_after  = Pt(4)
    # Rahmen entfernen (weiche Box)
    tbl = t._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")
    doc.add_paragraph()

def warn_box(doc, text):
    info_box(doc, text, bg="FEE2E2", fg=RGBColor(0x99,0x1B,0x1B), prefix="⚠  ")

def tip_box(doc, text):
    info_box(doc, text, bg="DCFCE7", fg=RGBColor(0x16,0x65,0x34), prefix="✔  ")

def section_banner(doc, text, sub=""):
    """Farbiges Banner als Abschnitts-Trennlinie."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.cell(0,0)
    _shd(cell, "C8102E")
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(6)
    r = p.add_run(text)
    r.font.size = Pt(14); r.bold = True
    r.font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
    if sub:
        r2 = p.add_run("  —  " + sub)
        r2.font.size = Pt(10); r2.italic = True
        r2.font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
    doc.add_paragraph()


# ════════════════════════════════════════════════════════════════════════
# DOKUMENT AUFBAUEN
# ════════════════════════════════════════════════════════════════════════
def build():
    doc = Document()
    for sec in doc.sections:
        sec.top_margin    = Cm(2.0)
        sec.bottom_margin = Cm(2.0)
        sec.left_margin   = Cm(2.5)
        sec.right_margin  = Cm(2.5)

    # ── Deckblatt ─────────────────────────────────────────────────────
    doc.add_paragraph()
    t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("Plattenwechsler")
    r.font.size = Pt(30); r.bold = True
    r.font.color.rgb = RGBColor(0xC8,0x10,0x2E)

    t2 = doc.add_paragraph(); t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = t2.add_run("Technische Dokumentation  ·  Raspberry Pi Software")
    r2.font.size = Pt(14); r2.font.color.rgb = RGBColor(0x1E,0x20,0x28)

    doc.add_paragraph()
    t3 = doc.add_paragraph(); t3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = t3.add_run("DHBW Stuttgart  ·  Projekt G6-TWIE23A  ·  Mai 2026")
    r3.font.size = Pt(11); r3.italic = True
    r3.font.color.rgb = RGBColor(0x6C,0x72,0x80)

    doc.add_paragraph()
    toc_t = doc.add_table(rows=1, cols=3)
    toc_t.style = "Table Grid"
    for i, (lbl, col) in enumerate([("Teil 1: Pi Software","C8102E"),
                                     ("Teil 2: Schnittstellen","2D3142"),
                                     ("Anhang A–G","475569")]):
        cell = toc_t.cell(0,i); _shd(cell, col)
        r = cell.paragraphs[0].add_run(lbl)
        r.bold = True; r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # TEIL 1 — PI SOFTWARE
    # ══════════════════════════════════════════════════════════════════
    section_banner(doc, "Teil 1", "Software Raspberry Pi")

    # 1.1 Systemübersicht
    add_heading(doc, "1.1  Systemübersicht")
    add_para(doc,
        "Der Raspberry Pi 4 bildet das Herzstück des Plattenwechslers. Er koordiniert "
        "den gesamten Ablauf: von der Erkennung fertiger Druckplatten über den eigentlichen "
        "Wechselvorgang bis hin zur Benachrichtigung des Bedieners per Telegram. Die Software "
        "ist vollständig in Python geschrieben und in klar getrennte Module gegliedert.")
    add_para(doc,
        "Die Bedienung erfolgt über einen 7-Zoll-Touchscreen im Vollbild (1280 × 720 Pixel, "
        "PyQt5). Parallel läuft eine Flask-Web-App auf Port 5000, die über jeden Browser "
        "im Netzwerk erreichbar ist und denselben Funktionsumfang bietet.")
    add_para(doc,
        "Der Pi ist über UART (/dev/ttyUSB0, 115200 Baud) mit dem ESP32 auf dem Schlitten "
        "verbunden. Der ESP32 steuert ausschließlich die Motoren und liest Schlitten-Sensoren "
        "aus; der Pi übernimmt die gesamte Ablauflogik, Benutzerinteraktion und Anbindung "
        "an externe Dienste.")
    add_img(doc, make_architektur(), width_cm=15.5,
            caption="Abb. 1 — Systemarchitektur Raspberry Pi")

    # 1.2 Softwaremodule
    add_heading(doc, "1.2  Softwaremodule", level=2)
    add_para(doc,
        "Die Software besteht aus neun Modulen mit klar definierten Verantwortlichkeiten. "
        "Jedes Modul kommuniziert mit den anderen ausschließlich über Callbacks und "
        "Methodenaufrufe — keine globalen Variablen.")
    add_table(doc,
        ["Modul", "Datei", "Aufgabe"],
        [
            ["Hauptablauf",     "core/hauptablauf.py",    "Statemachine, Plattenwechsel, Service-Modus"],
            ["AuftragsQueue",   "core/auftrag_queue.py",  "Thread-sichere FIFO-Warteschlange für Aufträge"],
            ["FehlerBehandlung","core/fehler.py",         "Aktiver Fehler, Quittierung, Historien-Liste"],
            ["ESP-Client",      "io_/esp_client.py",      "UART-Kommunikation, Protokoll-Parsing, Timeouts"],
            ["Mock-ESP",        "io_/mock_esp_client.py", "Software-Simulation des ESP für Tests ohne Hardware"],
            ["GPIO-Manager",    "io_/gpio_manager.py",    "Endschalter-Interrupts, Drucker-fertig-Pins, Not-Aus"],
            ["MQTT-Client",     "io_/mqtt_client.py",     "Broker-Verbindung, Publish/Subscribe aller Topics"],
            ["Telegram-Client", "io_/telegram_client.py", "Bot-API, Befehle empfangen, Status-Nachrichten senden"],
            ["Config",          "config.py",              "config.yaml laden/speichern, CRUD Drucker/Ablage/Magazin"],
            ["HMI",             "ui/main_window.py",      "PyQt5-Vollbild, 6 Tabs, Dialoge, On-Screen-Tastatur"],
            ["Flask Web-App",   "webapp/app.py",          "REST-API + Server-Sent Events (SSE), Port 5000"],
            ["main.py",         "main.py",                "Einstiegspunkt, Dependency Injection, CLI-Argumente"],
        ],
        col_widths=[3.2, 4.2, 9.1]
    )

    # 1.3 Threading
    add_heading(doc, "1.3  Threading-Modell", level=2)
    add_para(doc,
        "Die Anwendung nutzt mehrere Threads, um Hardware-Kommunikation und "
        "UI-Reaktionsfähigkeit zu entkoppeln. Alle Zugriffe auf gemeinsam genutzte Daten "
        "sind durch threading.RLock() abgesichert. UI-Updates aus Hintergrund-Threads "
        "erfolgen ausschließlich über Qt-Signale.")
    add_table(doc,
        ["Thread", "Name", "Aufgabe"],
        [
            ["UI-Thread",       "Qt-Main-Thread",   "PyQt5-Ereignisschleife, alle Widget-Updates"],
            ["Worker-Thread",   "Hauptablauf",       "Statemachine und Plattenwechsel (blockierend)"],
            ["Reader-Thread",   "EspReader",         "Kontinuierliches Lesen vom UART, Protokoll-Parsing"],
            ["Watchdog-Thread", "EspWatchdog",       "Heartbeat-Überwachung, automatischer Reconnect"],
            ["GPIO-Threads",    "gpiozero intern",   "Interrupt-Callbacks für Endschalter und Fertig-Pins"],
        ],
        col_widths=[3.2, 3.8, 9.5]
    )

    doc.add_page_break()

    # 1.4 Statemachine
    add_heading(doc, "1.4  Statemachine")
    add_para(doc,
        "Der Hauptablauf des Raspberry Pi wird durch eine Statemachine gesteuert. "
        "Der aktuelle Zustand bestimmt, welche Aktionen erlaubt sind und wie auf "
        "Ereignisse — Drucker-Fertig-Signal, Fehler, Benutzereingabe — reagiert wird. "
        "Im Normalfall wechselt das System nach dem Start automatisch von "
        "INIT über REFERENZFAHRT in den Zustand BEREITSCHAFT.")
    add_img(doc, make_statemachine(), width_cm=15.5,
            caption="Abb. 2 — Pi-Statemachine")
    add_table(doc,
        ["Zustand", "Beschreibung", "Eintrittsbedingung"],
        [
            ["INIT",           "System startet, wartet auf ESP-Verbindung und Heartbeat",
             "Programmstart"],
            ["REFERENZFAHRT",  "Homing aller vier Achsen läuft (X, Z, Greifer, Türarm)",
             "Nach INIT oder nach Fehlerquittierung"],
            ["BEREITSCHAFT",   "System ist betriebsbereit und wartet auf Aufträge",
             "Referenzfahrt erfolgreich (HOME_DONE vom ESP)"],
            ["PLATTENWECHSEL", "17-Schritt-Wechselsequenz wird gerade ausgeführt",
             "Auftrag aus der Queue entnommen"],
            ["SERVICE",        "Manueller Fahrbetrieb, keine Aufträge werden angenommen",
             "Bediener aktiviert Service-Modus (nur aus BEREITSCHAFT)"],
            ["FEHLER",         "Fehler aufgetreten — alle Motoren gestoppt",
             "ESP-Fehler, Timeout, interner Fehler, Not-Aus"],
            ["NOT_AUS",        "Not-Aus-Taster betätigt — sofortiger Motorstopp",
             "GPIO-Interrupt am Not-Aus-Pin"],
        ],
        col_widths=[3.5, 7.0, 6.0]
    )

    # 1.5 Plattenwechsel
    add_heading(doc, "1.5  Plattenwechsel-Ablauf")
    add_para(doc,
        "Ein Plattenwechsel wird ausgelöst, sobald ein Drucker sein Fertig-Signal gibt "
        "(GPIO-Interrupt, fallende Flanke). Der Auftrag wird in die Queue eingereiht "
        "und der Reihe nach abgearbeitet. Sind mehrere Drucker gleichzeitig fertig, "
        "werden sie nacheinander bedient.")
    add_para(doc,
        "Vor dem Start jedes Wechsels prüft der Pi, ob mindestens eine freie Ablage "
        "und ein verfügbares Magazin vorhanden sind. Ist beides nicht der Fall, "
        "wird der Auftrag sofort mit einer entsprechenden Fehlermeldung abgebrochen — "
        "kein Motor startet.")
    add_para(doc, "Der Wechsel gliedert sich in fünf Phasen:")
    add_table(doc,
        ["Phase", "Beschreibung", "ESP-Kommandos"],
        [
            ["1  Alte Platte holen",
             "Schlitten fährt vor den Drucker, Tür wird geöffnet, "
             "Schlitten fährt auf Druckbett-Höhe, Platte wird aufgenommen, "
             "Schlitten fährt zurück, Tür wird geschlossen.",
             "MOVE_TO → OPEN_DOOR → MOVE_TO → PICKUP → MOVE_TO → CLOSE_DOOR"],
            ["2  Ablage",
             "Schlitten fährt zur nächsten freien Ablage (First-Fit). "
             "Platte wird abgelegt. Ablage-Status wechselt zu BELEGT.",
             "MOVE_TO → DEPOSIT"],
            ["3  Neue Platte holen",
             "Schlitten fährt zum ersten verfügbaren Magazin-Slot. "
             "Platte wird aufgenommen. Magazin-Status wechselt zu LEER.",
             "MOVE_TO → PICKUP"],
            ["4  Neue Platte einlegen",
             "Schlitten fährt vor den Drucker, Tür wird geöffnet, "
             "Schlitten fährt auf Druckbett-Höhe, Platte wird eingelegt, "
             "Schlitten fährt zurück, Tür wird geschlossen.",
             "MOVE_TO → OPEN_DOOR → MOVE_TO → DEPOSIT → MOVE_TO → CLOSE_DOOR"],
            ["5  Heimfahrt",
             "Schlitten kehrt zur Home-Position zurück. "
             "Ist die Queue nicht leer, wird sofort der nächste Auftrag gestartet.",
             "MOVE_HOME  (oder nächster MOVE_TO)"],
        ],
        col_widths=[3.5, 6.5, 6.5]
    )
    info_box(doc,
        "Tritt während eines Plattenwechsels ein Fehler auf, wird die gesamte Queue geleert. "
        "Der physische Zustand von Ablage, Magazin und Schlitten ist danach unbekannt und "
        "muss manuell geprüft werden.")

    # 1.6 Lager
    add_heading(doc, "1.6  Lager-Konzept: Ablagen und Magazine")
    add_para(doc,
        "Das System unterstützt mehrere Ablage-Slots und Magazin-Slots, die unabhängig "
        "voneinander konfiguriert und genutzt werden. Jeder Slot hat eine eigene "
        "X/Z-Position und individuelle Greifer-Parameter.")
    add_para(doc,
        "Der Pi wählt den zu verwendenden Slot automatisch nach dem First-Fit-Prinzip: "
        "Er nimmt den ersten Slot mit dem passenden Status — freie Ablage für DEPOSIT, "
        "verfügbares Magazin für PICKUP. Der Status wird nach jeder Plattenbewegung "
        "sofort in der config.yaml persistiert, sodass er nach einem Neustart erhalten bleibt.")
    add_table(doc,
        ["Slot-Typ", "Status-Felder", "Wann automatisch gesetzt"],
        [
            ["Ablage",  "belegt: true / false",     "Nach erfolgreichem DEPOSIT → belegt=true"],
            ["Magazin", "verfuegbar: true / false",  "Nach erfolgreichem PICKUP → verfuegbar=false"],
        ],
        col_widths=[3.5, 5.0, 8.0]
    )
    tip_box(doc,
        "Der Status kann im Lager-Tab der HMI manuell umgeschaltet werden — "
        "zum Beispiel nachdem eine Ablage manuell geleert oder ein Magazin nachgefüllt wurde.")

    doc.add_page_break()

    # 1.7 Fehlerbehandlung
    add_heading(doc, "1.7  Fehlerbehandlung")
    add_para(doc,
        "Tritt während des Betriebs ein Fehler auf, stoppt der ESP sofort alle Motoren "
        "und wechselt in den Zustand ERROR. Der Pi übernimmt den Fehler, wechselt in "
        "den Zustand FEHLER und informiert den Bediener über HMI, Telegram und MQTT. "
        "Es kann immer nur ein aktiver Fehler vorliegen.")
    add_para(doc, "Fehlerquittierung läuft immer nach demselben Schema ab:")
    add_numbered(doc, [
        "Bediener quittiert den Fehler am Touchscreen (Fehler-Tab) oder per MQTT/Telegram",
        "Pi sendet RESET_ERROR an den ESP — ESP wechselt in NOT_REFERENCED",
        "Pi startet automatisch eine neue Referenzfahrt",
        "Nach erfolgreicher Referenzfahrt kehrt das System in BEREITSCHAFT zurück",
    ])
    doc.add_paragraph()
    add_table(doc,
        ["Fehlerklasse", "Auslöser / ESP-Codes"],
        [
            ["Kommunikation",   "INVALID_COMMAND, BUSY, INVALID_STATE — kein Heartbeat innerhalb 5 s"],
            ["Fahrt",           "MOVE_TIMEOUT (60 s), HOMING_TIMEOUT (30 s), NOT_REFERENCED, POSITION_ERROR"],
            ["Hindernis",       "OBSTACLE — TF-Luna LiDAR unterschreitet Stoppabstand während der Fahrt"],
            ["Sensor",          "SENSOR_FAULT_OBSTACLE (TF-Luna defekt), SENSOR_FAULT_GRIPPER"],
            ["Tür",             "DOOR_NOT_OPEN — VL53L0X meldet zu geringe Distanz vor PICKUP/DEPOSIT"],
            ["Greifer",         "PLATE_NOT_DETECTED — Plattenerkennungs-Taster nach PICKUP nicht aktiv"],
            ["Motor",           "DRIVER_FAULT — CL42T Closed-Loop-Treiber meldet Alarm-Ausgang"],
            ["Lager",           "Pi-intern: keine freie Ablage oder kein verfügbares Magazin"],
            ["Not-Aus",         "GPIO-Interrupt am konfigurierten Not-Aus-Pin (BCM 26 Standard)"],
        ],
        col_widths=[3.5, 13.0]
    )

    # 1.8 HMI-Bedienung
    add_heading(doc, "1.8  HMI-Bedienung")
    add_para(doc,
        "Die HMI läuft im Vollbild auf dem 7-Zoll-Touchscreen (1280 × 720 px). "
        "Die Navigationsleiste auf der linken Seite enthält sechs Tabs. "
        "Der rote STOP-Button am oberen Rand ist auf jeder Seite erreichbar "
        "und hält alle Motorbewegungen sofort an.")
    add_para(doc,
        "Eine QWERTZ-On-Screen-Tastatur erscheint automatisch, wenn ein Texteingabefeld "
        "den Fokus erhält. Eingaben werden per Touch oder angeschlossener Tastatur möglich.")

    add_heading(doc, "Tab: Status", level=3)
    add_para(doc,
        "Der Status-Tab ist die Hauptübersicht und wird beim Start angezeigt. "
        "Ein farbiges Banner oben zeigt den aktuellen Systemzustand in Großschrift an "
        "(z.B. BEREITSCHAFT in Grün, FEHLER in Rot). Darunter sind drei Karten angeordnet:")
    add_bullet(doc, [
        "Schlitten-Position — aktuelle X/Z-Koordinaten in mm, Referenziert-Status, "
        "Platte am Schlitten, Hindernissensor-Status",
        "Drucker — eine Kachel pro konfiguriertem Drucker mit aktuellem Status "
        "(BEREIT / IN QUEUE / AKTIV / FERTIG)",
        "Auftragswarteschlange — Liste der ausstehenden Drucker-IDs",
    ])

    add_heading(doc, "Tab: Manuell", level=3)
    add_para(doc,
        "Zeigt alle konfigurierten Drucker als anklickbare Kacheln. "
        "Ein Antippen löst sofort einen Plattenwechsel-Auftrag für den gewählten Drucker aus "
        "und reiht ihn in die Queue ein. Dieser Tab dient zum manuellen Anstoßen eines "
        "Wechsels unabhängig vom Fertig-Pin des Druckers.")

    add_heading(doc, "Tab: Service", level=3)
    add_para(doc,
        "Der Service-Modus ermöglicht manuelle Fahrten ohne automatischen Plattenwechsel. "
        "Er kann nur aus dem Zustand BEREITSCHAFT aktiviert werden. "
        "Eingehende Drucker-Fertig-Signale werden gespeichert und nach Verlassen des "
        "Service-Modus automatisch in die Queue eingereiht.")
    add_para(doc, "Der Tab enthält vier Bereiche:")
    add_bullet(doc, [
        "Schlitten zu Drucker fahren — ein Button pro konfiguriertem Drucker",
        "Ablagen — ein Button pro Ablage-Slot mit Name und aktuellem Belegungs-Status",
        "Magazine — ein Button pro Magazin-Slot mit Name und Verfügbarkeits-Status",
        "Referenzfahrt — Button zum manuellen Starten der Referenzfahrt",
    ])
    info_box(doc,
        "Die Service-Buttons werden dynamisch aus der aktuellen Konfiguration aufgebaut. "
        "Werden Drucker oder Lager-Slots hinzugefügt oder entfernt, aktualisiert "
        "sich der Service-Tab automatisch.")

    add_heading(doc, "Tab: Drucker", level=3)
    add_para(doc,
        "Alle konfigurierten Drucker werden als Kacheln dargestellt. "
        "Antippen öffnet einen Vollbild-Bearbeitungsdialog. "
        "Über den Button 'Neuen Drucker hinzufügen' wird ein leerer Dialog geöffnet.")
    add_para(doc, "Der Bearbeitungsdialog ist in zwei Tabs aufgeteilt:")
    add_bullet(doc, [
        "Positionen — X-Position, Z Anfahrt, Z Türarm-Höhe, Z Druckbett",
        "Tür / Greifer — Türarm-Hub, Türradius, Öffnungswinkel, Greifer-Tiefe, Hub-Offset",
    ])
    add_para(doc,
        "Name und Fertig-Pin befinden sich immer sichtbar über den Tabs. "
        "Jeder GPIO-Pin darf nur einmal als Fertig-Pin vergeben werden — die HMI "
        "verhindert Doppelbelegungen mit einer Warnmeldung. "
        "Alle Änderungen werden direkt in config.yaml gespeichert.")

    add_heading(doc, "Tab: Lager", level=3)
    add_para(doc,
        "Der Lager-Tab verwaltet Ablagen und Magazine in zwei Unter-Tabs. "
        "Jeder Slot wird als Kachel angezeigt mit Name, Position und aktuellem Status.")
    add_bullet(doc, [
        "Ablagen — Kacheln zeigen FREI (grün) oder BELEGT (rot). "
        "Ein Klick öffnet den Editor oder schaltet den Status manuell um.",
        "Magazine — Kacheln zeigen VERFÜGBAR (grün) oder LEER (grau). "
        "Über 'Neue Ablage / Neues Magazin hinzufügen' werden neue Slots angelegt.",
    ])
    add_para(doc,
        "Jeder Slot hat einen eigenen Editor-Dialog mit X/Z-Position, "
        "Greifer-Tiefe und Hub-Offset — identisch zur Drucker-Konfiguration.")

    add_heading(doc, "Tab: Fehler", level=3)
    add_para(doc,
        "Zeigt den aktuell aktiven Fehler mit Fehlerklasse, ESP-Code und Zeitstempel. "
        "Über den Quittieren-Button wird der Fehler bestätigt und die Referenzfahrt eingeleitet. "
        "Eine scrollbare Liste darunter zeigt die letzten aufgetretenen Fehler als Historie.")
    warn_box(doc,
        "Quittieren ohne die Fehlerursache behoben zu haben kann zu Folgefehlern führen. "
        "Beim Fehler PLATE_NOT_DETECTED muss der Schlitten manuell geprüft werden — "
        "die Platte könnte noch auf dem Schlitten oder abgestürzt sein.")

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # TEIL 2 — SCHNITTSTELLEN
    # ══════════════════════════════════════════════════════════════════
    section_banner(doc, "Teil 2", "Schnittstellen")

    # 2.1 UART
    add_heading(doc, "2.1  ESP32 ↔ Pi: UART-Protokoll")
    add_para(doc,
        "Die Kommunikation zwischen Pi und ESP32 erfolgt über eine serielle Verbindung "
        "(USB-Serial, /dev/ttyUSB0). Das Protokoll ist ASCII-basiert: jede Nachricht "
        "ist eine einzelne Zeile, Felder werden durch Semikolon getrennt.")
    add_table(doc,
        ["Parameter", "Wert"],
        [
            ["Schnittstelle",   "/dev/ttyUSB0  (konfigurierbar)"],
            ["Baudrate",        "115200, 8N1"],
            ["Encoding",        "ASCII, Zeilenende \\n oder \\r\\n"],
            ["Feldtrenner",     "Semikolon  ;"],
            ["Positionsangaben","Immer Ganzzahl in Millimeter"],
            ["Kommando-Format", "CMD;<id>;<befehl>[;<key>=<value>...]"],
            ["Kommando-Queue",  "Max. 8 Einträge — bei Überlauf: RSP;<id>;ERR;BUSY"],
        ],
        col_widths=[4.5, 12.0]
    )

    add_heading(doc, "Kommandos Pi → ESP", level=3)
    add_table(doc,
        ["Kommando", "Parameter", "Voraussetzung"],
        [
            ["PING / STATUS\nSTREAM_ON / STREAM_OFF / STOP",
             "—", "immer"],
            ["HOME",            "—",
             "nicht ERROR, nicht busy"],
            ["MOVE_HOME",       "—",
             "READY oder STOPPED, referenziert"],
            ["MOVE_TO",         "x=<mm>  z=<mm>",
             "READY oder STOPPED, referenziert"],
            ["HOME_SWITCH_HIT", "axis=X|Z",
             "nur in BUSY_HOMING oder BUSY_MOVE_HOME"],
            ["OPEN_DOOR",       "x_approach  z_approach  arm_extend\nradius  angle  hook_drop",
             "READY, referenziert"],
            ["CLOSE_DOOR",      "x_approach  z_approach  arm_extend\nradius  angle  hook_drop",
             "READY, referenziert"],
            ["PICKUP",          "gripper_depth  lift_offset",
             "READY, referenziert"],
            ["DEPOSIT",         "gripper_depth  lift_offset",
             "READY, referenziert"],
            ["RESET_ERROR",     "—",
             "nur in ERROR"],
        ],
        col_widths=[4.2, 5.8, 6.5]
    )

    add_heading(doc, "Antworten ESP → Pi", level=3)
    add_mono(doc, "RSP;<id>;ACK                                ← Kommando angenommen")
    add_mono(doc, "RSP;<id>;ERR;<fehlercode>                   ← abgelehnt, kein Motor gestartet")
    add_mono(doc, "EVT;<id>;OK;<event_name>;<felder>           ← Aktion abgeschlossen")
    add_mono(doc, "EVT;0;STATE;<zustand>;ref=…;x=…;z=…        ← spontaner Zustandswechsel")
    add_mono(doc, "EVT;0;ERR;<fehlercode>;x=…;z=…             ← Fehler (ESP → ERROR)")
    add_mono(doc, "EVT;0;STATUS;state=…;error=…;ref=…;…       ← vollständiger Snapshot")
    add_mono(doc, "EVT;0;HEARTBEAT;uptime_ms=…                ← alle 1000 ms")
    doc.add_paragraph()

    add_para(doc,
        "Besonderheit OPEN_DOOR: Der Pi übergibt x_approach = pos_x des Druckers. "
        "Der ESP fährt intern zur Anfahrposition, führt den Kreisbogen aus und "
        "kehrt selbstständig zur Ausgangsposition zurück — ohne weiteren Pi-Eingriff.")
    add_para(doc,
        "Besonderheit CLOSE_DOOR: Der Pi berechnet die Anfahrposition aus der "
        "Öffnungsgeometrie:  x_close = pos_x + radius · (cos(winkel°) − 1). "
        "Für Öffnungswinkel > 0° ist cos < 1, daher x_close < pos_x.")
    add_para(doc,
        "Besonderheit HOME_SWITCH_HIT: Die Schlitten-Endschalter (X, Z) sind am Pi "
        "angeschlossen. Bei einem GPIO-Interrupt meldet der Pi den Endschalter sofort "
        "per HOME_SWITCH_HIT an den ESP. Greifer- und Türarm-Endschalter sitzen am "
        "ESP und werden intern ausgewertet.")

    # 2.2 MQTT
    add_heading(doc, "2.2  Pi ↔ Außenwelt: MQTT", level=2)
    add_para(doc,
        "Ein lokaler Mosquitto-Broker läuft auf dem Pi. Alle Topics verwenden einen "
        "konfigurierbaren Base-Topic (Standard: plattenwechsler-g6twie23a). "
        "Status-Topics werden mit retain=true veröffentlicht, sodass neue Subscriber "
        "sofort den letzten Stand erhalten.")
    add_table(doc,
        ["Topic (relativ zum Base-Topic)", "Richtung", "Inhalt / Payload"],
        [
            ["status/system",              "Pi → Broker", "Vollständiger Pi-Snapshot (JSON, retained)"],
            ["status/esp",                 "Pi → Broker", "ESP-Snapshot (JSON, retained)"],
            ["status/online",              "Pi → Broker", "online / offline (Will-Message)"],
            ["status/drucker/<id>",        "Pi → Broker", "Drucker-Status pro ID (JSON)"],
            ["error",                      "Pi → Broker", "Fehlerdetails bei neuem Fehler (JSON)"],
            ["event/auftrag",              "Pi → Broker", "Ergebnis eines Plattenwechsels (JSON)"],
            ["cmd/auftrag",                "Broker → Pi", '{"drucker_id": N} — Plattenwechsel starten'],
            ["cmd/quittieren",             "Broker → Pi", '{} — Fehler quittieren'],
            ["cmd/referenzfahrt",          "Broker → Pi", '{} — Referenzfahrt starten'],
            ["cmd/stop",                   "Broker → Pi", '{} — Sofort-Stop'],
            ["cmd/service/modus",          "Broker → Pi", '{"aktiv": true|false}'],
            ["cmd/service/fahre",          "Broker → Pi", '{"ziel": "home"|"ablage"|"magazin"}'],
            ["cmd/service/drucker",        "Broker → Pi", '{"drucker_id": N}'],
            ["cmd/drucker/setzen",         "Broker → Pi", "Drucker-Objekt (JSON)"],
            ["cmd/drucker/entfernen",      "Broker → Pi", '{"id": N}'],
        ],
        col_widths=[5.5, 3.0, 8.0]
    )

    # 2.3 Web-App
    add_heading(doc, "2.3  Pi ↔ Browser: Web-App (Port 5000)", level=2)
    add_para(doc,
        "Die Flask-Web-App spiegelt den vollständigen Funktionsumfang der HMI im Browser. "
        "Sie nutzt Server-Sent Events (SSE) um den Browser in Echtzeit zu aktualisieren "
        "ohne Polling.")
    add_table(doc,
        ["Endpunkt", "Methode", "Funktion"],
        [
            ["/",                       "GET",  "HTML Single-Page-App"],
            ["/api/state",              "GET",  "Aktueller System-Snapshot (JSON)"],
            ["/api/events",             "GET",  "SSE-Stream — Events: state, error"],
            ["/api/cmd/auftrag",        "POST", '{"drucker_id": N}'],
            ["/api/cmd/quittieren",     "POST", '{} — Fehler quittieren'],
            ["/api/cmd/stop",           "POST", '{} — Sofort-Stop'],
            ["/api/cmd/referenzfahrt",  "POST", '{} — Referenzfahrt starten'],
            ["/api/cmd/drucker/setzen", "POST", "Drucker anlegen / aktualisieren"],
        ],
        col_widths=[5.5, 2.0, 9.0]
    )

    # 2.4 GPIO
    add_heading(doc, "2.4  GPIO-Belegung Raspberry Pi", level=2)
    add_para(doc,
        "Alle Pins in BCM-Nummerierung. Endschalter und Not-Aus sind in config.yaml "
        "konfigurierbar. Fertig-Pins werden pro Drucker vergeben.")
    add_table(doc,
        ["Pin (BCM)", "Funktion", "Reaktion des Pi"],
        [
            ["17 (Standard)", "Endschalter X-Achse",
             "GPIO-Interrupt → sofort CMD;x;HOME_SWITCH_HIT;axis=X an ESP"],
            ["4 (Standard)",  "Endschalter Z-Achse",
             "GPIO-Interrupt → sofort CMD;x;HOME_SWITCH_HIT;axis=Z an ESP"],
            ["26 (Standard)", "Not-Aus (konfigurierbar invertiert)",
             "GPIO-Interrupt → CMD;x;STOP an ESP, Zustand → FEHLER"],
            ["pro Drucker",   "Fertig-Pin (frei konfigurierbar, muss eindeutig sein)",
             "GPIO-Interrupt → Auftrag für diesen Drucker in Queue"],
        ],
        col_widths=[3.0, 4.5, 9.0]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # ANHANG
    # ══════════════════════════════════════════════════════════════════
    section_banner(doc, "Anhang", "Referenz, Sequenzen, Konfiguration, Installation")

    # A: Kommandoparameter
    add_heading(doc, "A  Kommandoparameter (vollständig)")

    add_heading(doc, "A.1  OPEN_DOOR / CLOSE_DOOR", level=2)
    add_para(doc,
        "Beide Befehle verwenden dieselben sechs Parameter. Der ESP führt die "
        "komplette Bogenbewegung intern aus und kehrt danach selbstständig zur "
        "Ausgangsposition zurück.")
    add_table(doc,
        ["Parameter", "Typ", "Bedeutung", "Pi-Quelle"],
        [
            ["x_approach", "int (mm)", "Absolute X-Anfahrposition",
             "OPEN: pos_x  /  CLOSE: pos_x + radius·(cos(winkel)−1)"],
            ["z_approach",  "int (mm)", "Absolute Z-Anfahrposition",
             "pos_z_tuer des Druckers"],
            ["arm_extend",  "int (mm)", "Ausfahrlänge Türarm zum Greifen",
             "door_arm_hub_mm des Druckers"],
            ["radius",      "int (mm)", "Kreisradius (Türscharnier → Greifpunkt)",
             "tuer_radius des Druckers"],
            ["angle",       "int (°)",  "Öffnungswinkel der Tür",
             "tuer_winkel des Druckers"],
            ["hook_drop",   "int (mm)", "Z-Versatz für Einhakmechanismus (0 = kein)",
             "fest: 0"],
        ],
        col_widths=[2.8, 2.0, 5.2, 6.5]
    )
    add_para(doc, "OPEN_DOOR — interner ESP-Ablauf:", bold=True)
    add_numbered(doc, [
        "Schlitten fährt auf (x_approach, z_approach) — beide Achsen gleichzeitig",
        "Türarm fährt arm_extend mm aus",
        "Z-Achse fährt hook_drop mm nach oben → Mechanismus hakt in Tür ein",
        "Kreisbogen öffnen: Türarm konstante Drehzahl, X-Achse folgt geometrisch",
        "Z-Achse fährt hook_drop mm nach unten → Mechanismus hakt aus",
        "Türarm fährt vollständig ein",
        "Schlitten kehrt zur Ausgangsposition zurück",
    ])
    add_para(doc, "CLOSE_DOOR — interner ESP-Ablauf:", bold=True)
    add_para(doc,
        "Identisch, aber Schritt 2 fährt den Arm auf Grifftiefe bei geöffneter Tür: "
        "arm_extend + radius · sin(angle) mm. Schritt 4 führt den Kreisbogen rückwärts aus.",
        indent=0.5)
    doc.add_paragraph()

    add_heading(doc, "A.2  PICKUP / DEPOSIT", level=2)
    add_table(doc,
        ["Parameter", "Typ", "PICKUP", "DEPOSIT"],
        [
            ["gripper_depth","int (mm)",
             "Greifer fährt aus → Gabel schiebt sich unter Platte",
             "Greifer fährt aus → Platte wird über Stellfläche positioniert"],
            ["lift_offset",  "int (mm)",
             "Z hebt danach → Platte hebt sich von der Unterlage; Greifer ein",
             "Z hebt zuerst (Platte über Ziel); Greifer aus; Z senkt; Greifer ein"],
        ],
        col_widths=[3.0, 2.0, 6.5, 5.0]
    )

    add_heading(doc, "A.3  MOVE_TO", level=2)
    add_para(doc,
        "Fahrt von der aktuellen Position zur Zielposition. Beide Achsen fahren gleichzeitig.")
    add_para(doc,
        "Sonderfall: Wenn der Schlitten an der Home-Position steht (x=0, z=0), "
        "führt der ESP zuerst einen automatischen Z-Scan durch: Die Z-Achse fährt "
        "die gesamte Verfahrlänge hoch, der TF-Luna LiDAR prüft dabei kontinuierlich "
        "auf Hindernisse (Zustand: BUSY_SCANNING). Erst nach einem freien Scan startet "
        "die eigentliche Fahrt.")

    doc.add_page_break()

    # B: Zustandscodes
    add_heading(doc, "B  Zustands- und Fehlercodes")
    add_heading(doc, "B.1  ESP-Zustandscodes", level=2)
    add_table(doc,
        ["Code", "Bedeutung", "Erlaubte Befehle"],
        [
            ["NOT_REFERENCED",  "Bereit, keine Referenzfahrt",    "HOME, PING, STATUS, STOP"],
            ["READY",           "Referenziert, wartet",            "alle außer RESET_ERROR"],
            ["BUSY_HOMING",     "Referenzfahrt läuft",             "STOP, HOME_SWITCH_HIT"],
            ["BUSY_SCANNING",   "Z-Scan vor Fahrt aus Home",       "STOP"],
            ["BUSY_MOVING",     "Fahrt zu Zielposition",           "STOP"],
            ["BUSY_MOVE_HOME",  "Heimfahrt",                       "STOP, HOME_SWITCH_HIT"],
            ["BUSY_PICKUP",     "Plattenentnahme",                 "STOP"],
            ["BUSY_DEPOSIT",    "Plattenablage",                   "STOP"],
            ["BUSY_OPEN_DOOR",  "Türöffnung",                      "STOP"],
            ["BUSY_CLOSE_DOOR", "Türschließung",                   "STOP"],
            ["STOPPED",         "Per STOP angehalten",             "wie READY"],
            ["ERROR",           "Fehler, Motoren gestoppt",        "RESET_ERROR, PING, STATUS"],
        ],
        col_widths=[3.8, 5.2, 7.5], mono_cols=[0]
    )

    add_heading(doc, "B.2  ESP-Statemachine", level=2)
    add_img(doc, make_esp_states(), width_cm=15.5,
            caption="Abb. 3 — ESP32 Zustandsmaschine")

    add_heading(doc, "B.3  Fehlercodes", level=2)
    add_table(doc,
        ["Code", "Klasse", "Bedeutung"],
        [
            ["INVALID_COMMAND",       "Kommunikation", "Unbekanntes Kommando / Syntaxfehler"],
            ["BUSY",                  "Kommunikation", "Kommando-Queue voll (max. 8 Einträge)"],
            ["INVALID_STATE",         "Kommunikation", "Kommando im aktuellen Zustand nicht erlaubt"],
            ["NOT_REFERENCED",        "Fahrt",         "MOVE_TO ohne vorherige Referenzfahrt"],
            ["MOVE_TIMEOUT",          "Fahrt",         "Ziel nicht in 60 s erreicht"],
            ["HOMING_TIMEOUT",        "Fahrt",         "Referenzfahrt nicht in 30 s abgeschlossen"],
            ["POSITION_ERROR",        "Fahrt",         "Rücklese-Position außerhalb Toleranz"],
            ["OBSTACLE",              "Hindernis",     "TF-Luna unterschreitet Stoppabstand"],
            ["SENSOR_FAULT_OBSTACLE", "Sensor",        "TF-Luna defekt / nicht initialisierbar"],
            ["SENSOR_FAULT_GRIPPER",  "Sensor",        "Greifer-Endschalter antwortet unerwartet"],
            ["DRIVER_FAULT",          "Motor",         "CL42T-Treiber meldet ALM-Ausgang"],
            ["PLATE_NOT_DETECTED",    "Greifer",       "Plattenerkennungs-Taster nach PICKUP nicht aktiv"],
            ["DOOR_NOT_OPEN",         "Tür",           "VL53L0X: Distanz < Schwellwert vor PICKUP/DEPOSIT"],
        ],
        col_widths=[4.2, 3.0, 9.3], mono_cols=[0]
    )

    doc.add_page_break()

    # C: Kommunikationssequenzen
    add_heading(doc, "C  Kommunikationssequenzen")
    add_img(doc, make_protokoll(), width_cm=15.5,
            caption="Abb. 4 — Kommunikationsprotokoll Pi ↔ ESP32")

    add_heading(doc, "Plattenwechsel-Sequenz (Kurzübersicht)", level=2)
    for line in [
        " 1. MOVE_TO  pos_x, pos_z_anfahr          → Ausgangsposition Drucker",
        " 2. OPEN_DOOR x=pos_x, z=pos_z_tuer, …   → Tür öffnen (Kreisbogen)",
        " 3. STATUS   → door_open==1?              → Tür-Prüfung (VL53L0X)",
        " 4. MOVE_TO  pos_x, pos_z_druckbett       → Gabel-Bereitschaft",
        " 5. PICKUP   gripper_depth, lift_offset   → Platte aufnehmen",
        " 6. MOVE_TO  pos_x, pos_z_anfahr",
        " 7. CLOSE_DOOR x=x_close, z=pos_z_tuer   → Tür schließen",
        " 8. MOVE_TO  ablage.x, ablage.z           → Ablage anfahren",
        " 9. DEPOSIT  gripper_depth, lift_offset   → Ablage=BELEGT",
        "10. MOVE_TO  magazin.x, magazin.z         → Magazin anfahren",
        "11. PICKUP   gripper_depth, lift_offset   → Magazin=LEER",
        "12. MOVE_TO  pos_x, pos_z_anfahr",
        "13. OPEN_DOOR …  +  STATUS-Prüfung",
        "14. MOVE_TO  pos_x, pos_z_druckbett",
        "15. DEPOSIT  gripper_depth, lift_offset   → Neue Platte eingelegt",
        "16. MOVE_TO  pos_x, pos_z_anfahr",
        "17. CLOSE_DOOR …  →  MOVE_HOME",
    ]:
        add_mono(doc, line)
    doc.add_paragraph()

    # D: EVT STATUS Felder
    add_heading(doc, "D  EVT STATUS — vollständige Felder")
    add_table(doc,
        ["Feld", "Typ", "Bedeutung"],
        [
            ["state",          "enum",     "Aktueller ESP-Zustand"],
            ["error",          "string",   "Aktiver Fehlercode (NONE wenn kein Fehler)"],
            ["ref",            "0/1",      "1 = referenziert"],
            ["x, z",           "int (mm)", "Ist-Position X und Z"],
            ["target_x, target_z","int (mm)","Soll-Position X und Z"],
            ["busy",           "0/1",      "1 = Bewegung aktiv"],
            ["gripper_home",   "0/1",      "1 = Greifer-Endschalter in Heimposition"],
            ["door_arm_home",  "0/1",      "1 = Türarm-Endschalter in Heimposition"],
            ["obstacle_ok",    "0/1",      "1 = TF-Luna gesund und frei"],
            ["door_open",      "0/1",      "1 = Druckertür offen (VL53L0X-Auswertung)"],
            ["door_dist_mm",   "int (mm)", "Rohwert VL53L0X (Debugging, nur valide an Druckerposition)"],
            ["plate_detected", "0/1",      "1 = Plattenerkennungs-Taster aktiv"],
        ],
        col_widths=[3.5, 2.5, 10.5]
    )

    doc.add_page_break()

    # E: config.yaml
    add_heading(doc, "E  config.yaml — vollständige Referenz")
    add_heading(doc, "E.1  Drucker", level=2)
    add_table(doc,
        ["Schlüssel", "Typ", "Bedeutung"],
        [
            ["id, name",        "int, string",  "Eindeutige ID, Anzeigename in HMI und Web-App"],
            ["pin_fertig",      "int (BCM)",    "GPIO-Fertig-Pin (0 = deaktiviert, muss eindeutig sein)"],
            ["pos_x",           "int (mm)",     "X-Position vor dem Drucker (= x_approach bei OPEN_DOOR)"],
            ["pos_z_anfahr",    "int (mm)",     "Z Ausgangsposition — sichere Höhe vor dem Drucker"],
            ["pos_z_tuer",      "int (mm)",     "Z für OPEN/CLOSE_DOOR (= z_approach)"],
            ["pos_z_druckbett", "int (mm)",     "Z Gabel-Bereitschaftsposition für PICKUP/DEPOSIT"],
            ["door_arm_hub_mm", "int (mm)",     "Türarm-Ausfahrlänge (= arm_extend)"],
            ["tuer_radius",     "int (mm)",     "Kreisradius Türbewegung (Scharnier → Greifpunkt)"],
            ["tuer_winkel",     "int (°)",      "Öffnungswinkel der Tür"],
            ["gripper_depth",   "int (mm)",     "Greifer-Ausfahrtiefe für PICKUP/DEPOSIT"],
            ["lift_offset",     "int (mm)",     "Z-Hub beim PICKUP/DEPOSIT"],
        ],
        col_widths=[3.8, 2.5, 10.2]
    )

    add_heading(doc, "E.2  Weitere Abschnitte", level=2)
    add_table(doc,
        ["Abschnitt", "Wichtige Schlüssel und Standardwerte"],
        [
            ["esp",      "port (/dev/ttyUSB0)  baud (115200)  ack_timeout_s (1.0)  "
                         "move_timeout_s (60.0)  home_timeout_s (30.0)  "
                         "mech_timeout_s (10.0)  heartbeat_timeout_s (5.0)  skip_homing (false)"],
            ["gpio",     "endschalter.x (17)  endschalter.z (4)  "
                         "not_aus.pin (26)  not_aus.invert (false)"],
            ["ablagen",  "id, name, x, z, gripper_depth, lift_offset, belegt (Laufzeit-Status)"],
            ["magazine", "id, name, x, z, gripper_depth, lift_offset, verfuegbar (Laufzeit-Status)"],
            ["mqtt",     "enabled (true)  broker_host (localhost)  broker_port (1883)  "
                         "base_topic (plattenwechsler-g6twie23a)  qos (1)  retain_status (true)"],
            ["telegram", "enabled  bot_token  allowed_chat_ids []  send_status_to_first (true)"],
            ["hmi",      "fullscreen (true)  width (1280)  height (720)"],
            ["system",   "log_level (INFO)  log_file (…/plattenwechsler.log)"],
        ],
        col_widths=[2.8, 13.7]
    )

    # F: Timing
    add_heading(doc, "F  Timing-Parameter")
    add_table(doc,
        ["Parameter", "Wert", "Konfigurierbar"],
        [
            ["UART Baudrate",                    "115200 Baud", "esp.baud"],
            ["Heartbeat-Intervall (ESP → Pi)",   "1000 ms",     "ESP-Firmware (fest)"],
            ["Heartbeat-Timeout (Pi)",           "5000 ms",     "esp.heartbeat_timeout_s"],
            ["STATUS-Stream-Intervall",          "100 ms",      "ESP-Firmware (fest)"],
            ["Hindernissensor-Abrufintervall",   "50 ms",       "ESP-Firmware (fest)"],
            ["ACK-Timeout (Pi → RSP)",           "1000 ms",     "esp.ack_timeout_s"],
            ["Timeout MOVE_TO / OPEN_DOOR / CLOSE_DOOR", "60 s","esp.move_timeout_s"],
            ["Timeout HOME / MOVE_HOME",         "30 s",        "esp.home_timeout_s"],
            ["Timeout PICKUP / DEPOSIT",         "10 s",        "esp.mech_timeout_s"],
            ["MQTT Reconnect",                   "5 s",         "mqtt.reconnect_intervall_s"],
            ["ESP Reconnect",                    "2 s",         "esp.reconnect_intervall_s"],
        ],
        col_widths=[7.0, 2.5, 7.0]
    )

    doc.add_page_break()

    # G: Installation
    add_heading(doc, "G  Installationsanleitung")
    add_heading(doc, "G.1  Systemvoraussetzungen", level=2)
    add_table(doc,
        ["Komponente", "Anforderung"],
        [
            ["Hardware",        "Raspberry Pi 4, 2 GB RAM empfohlen"],
            ["Betriebssystem",  "Raspberry Pi OS 64-bit Bookworm oder neuer"],
            ["Display",         "7-Zoll Touchscreen (1280×720), Rotation 90° konfiguriert"],
            ["Python",          "3.11 oder neuer (im OS enthalten)"],
            ["Compositor",      "Wayland / Labwc (Standard in Pi OS Bookworm)"],
            ["ESP32",           "Firmware geflasht, per USB verbunden (/dev/ttyUSB0)"],
        ],
        col_widths=[3.5, 13.0]
    )

    add_heading(doc, "G.2  Installations-Schritte", level=2)
    add_numbered(doc, [
        "System-Pakete installieren:",
    ])
    add_mono(doc, "sudo apt update && sudo apt install -y python3-pyqt5 mosquitto mosquitto-clients")
    add_numbered(doc, [
        "Projekt entpacken und Python-Umgebung einrichten:",
    ])
    for line in [
        "cd ~  &&  unzip plattenwechsler.zip  &&  cd plattenwechsler",
        "python3 -m venv venv --system-site-packages",
        "source venv/bin/activate",
        "pip install -r requirements.txt",
    ]:
        add_mono(doc, line)
    add_numbered(doc, ["Mosquitto aktivieren:"])
    add_mono(doc, "sudo systemctl enable --now mosquitto")
    add_numbered(doc, ["Display-Rotation einrichten — in ~/.config/labwc/autostart:"])
    add_mono(doc, "wlr-randr --output DSI-1 --transform 90 &")
    doc.add_paragraph()

    add_heading(doc, "G.3  Programm starten", level=2)
    add_table(doc,
        ["Befehl", "Modus"],
        [
            ["venv/bin/python3 -m plattenwechsler.main",              "Vollbild, echte Hardware"],
            ["… --mock",                                               "Mock-ESP, kein Hardware nötig"],
            ["… --no-fullscreen",                                      "Fenster (Entwicklung)"],
            ["… --no-mqtt --no-telegram --no-gui",                     "Nur Logik, kein UI"],
            ["venv/bin/python3 -m webapp.app",                        "Web-App (Port 5000)"],
            ["source venv/bin/activate && pytest tests/ -v",          "Tests ausführen"],
        ],
        col_widths=[9.5, 7.0]
    )

    add_heading(doc, "G.4  Inbetriebnahme-Checkliste", level=2)
    checklist = [
        "ESP32 per USB verbunden  —  ls /dev/ttyUSB*  zeigt /dev/ttyUSB0",
        "Endschalter X und Z angeschlossen, Pins in config.yaml eingetragen",
        "Not-Aus angeschlossen, gpio.not_aus.pin gesetzt",
        "Fertig-Pins aller Drucker eingetragen und eindeutig",
        "Positionen aller Drucker eingemessen (pos_x, pos_z_anfahr, pos_z_tuer, pos_z_druckbett)",
        "Türradius und Öffnungswinkel aller Drucker eingetragen und kalibriert",
        "Mindestens eine Ablage und ein Magazin konfiguriert",
        "Mosquitto läuft  —  systemctl status mosquitto",
        "Programm im Mock-Modus (--mock) gestartet und Referenzfahrt erfolgreich",
        "Referenzfahrt mit echter Hardware durchgeführt — alle Endschalter ausgelöst",
        "Test-Plattenwechsel für jeden Drucker durchgeführt und Ablauf geprüft",
        "Lager-Status nach dem Test manuell zurückgesetzt",
    ]
    for item in checklist:
        p = doc.add_paragraph()
        r = p.add_run("☐  " + item)
        r.font.size = Pt(10); r.font.color.rgb = RGBColor(0x1E,0x20,0x28)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Cm(0.4)

    out = "/home/nura/plattenwechsler/docs/Plattenwechsler_Gesamt.docx"
    doc.save(out)
    print(f"Gespeichert: {out}")

if __name__ == "__main__":
    build()
