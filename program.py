from pathlib import Path

import fitz
import pdfplumber
import csv

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
current_dir = Path(__file__).parent

INPUT_DIR = current_dir / "input"
OUTPUT_DIR = current_dir / "output"

VOICE_CSV = OUTPUT_DIR / "voice_usage.csv"
DATA_CSV = OUTPUT_DIR / "data_usage.csv"
SMS_CSV = OUTPUT_DIR / "sms_usage.csv"


OUTPUT_DIR.mkdir(exist_ok=True)



# ─────────────────────────────────────────────
# INSPECTION FUNCTIONS
# ─────────────────────────────────────────────
def pdfplumber_to_fitz(bbox, page):
    """
    Convert pdfplumber coordinates to pymupdf/fitz coordinates.
    pdfplumber compensates for rotation, fitz uses physical page coordinates.
    For rotation=90: fitz_x = pdfplumber_y, fitz_y = page.width - pdfplumber_x
    """
    x0, y0, x1, y1 = bbox
 
    if page.rotation == 90:
        return (y0, page.width - x1, y1, page.width - x0)
    elif page.rotation == 270:
        return (page.height - y1, x0, page.height - y0, x1)
    elif page.rotation == 180:
        return (page.width - x1, page.height - y1, page.width - x0, page.height - y0)
    else:
        return (x0, y0, x1, y1)

def draw_boxes(input_pdf, output_pdf, pages_rects, color=(1, 0, 0), fill=None, width=0.5):
    doc = fitz.open(input_pdf)

    for page_num, page in enumerate(doc):
        page_rects = pages_rects

        for rect_coords in page_rects:
            rect = fitz.Rect(rect_coords[0:4])

            page.draw_rect(
                rect,
                fill=fill,
                color=color,
                width=width
            )

    doc.save(output_pdf)

def draw_section_areas(fileName, output_file, sections, page):
    fitz_sections = [pdfplumber_to_fitz(s, page) for s in sections]
    draw_boxes(
        input_pdf=fileName,
        output_pdf=output_file,
        pages_rects=fitz_sections,
        width=1.5
    )



# ─────────────────────────────────────────────
# EXTRACTION FUNCTIONS
# ─────────────────────────────────────────────
def normalize_table(table):

    result = []

    acc = [table[0]]
    for row in table[1:]:
        if row[0] == '':
            acc.append(row)
        else:
            merged = [
                ' '.join(filter(None, [r[i] for r in acc])).strip()
                for i in range(len(acc[0]))
            ]
            result.append(merged)
            acc = [row]

    merged = [
        ' '.join(filter(None, [r[i] for r in acc])).strip()
        for i in range(len(acc[0]))
    ]
    result.append(merged)

    return result

def extract_data(FILE, inspect=False):

    voice_data = []
    data_data = []
    sms_data = []

    with pdfplumber.open(FILE) as pdf:

        page = pdf.pages[0]


        words = page.extract_words()

        # 1. Identify header area using keywords
        x0_header = next(w['x0'] for w in words if w['text'] == 'Run')
        x1_header = page.width * 0.22
        y0_header = next(w['top'] for w in words if w['text'] == 'Run')
        y1_header = next(w['bottom'] for w in words if w['text'] == 'Number:')    

        x0_header -= 1
        y0_header -= 1
        x1_header += 1
        y1_header += 1 

      
        # 2. Identify table area using keywords
        x0_table = next(w['x0'] for w in words if w['text'] == 'Item')
        x1_table = page.width * 0.96       
        y0_table = next(w['top'] for w in words if w['text'] == 'Item')
        y1_table = next(w['top'] for w in words if w['text'] == 'AT&T') - 15

        x0_table -= 2
        y0_table -= 2
        x1_table += 2
        y1_table += 2


        sections = [
            (x0_header, y0_header, x1_header, y1_header),  # Header
            (x0_table, y0_table, x1_table, y1_table)       # Table
        ]

        if inspect:
            print(f"Header area coordinates: ({x0_header}, {y0_header}) to ({x1_header}, {y1_header})")
            print(f"Table area coordinates: ({x0_table}, {y0_table}) to ({x1_table}, {y1_table})")            
            draw_section_areas(FILE, OUTPUT_DIR / "sections_inspection.pdf", sections, page)



        for page in pdf.pages:

            # Extract header text
            header_crop = page.crop(sections[0])
            header_text = header_crop.extract_text()

            # Extract table data
            table_crop = page.crop(sections[1])
            table = table_crop.extract_table({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
            })

            table = normalize_table(table)

            # "Voice Usage For: (614)404-6348"
            section_type = None
            if 'Voice Usage For:' in header_text:
                section_type = 'voice'
                if len(voice_data) == 0:
                    voice_data.append(table[0])
                voice_data.extend(table[1:])

            elif 'Data Usage For:' in header_text:
                section_type = 'data'
                if len(data_data) == 0:
                    data_data.append(table[0])
                data_data.extend(table[1:])

            elif 'SMS Usage For:' in header_text:
                section_type = 'sms'
                if len(sms_data) == 0:
                    sms_data.append(table[0])   
                sms_data.extend(table[1:])

    return {
        'voice': voice_data,
        'data': data_data,
        'sms': sms_data
    }



# ─────────────────────────────────────────────
# WRITE CSV
# ─────────────────────────────────────────────
def write_csv(path, data):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(data)



# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":

    FILE = INPUT_DIR / "example.pdf"
    data = extract_data(FILE, inspect=True) 

    write_csv(VOICE_CSV, data['voice'])
    write_csv(DATA_CSV, data['data'])
    write_csv(SMS_CSV, data['sms'])

    print(f"Data extracted and saved to:\n- {VOICE_CSV}\n- {DATA_CSV}\n- {SMS_CSV}")

