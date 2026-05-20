"""Erstellt den Anhang zur Plattenwechsler-Dokumentation als Word-Datei."""
import io, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

C_RED   = "#C8102E"
C_DARK  = "#1E2028"
C_MED   = "#2D3142"
C_LIGHT = "#6C7280"
C_OK    = "#22C55E"
C_WARN  = "#F59E0B"
C_INFO  = "#3B82F6"
C_BG    = "#F8F9FA"
C_WHITE = "#FFFFFF"


def fig_to_stream(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


# ════════════════════════════════════════════════════════════════════════
# Grafik A: Zustandsübergänge ESP (vollständig)
# ════════════════════════════════════════════════════════════════════════
def make_esp_statemachine():
    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 14); ax.set_ylim(0, 9)
    ax.axis("off")

    states = {
        "NOT_REFERENCED": (2.2, 7.8, C_LIGHT),
        "READY":          (2.2, 6.0, C_OK),
        "BUSY_HOMING":    (6.5, 7.8, C_INFO),
        "BUSY_SCANNING":  (6.5, 6.3, C_INFO),
        "BUSY_MOVING":    (6.5, 4.8, C_INFO),
        "BUSY_MOVE_HOME": (6.5, 3.3, C_INFO),
        "BUSY_PICKUP":    (6.5, 1.8, "#7C3AED"),
        "BUSY_DEPOSIT":   (10.5, 1.8, "#7C3AED"),
        "BUSY_OPEN_DOOR": (10.5, 3.3, C_WARN),
        "BUSY_CLOSE_DOOR":(10.5, 4.8, C_WARN),
        "STOPPED":        (10.5, 6.3, C_MED),
        "ERROR":          (10.5, 7.8, "#DC2626"),
    }

    def sbox(x, y, label, color, w=2.6, h=0.75):
        rect = FancyBboxPatch((x-w/2, y-h/2), w, h,
                              boxstyle="round,pad=0.08", linewidth=1.8,
                              edgecolor=color, facecolor=color)
        ax.add_patch(rect)
        ax.text(x, y, label, ha="center", va="center",
                color=C_WHITE, fontsize=8.5, fontweight="bold")

    for name, (x, y, c) in states.items():
        sbox(x, y, name, c)

    def arr(x1, y1, x2, y2, label="", rad=0.0, col=C_LIGHT, lbl_dx=0, lbl_dy=0.13):
        style = f"arc3,rad={rad}"
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=col,
                                   lw=1.3, mutation_scale=12,
                                   connectionstyle=style))
        if label:
            mx = (x1+x2)/2 + lbl_dx
            my = (y1+y2)/2 + lbl_dy
            ax.text(mx, my, label, fontsize=6.8, color=C_DARK, ha="center",
                    bbox=dict(boxstyle="round,pad=0.1", fc=C_BG, ec="none", alpha=0.9))

    # NOT_REFERENCED → BUSY_HOMING
    arr(3.5, 7.8, 5.2, 7.8, "HOME")
    # BUSY_HOMING → READY
    arr(5.2, 7.43, 3.5, 6.38, "HOME_DONE", col=C_OK)
    # READY → BUSY_SCANNING (MOVE_TO aus Home)
    arr(3.5, 6.18, 5.2, 6.3, "MOVE_TO\n(aus Home)", lbl_dy=0.18)
    # BUSY_SCANNING → BUSY_MOVING
    arr(6.5, 5.92, 6.5, 5.17, "Scan ok", col=C_OK)
    # READY → BUSY_MOVING (MOVE_TO nicht aus Home)
    arr(3.5, 5.82, 5.2, 4.95, "MOVE_TO", lbl_dy=0.15)
    # BUSY_MOVING → READY
    arr(5.2, 4.62, 3.5, 5.63, "MOVE_DONE", col=C_OK)
    # READY → BUSY_MOVE_HOME
    arr(3.5, 5.7,  5.2, 3.45, "MOVE_HOME", rad=0.15, lbl_dx=0.5, lbl_dy=0.1)
    # BUSY_MOVE_HOME → READY
    arr(5.2, 3.17, 3.5, 5.63, "MOVE_HOME_DONE", col=C_OK, rad=0.15, lbl_dx=-0.7, lbl_dy=0.1)
    # READY → BUSY_PICKUP
    arr(3.5, 5.63, 5.2, 1.95, "PICKUP", rad=0.2, lbl_dx=0.5)
    # BUSY_PICKUP → READY
    arr(5.2, 1.62, 3.5, 5.63, "PICKUP_DONE", col=C_OK, rad=0.25, lbl_dx=-0.8)
    # READY → BUSY_DEPOSIT
    arr(3.5, 5.63, 9.2, 1.95, "DEPOSIT", rad=-0.15, lbl_dy=0.15)
    # BUSY_DEPOSIT → READY
    arr(9.2, 1.62, 3.5, 5.63, "DEPOSIT_DONE", col=C_OK, rad=-0.2, lbl_dy=-0.1)
    # READY → BUSY_OPEN_DOOR
    arr(3.5, 6.0,  9.2, 3.45, "OPEN_DOOR", rad=-0.1, lbl_dy=0.15)
    # BUSY_OPEN_DOOR → READY
    arr(9.2, 3.17, 3.5, 5.82, "DOOR_OPEN_DONE", col=C_OK, rad=-0.15, lbl_dy=-0.12)
    # READY → BUSY_CLOSE_DOOR
    arr(3.5, 6.2,  9.2, 4.95, "CLOSE_DOOR", rad=-0.05)
    # BUSY_CLOSE_DOOR → READY
    arr(9.2, 4.62, 3.5, 6.0, "DOOR_CLOSE_DONE", col=C_OK, rad=-0.1, lbl_dy=-0.12)
    # STOP → STOPPED (from any BUSY)
    arr(7.8, 4.8,  9.2, 6.0, "STOP", col="#F59E0B")
    # STOPPED → READY (via HOME / MOVE_TO etc.)
    arr(9.2, 5.92, 3.5, 6.18, "HOME / MOVE_TO", col=C_OK, lbl_dy=0.15)
    # Any BUSY → ERROR
    arr(7.8, 7.8, 9.2, 7.8, "Fehler / Timeout", col="#DC2626")
    arr(7.8, 5.05, 9.5, 7.43, "Fehler", col="#DC2626", rad=-0.2)
    # ERROR → NOT_REFERENCED
    arr(9.2, 7.43, 3.5, 7.43, "RESET_ERROR", col=C_OK)

    # Boot arrow
    ax.annotate("", xy=(2.2, 8.17), xytext=(2.2, 8.75),
                arrowprops=dict(arrowstyle="-|>", color=C_DARK, lw=1.5))
    ax.text(2.2, 8.85, "boot", ha="center", fontsize=7.5, color=C_DARK)

    ax.set_title("ESP32 — vollständige Zustandsmaschine", fontsize=12,
                 fontweight="bold", color=C_DARK, pad=10)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# Grafik B: GPIO-Belegung Raspberry Pi
# ════════════════════════════════════════════════════════════════════════
def make_gpio():
    fig, ax = plt.subplots(figsize=(12, 5.5))
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 12); ax.set_ylim(0, 5.5)
    ax.axis("off")

    # Pi-Umriss
    pi = FancyBboxPatch((0.3, 0.4), 3.2, 4.8,
                        boxstyle="round,pad=0.15", linewidth=2.5,
                        edgecolor=C_RED, facecolor="#FFF5F5")
    ax.add_patch(pi)
    ax.text(1.9, 5.0, "Raspberry Pi 4", ha="center", color=C_RED,
            fontsize=10, fontweight="bold")

    pins = [
        (17, "Endschalter X", C_INFO, 4.2),
        (4,  "Endschalter Z", C_INFO, 3.3),
        (26, "Not-Aus",       "#DC2626", 2.4),
        (27, "Drucker 1 fertig", C_OK, 1.5),
        ("...", "weitere Drucker-Pins", C_LIGHT, 0.8),
    ]

    for pin, label, col, y in pins:
        # Pin-Kreis im Pi
        circ = plt.Circle((2.8, y), 0.22, color=col, zorder=3)
        ax.add_patch(circ)
        ax.text(2.8, y, str(pin), ha="center", va="center",
                color=C_WHITE, fontsize=7, fontweight="bold", zorder=4)
        ax.text(1.5, y, f"GPIO {pin}", ha="center", va="center",
                color=C_DARK, fontsize=8)
        # Linie zum Label
        ax.annotate("", xy=(5.5, y), xytext=(3.02, y),
                    arrowprops=dict(arrowstyle="-", color=col, lw=1.5))
        # Label-Box
        lbox = FancyBboxPatch((5.5, y-0.28), 3.8, 0.56,
                              boxstyle="round,pad=0.06",
                              facecolor=col, edgecolor="none", alpha=0.85)
        ax.add_patch(lbox)
        ax.text(7.4, y, label, ha="center", va="center",
                color=C_WHITE, fontsize=8.5, fontweight="bold")

    # UART-Verbindung
    ax.annotate("", xy=(10.5, 2.4), xytext=(3.5, 2.4),
                arrowprops=dict(arrowstyle="<|-|>", color=C_MED,
                               lw=2, mutation_scale=13))
    ax.text(7.0, 2.72, "UART  /dev/ttyUSB0  115200 Baud",
            ha="center", fontsize=8, color=C_MED,
            bbox=dict(boxstyle="round,pad=0.15", fc=C_BG, ec=C_MED, lw=1))
    esp = FancyBboxPatch((10.5, 1.8), 1.2, 1.2,
                         boxstyle="round,pad=0.1",
                         facecolor=C_MED, edgecolor="none")
    ax.add_patch(esp)
    ax.text(11.1, 2.4, "ESP32", ha="center", va="center",
            color=C_WHITE, fontsize=9, fontweight="bold")

    ax.set_title("GPIO-Belegung Raspberry Pi (Pi-Seite)", fontsize=11,
                 fontweight="bold", color=C_DARK, pad=8)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# Grafik C: Vollständige Kommunikationssequenz (Plattenwechsel)
# ════════════════════════════════════════════════════════════════════════
def make_vollsequenz():
    fig, ax = plt.subplots(figsize=(14, 11))
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 14); ax.set_ylim(0, 11)
    ax.axis("off")

    actors = [(2.5, "Raspberry Pi", C_RED), (11.5, "ESP32", C_MED)]
    for x, lbl, col in actors:
        ax.plot([x, x], [0.3, 10.3], color=col, lw=1.5, ls="--", alpha=0.35)
        r = FancyBboxPatch((x-1.2, 10.3), 2.4, 0.55,
                           boxstyle="round,pad=0.08", facecolor=col, edgecolor="none")
        ax.add_patch(r)
        ax.text(x, 10.57, lbl, ha="center", va="center",
                color=C_WHITE, fontsize=9.5, fontweight="bold")

    msgs = [
        # Phase-Header, dann Nachrichten
        ("──── Phase 1: alte Platte holen ────", None, None, None, C_RED),
        ("CMD;1;MOVE_TO;x=370;z=120",                "→", "Ausgangsposition anfahren",    C_INFO, None),
        ("EVT;1;OK;MOVE_DONE",                        "←", "Position erreicht",            C_OK,   None),
        ("CMD;2;OPEN_DOOR;x_approach=370;…",          "→", "Tür öffnen",                   C_WARN, None),
        ("EVT;2;OK;DOOR_OPEN_DONE",                   "←", "Tür geöffnet",                 C_OK,   None),
        ("CMD;3;STATUS  →  door_open=1?",             "→", "Türsensor prüfen",              C_INFO, None),
        ("CMD;4;MOVE_TO;x=370;z=50",                  "→", "Druckbett anfahren",            C_INFO, None),
        ("CMD;5;PICKUP;gripper_depth=120;…",          "→", "Platte aufnehmen",              C_INFO, None),
        ("EVT;5;OK;PICKUP_DONE",                      "←", "Platte aufgenommen",            C_OK,   None),
        ("CMD;6;MOVE_TO;x=370;z=120",                 "→", "Ausgangsposition",              C_INFO, None),
        ("CMD;7;CLOSE_DOOR;x_approach=79;…",          "→", "Tür schließen",                 C_WARN, None),
        ("EVT;7;OK;DOOR_CLOSE_DONE",                  "←", "Tür geschlossen",               C_OK,   None),
        ("──── Phase 2: Ablage ────",          None, None, None, "#D97706"),
        ("CMD;8;MOVE_TO;x=20;z=20",                   "→", "Ablage anfahren",               C_INFO, None),
        ("CMD;9;DEPOSIT;gripper_depth=120;…",         "→", "Ablage ablegen",                C_INFO, None),
        ("EVT;9;OK;DEPOSIT_DONE  →  Ablage=BELEGT",  "←", "",                              C_OK,   None),
        ("──── Phase 3: Magazin ────",         None, None, None, "#059669"),
        ("CMD;10;MOVE_TO;x=50;z=50",                  "→", "Magazin anfahren",              C_INFO, None),
        ("CMD;11;PICKUP;gripper_depth=120;…",         "→", "Neue Platte holen",             C_INFO, None),
        ("EVT;11;OK;PICKUP_DONE  →  Magazin=LEER",   "←", "",                              C_OK,   None),
        ("──── Phase 4: Neue Platte einlegen ────", None, None, None, C_INFO),
        ("CMD;12–16  MOVE_TO / OPEN_DOOR / …",        "→", "analog Phase 1 (DEPOSIT)",      C_LIGHT,None),
        ("──── Phase 5: Heimfahrt ────",       None, None, None, C_LIGHT),
        ("CMD;17;MOVE_HOME",                          "→", "Heimfahrt",                     C_INFO, None),
        ("EVT;17;OK;MOVE_HOME_DONE",                  "←", "zuhause",                       C_OK,   None),
    ]

    y = 9.9
    dy_hdr = 0.35
    dy_msg = 0.37

    for item in msgs:
        msg, direction, note, col, hdr_col = item
        if direction is None:
            # Phase-Header
            ax.add_patch(FancyBboxPatch((0.4, y-0.22), 13.2, 0.32,
                                        boxstyle="round,pad=0.04",
                                        facecolor=hdr_col, edgecolor="none", alpha=0.85))
            ax.text(7.0, y-0.06, msg, ha="center", va="center",
                    color=C_WHITE, fontsize=8.5, fontweight="bold")
            y -= dy_hdr
        else:
            x1 = 2.5 if direction == "→" else 11.5
            x2 = 11.5 if direction == "→" else 2.5
            ax.annotate("", xy=(x2, y), xytext=(x1, y),
                        arrowprops=dict(arrowstyle="-|>", color=col,
                                       lw=1.4, mutation_scale=11))
            bg = "#EFF6FF" if direction == "→" else "#F0FDF4"
            ax.text(7.0, y+0.10, msg, ha="center", va="bottom",
                    fontsize=7.0, color=C_DARK, family="monospace",
                    bbox=dict(boxstyle="round,pad=0.12", fc=bg, ec="none"))
            if note:
                ax.text(0.1, y+0.05, note, ha="left", va="center",
                        fontsize=6.5, color=C_LIGHT, style="italic")
            y -= dy_msg

    ax.set_title("Vollständige Kommunikationssequenz — Plattenwechsel",
                 fontsize=12, fontweight="bold", color=C_DARK, pad=8)
    return fig_to_stream(fig)


# ════════════════════════════════════════════════════════════════════════
# Word-Hilfsfunktionen (identisch mit generate_doku.py)
# ════════════════════════════════════════════════════════════════════════
def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = (RGBColor(0xC8, 0x10, 0x2E) if level == 1
                              else RGBColor(0x1E, 0x20, 0x28))
    h.paragraph_format.space_before = Pt(14 if level == 1 else 8)
    h.paragraph_format.space_after  = Pt(6)
    return h

def add_para(doc, text, bold=False, italic=False, size=10.5):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold; run.italic = italic
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0x1E, 0x20, 0x28)
    p.paragraph_format.space_after = Pt(4)
    return p

def add_mono(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Courier New"
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x1E, 0x20, 0x28)
    p.paragraph_format.left_indent = Cm(0.8)
    p.paragraph_format.space_after = Pt(2)
    return p

def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1+len(rows), cols=len(headers))
    table.style = "Table Grid"
    hrow = table.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]
        cell.text = h
        shd = OxmlElement("w:shd")
        shd.set(qn("w:fill"), "C8102E"); shd.set(qn("w:val"), "clear")
        cell._tc.get_or_add_tcPr().append(shd)
        for run in cell.paragraphs[0].runs:
            run.bold = True; run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for ri, row in enumerate(rows):
        trow = table.rows[ri+1]
        for ci, val in enumerate(row):
            cell = trow.cells[ci]; cell.text = str(val)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
        if ri % 2 == 0:
            for ci in range(len(headers)):
                shd = OxmlElement("w:shd")
                shd.set(qn("w:fill"), "F8F9FA"); shd.set(qn("w:val"), "clear")
                trow.cells[ci]._tc.get_or_add_tcPr().append(shd)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return table

def add_img(doc, stream, width_cm=15.0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(stream, width=Cm(width_cm))
    doc.add_paragraph()


# ════════════════════════════════════════════════════════════════════════
# Anhang-Dokument
# ════════════════════════════════════════════════════════════════════════
def build_anhang():
    doc = Document()
    for section in doc.sections:
        section.top_margin    = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    # Deckblatt
    doc.add_paragraph()
    t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("Plattenwechsler — Anhang")
    r.font.size = Pt(26); r.bold = True
    r.font.color.rgb = RGBColor(0xC8, 0x10, 0x2E)
    t2 = doc.add_paragraph(); t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = t2.add_run("Schnittstellenreferenz · GPIO-Belegung · Konfiguration · Installation")
    r2.font.size = Pt(13); r2.font.color.rgb = RGBColor(0x1E, 0x20, 0x28)
    doc.add_paragraph()
    t3 = doc.add_paragraph(); t3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = t3.add_run("DHBW · Projekt G6-TWIE23A · Mai 2026")
    r3.font.size = Pt(11); r3.italic = True
    r3.font.color.rgb = RGBColor(0x6C, 0x72, 0x80)
    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # A. UART-Protokoll vollständige Referenz
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "A  UART-Protokoll — vollständige Referenz")
    add_para(doc,
        "Verbindung: /dev/ttyUSB0, 115200 Baud, 8N1, ASCII, eine Nachricht pro Zeile (\\n). "
        "Feldtrenner: Semikolon. Kommando-Format: CMD;<id>;<befehl>[;<key>=<value>…]")

    add_heading(doc, "A.1  Kommandos Pi → ESP", level=2)
    add_table(doc,
        ["Kommando", "Parameter (alle Werte in mm oder °)", "Voraussetzung"],
        [
            ["PING",            "—",                                                         "immer"],
            ["STATUS",          "—",                                                         "immer"],
            ["STREAM_ON",       "—",                                                         "immer"],
            ["STREAM_OFF",      "—",                                                         "immer"],
            ["STOP",            "—",                                                         "immer → STOPPED"],
            ["RESET_ERROR",     "—",                                                         "nur in ERROR"],
            ["HOME",            "—",                                                         "nicht ERROR, nicht busy"],
            ["MOVE_HOME",       "—",                                                         "READY / STOPPED, ref=1"],
            ["MOVE_TO",         "x=<mm>  z=<mm>",                                           "READY / STOPPED, ref=1"],
            ["HOME_SWITCH_HIT", "axis=X|Z",                                                  "BUSY_HOMING / BUSY_MOVE_HOME"],
            ["OPEN_DOOR",       "x_approach  z_approach  arm_extend  radius  angle  hook_drop", "READY, ref=1"],
            ["CLOSE_DOOR",      "x_approach  z_approach  arm_extend  radius  angle  hook_drop", "READY, ref=1"],
            ["PICKUP",          "gripper_depth  lift_offset",                                "READY, ref=1"],
            ["DEPOSIT",         "gripper_depth  lift_offset",                                "READY, ref=1"],
        ],
        col_widths=[3.5, 7.5, 5.5]
    )

    add_heading(doc, "A.2  OPEN_DOOR / CLOSE_DOOR — Parameterdetails", level=2)
    add_table(doc,
        ["Parameter", "Typ", "Bedeutung", "Pi-Quelle"],
        [
            ["x_approach", "int (mm)", "Absolute X-Anfahrposition",
             "OPEN: pos_x des Druckers\nCLOSE: pos_x + radius·(cos(winkel)−1)"],
            ["z_approach", "int (mm)", "Absolute Z-Anfahrposition",  "pos_z_tuer des Druckers"],
            ["arm_extend",  "int (mm)", "Ausfahrlänge Türarm",        "door_arm_hub_mm des Druckers"],
            ["radius",      "int (mm)", "Kreisradius (Scharnier → Greifpunkt)", "tuer_radius des Druckers"],
            ["angle",       "int (°)",  "Öffnungswinkel",             "tuer_winkel des Druckers"],
            ["hook_drop",   "int (mm)", "Z-Versatz Einhakmechanismus; 0 = kein Versatz", "fest: 0"],
        ],
        col_widths=[2.8, 2.0, 4.8, 7.0]
    )

    add_heading(doc, "A.3  PICKUP / DEPOSIT — Parameterdetails", level=2)
    add_table(doc,
        ["Parameter", "Typ", "Bedeutung", "Pi-Quelle"],
        [
            ["gripper_depth", "int (mm)", "Ausfahrtiefe Greifer", "gripper_depth der Zielkonfiguration"],
            ["lift_offset",   "int (mm)", "Z-Anhebung bei Pickup / Z-Anhebung vor Greifer-Ausfahrt bei Deposit",
             "lift_offset der Zielkonfiguration"],
        ],
        col_widths=[3.2, 2.0, 5.5, 5.8]
    )

    add_heading(doc, "A.4  Antwortformate ESP → Pi", level=2)
    add_mono(doc, "RSP;<id>;ACK                         ← Kommando angenommen")
    add_mono(doc, "RSP;<id>;ERR;<fehlercode>            ← Kommando abgelehnt")
    add_mono(doc, "EVT;<id>;OK;<event>;x=<mm>;z=<mm>   ← Aktion abgeschlossen")
    add_mono(doc, "EVT;0;STATE;<zustand>;ref=…;x=…;z=… ← Zustandswechsel (spontan)")
    add_mono(doc, "EVT;0;ERR;<fehlercode>;x=…;z=…      ← Fehler (→ ERROR)")
    add_mono(doc, "EVT;0;HEARTBEAT;uptime_ms=…          ← alle 1000 ms")
    add_mono(doc, "EVT;0;STATUS;state=…;error=…;ref=…;x=…;z=…;target_x=…;target_z=…;")
    add_mono(doc, "         busy=…;gripper_home=…;door_arm_home=…;obstacle_ok=…;")
    add_mono(doc, "         door_open=…;door_dist_mm=…;plate_detected=…")
    doc.add_paragraph()

    add_heading(doc, "A.5  EVT STATUS — Felder", level=2)
    add_table(doc,
        ["Feld", "Typ", "Bedeutung"],
        [
            ["state",         "enum",     "Aktueller ESP-Zustand"],
            ["error",         "string",   "Aktiver Fehlercode (NONE wenn kein Fehler)"],
            ["ref",           "0/1",      "1 = referenziert"],
            ["x, z",          "int (mm)", "Ist-Position X / Z"],
            ["target_x, target_z", "int (mm)", "Soll-Position X / Z"],
            ["busy",          "0/1",      "1 = Bewegung aktiv"],
            ["gripper_home",  "0/1",      "1 = Greifer-Endschalter in Heimposition"],
            ["door_arm_home", "0/1",      "1 = Türarm-Endschalter in Heimposition"],
            ["obstacle_ok",   "0/1",      "1 = TF-Luna gesund und frei"],
            ["door_open",     "0/1",      "1 = Druckertür offen (VL53L0X-Auswertung)"],
            ["door_dist_mm",  "int (mm)", "Rohwert Türsensor (Debugging)"],
            ["plate_detected","0/1",      "1 = Plattenerkennungs-Taster aktiv"],
        ],
        col_widths=[3.5, 2.5, 10.5]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # B. Zustandscodes & Fehlercodes
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "B  Zustands- und Fehlercodes")

    add_heading(doc, "B.1  ESP-Zustandscodes", level=2)
    add_table(doc,
        ["Code", "Bedeutung", "Erlaubte Befehle"],
        [
            ["NOT_REFERENCED", "Bereit, keine Referenzfahrt",          "PING, STATUS, HOME, STOP"],
            ["READY",          "Referenziert, wartet",                  "alle außer RESET_ERROR"],
            ["BUSY_HOMING",    "Referenzfahrt läuft",                   "STOP, HOME_SWITCH_HIT"],
            ["BUSY_SCANNING",  "Z-Scan vor Fahrt aus Home",             "STOP"],
            ["BUSY_MOVING",    "Fahrt zu Zielposition",                 "STOP"],
            ["BUSY_MOVE_HOME", "Heimfahrt läuft",                       "STOP, HOME_SWITCH_HIT"],
            ["BUSY_PICKUP",    "Plattenentnahme läuft",                 "STOP"],
            ["BUSY_DEPOSIT",   "Plattenablage läuft",                   "STOP"],
            ["BUSY_OPEN_DOOR", "Türöffnung läuft",                      "STOP"],
            ["BUSY_CLOSE_DOOR","Türschließung läuft",                   "STOP"],
            ["STOPPED",        "Per STOP angehalten",                   "HOME, MOVE_TO, MOVE_HOME, PICKUP, DEPOSIT, OPEN_DOOR, CLOSE_DOOR"],
            ["ERROR",          "Fehler, Motoren gestoppt",              "RESET_ERROR, PING, STATUS"],
        ],
        col_widths=[3.8, 4.8, 8.0]
    )

    add_heading(doc, "B.2  Fehlercodes", level=2)
    add_table(doc,
        ["Code", "Klasse", "Ursache / Bedeutung"],
        [
            ["INVALID_COMMAND",      "Kommunikation", "Unbekanntes Kommando oder Syntaxfehler"],
            ["BUSY",                 "Kommunikation", "Kommando-Queue voll (max. 8 Einträge)"],
            ["INVALID_STATE",        "Kommunikation", "Kommando im aktuellen Zustand nicht erlaubt"],
            ["NOT_REFERENCED",       "Fahrt",         "MOVE_TO ohne vorherige Referenzfahrt"],
            ["MOVE_TIMEOUT",         "Fahrt",         "Zielposition nicht rechtzeitig erreicht"],
            ["HOMING_TIMEOUT",       "Fahrt",         "Referenzfahrt-Timeout abgelaufen"],
            ["POSITION_ERROR",       "Fahrt",         "Rücklese-Position außerhalb Toleranz"],
            ["OBSTACLE",             "Hindernis",     "TF-Luna unterschreitet Stoppabstand während Fahrt"],
            ["SENSOR_FAULT_OBSTACLE","Sensor",        "TF-Luna defekt oder nicht initialisierbar"],
            ["SENSOR_FAULT_GRIPPER", "Sensor",        "Greifer-Endschalter antwortet nicht erwartet"],
            ["DRIVER_FAULT",         "Motor",         "Closed-Loop-Treiber (CL42T) meldet Alarm"],
            ["PLATE_NOT_DETECTED",   "Greifer",       "Plattenerkennungs-Taster nach PICKUP nicht ausgelöst"],
            ["DOOR_NOT_OPEN",        "Tür",           "Türsensor: zu geringe Distanz vor PICKUP/DEPOSIT"],
        ],
        col_widths=[4.2, 3.0, 9.3]
    )

    add_heading(doc, "B.3  Vollständige Zustandsmaschine ESP32", level=2)
    add_img(doc, make_esp_statemachine(), width_cm=16)

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # C. Vollständige Kommunikationssequenz
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "C  Vollständige Kommunikationssequenz")
    add_para(doc,
        "Die folgende Grafik zeigt die vollständige UART-Kommunikation zwischen Pi und ESP32 "
        "während eines typischen Plattenwechsels (vereinfacht — Zustandsmeldungen und "
        "Heartbeats sind aus Gründen der Übersichtlichkeit weggelassen).")
    add_img(doc, make_vollsequenz(), width_cm=16)

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # D. GPIO-Belegung Raspberry Pi
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "D  GPIO-Belegung Raspberry Pi")
    add_para(doc,
        "Alle Pins in BCM-Nummerierung. Endschalter-Pins und Not-Aus sind in config.yaml "
        "konfigurierbar. Fertig-Pins werden pro Drucker in der Konfiguration vergeben.")

    add_img(doc, make_gpio(), width_cm=14)

    add_heading(doc, "D.1  Eingänge (Pi ← Hardware)", level=2)
    add_table(doc,
        ["Pin (BCM)", "Funktion", "Auslöser", "Pi-Reaktion"],
        [
            ["17 (Standard)", "Endschalter X-Achse", "Schlitten an Home-Position X",
             "Sofort HOME_SWITCH_HIT;axis=X an ESP senden"],
            ["4 (Standard)",  "Endschalter Z-Achse", "Schlitten an Home-Position Z",
             "Sofort HOME_SWITCH_HIT;axis=Z an ESP senden"],
            ["26 (Standard)", "Not-Aus",             "Not-Aus-Taster gedrückt",
             "STOP an ESP, Zustand → FEHLER / NOT_AUS"],
            ["pro Drucker",   "Fertig-Pin",          "Drucker meldet Druck fertig (LOW)",
             "Auftrag in Queue einreihen"],
        ],
        col_widths=[2.8, 3.5, 4.2, 6.0]
    )

    add_heading(doc, "D.2  Signalpegel und Entprellung", level=2)
    add_table(doc,
        ["Signal", "Pegel aktiv", "Entprellung", "Hinweis"],
        [
            ["Endschalter X/Z", "LOW (active-low)", "gpiozero intern", "Hardware-Pullup empfohlen"],
            ["Not-Aus",         "LOW oder HIGH (konfigurierbar)", "gpiozero intern", "invert-Flag in config.yaml"],
            ["Drucker Fertig",  "LOW (active-low)", "gpiozero intern", "je Drucker konfigurierbar"],
        ],
        col_widths=[3.5, 4.0, 3.5, 5.5]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # E. config.yaml — vollständige Vorlage
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "E  config.yaml — vollständige Vorlage")
    add_para(doc,
        "Die Datei liegt im Projektverzeichnis /home/nura/plattenwechsler/config.yaml. "
        "Sie wird bei jeder Änderung über die HMI automatisch zurückgeschrieben.")

    config_lines = [
        "system:",
        "  log_level: INFO           # DEBUG | INFO | WARNING | ERROR",
        "  log_file: /home/nura/plattenwechsler/plattenwechsler.log",
        "",
        "esp:",
        "  port: /dev/ttyUSB0",
        "  baud: 115200",
        "  read_timeout_s: 0.1",
        "  ack_timeout_s: 1.0        # Max. Wartezeit auf RSP;ACK",
        "  move_timeout_s: 60.0      # Timeout Fahr- und Türbefehle",
        "  home_timeout_s: 30.0      # Timeout HOME / MOVE_HOME",
        "  mech_timeout_s: 10.0      # Timeout PICKUP / DEPOSIT",
        "  heartbeat_timeout_s: 5.0  # Reconnect ohne Heartbeat",
        "  reconnect_intervall_s: 2.0",
        "  skip_homing: false        # true nur für Tests",
        "",
        "gpio:",
        "  endschalter:",
        "    x: 17                   # BCM-Pin Endschalter X-Achse",
        "    z: 4                    # BCM-Pin Endschalter Z-Achse",
        "  not_aus:",
        "    pin: 26",
        "    invert: false           # true = active-high",
        "",
        "drucker:",
        "  - id: 1",
        "    name: Drucker 1",
        "    pin_fertig: 27          # BCM-Pin, muss eindeutig sein",
        "    pos_x: 370              # X-Position mm",
        "    pos_z_anfahr: 120       # Z Ausgangsposition mm",
        "    pos_z_tuer: 105         # Z für OPEN/CLOSE_DOOR mm",
        "    pos_z_druckbett: 50     # Z Gabel-Bereitschaft mm",
        "    door_arm_hub_mm: 30     # arm_extend mm",
        "    tuer_radius: 150        # Kreisradius mm",
        "    tuer_winkel: 160        # Öffnungswinkel °",
        "    gripper_depth: 120      # Greifer-Ausfahrtiefe mm",
        "    lift_offset: 8          # Z-Hub mm",
        "",
        "ablagen:",
        "  - id: 1",
        "    name: Ablage 1",
        "    x: 20",
        "    z: 20",
        "    gripper_depth: 120",
        "    lift_offset: 8",
        "    belegt: false           # wird zur Laufzeit aktualisiert",
        "",
        "magazine:",
        "  - id: 1",
        "    name: Magazin 1",
        "    x: 50",
        "    z: 50",
        "    gripper_depth: 120",
        "    lift_offset: 8",
        "    verfuegbar: true        # wird zur Laufzeit aktualisiert",
        "",
        "mqtt:",
        "  enabled: true",
        "  broker_host: localhost    # oder externer Broker",
        "  broker_port: 1883",
        "  username: ''",
        "  password: ''",
        "  client_id: plattenwechsler-pi",
        "  base_topic: plattenwechsler-g6twie23a",
        "  qos: 1",
        "  retain_status: true",
        "  reconnect_intervall_s: 5.0",
        "",
        "telegram:",
        "  enabled: true",
        "  bot_token: <BOT_TOKEN>",
        "  allowed_chat_ids:",
        "    - <CHAT_ID>",
        "  send_status_to_first: true",
        "",
        "hmi:",
        "  fullscreen: true",
        "  width: 1280",
        "  height: 720",
    ]
    for line in config_lines:
        add_mono(doc, line if line else " ")

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # F. Timing-Parameter
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "F  Timing-Parameter")
    add_table(doc,
        ["Parameter", "Wert", "Konfigurierbar in"],
        [
            ["UART Baudrate",                    "115200 Baud",  "config.yaml esp.baud"],
            ["Heartbeat-Intervall (ESP → Pi)",   "1000 ms",      "ESP-Firmware (fest)"],
            ["Heartbeat-Timeout (Pi)",           "5000 ms",      "config.yaml esp.heartbeat_timeout_s"],
            ["STATUS-Stream-Intervall",          "100 ms",       "ESP-Firmware (fest)"],
            ["Hindernissensor-Abfrageintervall", "50 ms",        "ESP-Firmware (fest)"],
            ["ACK-Timeout (Pi wartet auf RSP)",  "1000 ms",      "config.yaml esp.ack_timeout_s"],
            ["Timeout MOVE_TO / OPEN_DOOR / CLOSE_DOOR", "60.000 ms", "config.yaml esp.move_timeout_s"],
            ["Timeout HOME / MOVE_HOME",         "30.000 ms",    "config.yaml esp.home_timeout_s"],
            ["Timeout PICKUP / DEPOSIT",         "10.000 ms",    "config.yaml esp.mech_timeout_s"],
            ["MQTT Reconnect-Intervall",         "5000 ms",      "config.yaml mqtt.reconnect_intervall_s"],
            ["ESP Reconnect-Intervall",          "2000 ms",      "config.yaml esp.reconnect_intervall_s"],
        ],
        col_widths=[7.0, 3.0, 6.5]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # G. Installationsanleitung
    # ══════════════════════════════════════════════════════════════════
    add_heading(doc, "G  Installationsanleitung")

    add_heading(doc, "G.1  Voraussetzungen", level=2)
    add_table(doc,
        ["Komponente", "Version / Anforderung"],
        [
            ["Raspberry Pi OS", "64-bit Bookworm oder neuer"],
            ["Python",          "3.11 oder neuer (im OS enthalten)"],
            ["Wayland",         "Labwc als Compositor (Standard in Pi OS Bookworm)"],
            ["Mosquitto",       "MQTT-Broker (lokal, apt)"],
            ["ESP32",           "Firmware muss geflasht und per USB verbunden sein"],
        ],
        col_widths=[4.0, 12.5]
    )

    add_heading(doc, "G.2  Installation", level=2)
    install_steps = [
        "# 1. System-Pakete installieren",
        "sudo apt update && sudo apt install -y \\",
        "    python3-pyqt5 python3-pip python3-venv \\",
        "    mosquitto mosquitto-clients git unzip",
        "",
        "# 2. Mosquitto aktivieren",
        "sudo systemctl enable --now mosquitto",
        "",
        "# 3. Projekt entpacken",
        "cd ~ && unzip plattenwechsler.zip",
        "cd plattenwechsler",
        "",
        "# 4. Virtuelle Umgebung erstellen und Abhängigkeiten installieren",
        "python3 -m venv venv --system-site-packages",
        "source venv/bin/activate",
        "pip install -r requirements.txt",
        "",
        "# 5. Startaliase setzen (einmalig)",
        "echo 'alias platte=\"cd ~/plattenwechsler && QT_QPA_PLATFORM=wayland \\",
        "  WAYLAND_DISPLAY=wayland-0 venv/bin/python3 -m plattenwechsler.main\"' >> ~/.bashrc",
        "source ~/.bashrc",
    ]
    for line in install_steps:
        add_mono(doc, line if line else " ")

    add_heading(doc, "G.3  Display-Rotation (Pi Touch Display 2)", level=2)
    add_para(doc, "In ~/.config/labwc/autostart folgende Zeile eintragen:")
    add_mono(doc, "wlr-randr --output DSI-1 --transform 90 &")

    add_heading(doc, "G.4  Programm starten", level=2)
    add_table(doc,
        ["Befehl", "Modus"],
        [
            ["platte",                                       "Vollbild, echte Hardware"],
            ["platte --mock",                                "Mock-ESP, kein Hardware nötig"],
            ["platte --no-fullscreen",                       "Im Fenster (Entwicklung)"],
            ["platte --no-mqtt --no-telegram --no-gui",      "Nur Logik, kein UI"],
            ["venv/bin/python3 -m webapp.app",               "Web-App parallel starten (Port 5000)"],
            ["source venv/bin/activate && pytest tests/ -v", "Tests ausführen"],
        ],
        col_widths=[8.0, 8.5]
    )

    add_heading(doc, "G.5  Inbetriebnahme-Checkliste", level=2)
    checklist = [
        "☐  ESP32 per USB verbunden, /dev/ttyUSB0 verfügbar (ls /dev/ttyUSB*)",
        "☐  Endschalter X und Z angeschlossen und in config.yaml eingetragen",
        "☐  Not-Aus angeschlossen und in config.yaml eingetragen",
        "☐  Fertig-Pins aller Drucker eingetragen und eindeutig",
        "☐  Positionen aller Drucker (pos_x, pos_z_anfahr, pos_z_tuer, pos_z_druckbett) eingemessen",
        "☐  Türradius und Öffnungswinkel aller Drucker eingetragen",
        "☐  Ablagen und Magazine mit korrekten Positionen konfiguriert",
        "☐  Mosquitto läuft: systemctl status mosquitto",
        "☐  Telegram Bot-Token und Chat-ID eingetragen (wenn gewünscht)",
        "☐  Programm im Mock-Modus gestartet und Referenzfahrt erfolgreich",
        "☐  Programm mit echter Hardware gestartet, Referenzfahrt und Test-Plattenwechsel",
    ]
    for item in checklist:
        p = doc.add_paragraph(item)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Cm(0.5)
        for run in p.runs:
            run.font.size = Pt(10)

    out = "/home/nura/plattenwechsler/docs/Plattenwechsler_Anhang_Pi.docx"
    doc.save(out)
    print(f"Gespeichert: {out}")


if __name__ == "__main__":
    build_anhang()
