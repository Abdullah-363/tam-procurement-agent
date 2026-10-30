"""
Generates the fictional company's data for Tam.
Run:  python data/make_data.py      (from the backend folder)

Everything here is FICTIONAL: Raseen Holding Company, its people and its
vendors are invented. Only well-known products (SAP, Adobe, Microsoft) are
named, because they make the sole-source / renewal rules believable.
Currency: SAR.
"""
import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

HERE = Path(__file__).parent

COMPANY = {"name": "Raseen Holding Company", "name_ar": "شركة رصين القابضة", "currency": "SAR"}

# ---------------------------------------------------------------- people
PEOPLE = {
    "requester":      {"name": "Omar Al-Qahtani",   "title": "IT Analyst",           "department": "IT"},
    "it_head":        {"name": "Khalid Al-Zahrani", "title": "Head of IT",           "department": "IT"},
    "accountant":     {"name": "Sara Al-Otaibi",    "title": "Accountant",           "department": "Finance"},
    "finance_head":   {"name": "Nawaf Al-Shehri",   "title": "Head of Finance",      "department": "Finance"},
    "cfo":            {"name": "Reem Al-Dosari",    "title": "Chief Financial Officer", "department": "Executive"},
    "ceo":            {"name": "Turki Al-Mutairi",  "title": "Chief Executive Officer", "department": "Executive"},
    "admin_head":     {"name": "Faisal Al-Harbi",   "title": "Head of Administration", "department": "Admin"},
    "hr_head":        {"name": "Lama Al-Subaie",    "title": "Head of HR",           "department": "HR"},
    "marketing_head": {"name": "Yousef Al-Shammari", "title": "Head of Marketing",   "department": "Marketing"},
    "procurement_head": {"name": "Huda Al-Ghamdi",  "title": "Head of Procurement",  "department": "Procurement"},
    "auditor":        {"name": "Majed Al-Anazi",    "title": "Internal Auditor",     "department": "Internal Audit"},
}

# ---------------------------------------------------------------- policy
POLICY = {
    "currency": "SAR",
    "procurement_methods": {
        "low_value_max": 20000,          # < 20,000  -> Low Value, 1 quote
        "rfq_max": 200000,               # 20,000 - <200,000 -> RFQ, 3 quotes
        "rfq_min_quotes": 3,             # >= 200,000 -> Competitive Bidding (mandatory)
        "sole_source_exempt_from_bidding": True,
        "sole_source_requires_justification": True,
        "single_source_requires_justification_above": 20000,
    },
    "price_anomaly_threshold_pct": 20,   # unit price > reference by 20% -> flag
    "price_too_low_threshold_pct": 50,   # unit price < 50% of reference -> likely typo
    "approval_tiers": [
        {"max": 40000,  "final": ["finance_head"]},
        {"max": 200000, "final": ["cfo"]},
        {"max": None,   "final": ["cfo", "ceo"]},
    ],
    "approval_prefix": ["department_head", "accountant"],
    # Mobile phones and lines, by grade (Wisayah-style policy)
    "mobile_policy": {
        "manager": {"device": "MOB-IPH-PRO", "package": "PKG-MGR", "label": "iPhone Pro + unlimited package with unlimited roaming"},
        "staff":   {"device": "MOB-IPH",     "package": "PKG-STAFF", "label": "iPhone + unlimited package (no unlimited roaming)"},
        "intern":  None,
        "commitment_months": 12,
        "approval": ["hr_head", "department_head", "it_head"],
    },
    # HR confirms headcount when new per-user seats are bought, or when the purchase is for new employees
    "hr_confirmation": {"role": "hr_head", "after": "department_head",
                        "when": ["new per-user seats (licenses, subscriptions)", "equipment for new employees"]},
    "department_heads": {"IT": "it_head", "Admin": "admin_head", "HR": "hr_head", "Marketing": "marketing_head",
                         "Finance": "finance_head"},
    "follow_up_hours": {               # simulated hours
        "Normal": {"remind_after": 48, "escalate_after": 96},
        "Urgent": {"remind_after": 6,  "escalate_after": 24},
    },
    "escalation_target": {"department_head": "cfo", "it_head": "cfo", "admin_head": "cfo", "hr_head": "cfo",
                          "marketing_head": "cfo", "accountant": "finance_head",
                          "finance_head": "cfo", "cfo": "ceo", "ceo": "ceo"},
    "min_justification_chars": 60,
}

# ---------------------------------------------------------------- G/L accounts + budget
GL_ACCOUNTS = [
    # dept, gl, name, annual budget, spent YTD
    ("IT", "6110", "IT Hardware & Equipment",              450000, 268400),
    ("IT", "6120", "Software Licenses & Digital Services", 380000, 241900),
    ("IT", "6130", "Network & Infrastructure",             300000, 162300),
    ("IT", "6150", "Telecom & Mobile Services",            280000, 168400),
    ("IT", "6140", "IT Maintenance & Support Contracts",   520000, 198750),
    ("HR", "6210", "Training & Development",               250000, 131000),
    ("HR", "6220", "Recruitment",                          180000,  97500),
    ("Admin", "6310", "Office Supplies & Stationery",       90000,  61200),
    ("Admin", "6320", "Office Furniture",                  260000,  98400),
    ("Admin", "6330", "Facilities & Maintenance",          400000, 212300),
    ("Finance", "6510", "Market Data Subscriptions",        650000, 315000),
    ("Marketing", "6410", "Events & Exhibitions",          300000, 145000),
    ("Marketing", "6420", "Printing & Branding",           120000,  51200),
]

# ---------------------------------------------------------------- catalog (reference = last purchase price)
CATALOG = [
    {"code": "LAP-DEV-14",  "name": "Developer laptop 14in (32GB RAM, 1TB SSD, 3-yr warranty)", "category": "hardware", "gl": "6110", "ref_price": 6500},
    {"code": "LAP-STD-14",  "name": "Standard business laptop 14in (16GB RAM, 512GB SSD)",       "category": "hardware", "gl": "6110", "ref_price": 4200},
    {"code": "MON-27",      "name": "27in QHD monitor",                                          "category": "hardware", "gl": "6110", "ref_price": 1250},
    {"code": "DOCK-USBC",   "name": "USB-C docking station",                                     "category": "hardware", "gl": "6110", "ref_price": 650},
    {"code": "PRN-A3-MFP",  "name": "A3 multifunction printer",                                  "category": "hardware", "gl": "6110", "ref_price": 14500},
    {"code": "NET-CTRL-GW", "name": "Branch Wi-Fi controller gateway (up to 32 APs)",            "category": "network",  "gl": "6130", "ref_price": 9800},
    {"code": "NET-CTRL-LIC","name": "Controller capacity license, per access point",             "category": "network",  "gl": "6130", "ref_price": 520,  "requires": "NET-CTRL-GW"},
    {"code": "NET-CTRL-SUP","name": "3-year support contract for NET-CTRL-GW",                   "category": "network",  "gl": "6140", "ref_price": 2600, "requires": "NET-CTRL-GW"},
    {"code": "NET-AP6",     "name": "Wi-Fi 6 indoor access point",                               "category": "network",  "gl": "6130", "ref_price": 3400},
    {"code": "NET-AP6-SUP", "name": "3-year support for NET-AP6, per unit",                      "category": "network",  "gl": "6140", "ref_price": 900,  "requires": "NET-AP6"},
    {"code": "LIC-ADOBE-CC","name": "Adobe Creative Cloud All Apps, annual, per user",           "category": "software", "gl": "6120", "ref_price": 3100, "per_user": True},
    {"code": "LIC-M365-E3", "name": "Microsoft 365 E3, annual, per user",                        "category": "software", "gl": "6120", "ref_price": 1450, "per_user": True},
    # IT accessories
    {"code": "KBM-SET",     "name": "Wireless keyboard and mouse set",                           "category": "hardware", "gl": "6110", "ref_price": 220},
    {"code": "HEADSET-UC",  "name": "Noise-cancelling headset for calls",                        "category": "hardware", "gl": "6110", "ref_price": 450},
    {"code": "WEBCAM-HD",   "name": "Full HD webcam",                                            "category": "hardware", "gl": "6110", "ref_price": 380},
    {"code": "PROJ-4K",     "name": "Meeting room projector (4K)",                               "category": "hardware", "gl": "6110", "ref_price": 3900},
    {"code": "TAB-10",      "name": "10in business tablet",                                      "category": "hardware", "gl": "6110", "ref_price": 2800},
    {"code": "UPS-1500",    "name": "Desktop UPS 1500VA",                                        "category": "hardware", "gl": "6110", "ref_price": 900},
    {"code": "NET-SW24",    "name": "24-port managed network switch",                            "category": "network",  "gl": "6130", "ref_price": 5200},
    {"code": "NET-FW",      "name": "Branch firewall appliance",                                 "category": "network",  "gl": "6130", "ref_price": 14000},
    {"code": "LIC-PBI-PRO", "name": "Power BI Pro, annual, per user",                            "category": "software", "gl": "6120", "ref_price": 520, "per_user": True},
    {"code": "LIC-EDR",     "name": "Endpoint security license, annual, per device",             "category": "software", "gl": "6120", "ref_price": 180},
    {"code": "PRN-MAINT",   "name": "Printer fleet maintenance contract, annual",                "category": "hardware", "gl": "6140", "ref_price": 12000},
    # Office furniture
    {"code": "FUR-DESK-160","name": "Office desk 160cm with cable tray",                         "category": "furniture", "gl": "6320", "ref_price": 1450},
    {"code": "FUR-DESK-SIT","name": "Height-adjustable sit-stand desk",                          "category": "furniture", "gl": "6320", "ref_price": 3200},
    {"code": "FUR-CHAIR-ERG","name": "Ergonomic office chair",                                   "category": "furniture", "gl": "6320", "ref_price": 1850},
    {"code": "FUR-CHAIR-VIS","name": "Visitor chair",                                            "category": "furniture", "gl": "6320", "ref_price": 480},
    {"code": "FUR-TABLE-8", "name": "Meeting table, 8 seats",                                    "category": "furniture", "gl": "6320", "ref_price": 6800},
    {"code": "FUR-CABINET", "name": "Lockable filing cabinet, 4 drawers",                        "category": "furniture", "gl": "6320", "ref_price": 950},
    {"code": "FUR-PEDESTAL","name": "Mobile drawer pedestal",                                    "category": "furniture", "gl": "6320", "ref_price": 520},
    {"code": "FUR-WHITEBRD","name": "Magnetic whiteboard 180x120cm",                             "category": "furniture", "gl": "6320", "ref_price": 650},
    {"code": "FUR-SOFA",    "name": "Reception sofa, 3 seats",                                   "category": "furniture", "gl": "6320", "ref_price": 4300},
    # Office supplies
    {"code": "SUP-PAPER-A4","name": "A4 copy paper, box of 5 reams",                             "category": "office_supplies", "gl": "6310", "ref_price": 120},
    {"code": "SUP-TONER",   "name": "Laser toner cartridge (black)",                             "category": "office_supplies", "gl": "6310", "ref_price": 380},
    {"code": "SUP-STAT-KIT","name": "Stationery kit (pens, notebooks, staplers)",                "category": "office_supplies", "gl": "6310", "ref_price": 75},
    {"code": "SUP-COFFEE",  "name": "Coffee and tea supplies, monthly pack",                     "category": "office_supplies", "gl": "6310", "ref_price": 950},
    # Facilities
    {"code": "FAC-AC-SPLIT","name": "Split air conditioner 2.5 ton, installed",                  "category": "facilities", "gl": "6330", "ref_price": 4200},
    {"code": "FAC-AC-MAINT","name": "AC preventive maintenance contract, annual",                "category": "facilities", "gl": "6330", "ref_price": 18000},
    {"code": "FAC-CLEAN",   "name": "Office cleaning service, monthly",                          "category": "facilities", "gl": "6330", "ref_price": 9500},
    {"code": "FAC-WATER",   "name": "Water dispenser (hot and cold)",                            "category": "facilities", "gl": "6330", "ref_price": 750},
    {"code": "FAC-COFFEE-M","name": "Office coffee machine",                                     "category": "facilities", "gl": "6330", "ref_price": 2900},
    {"code": "FAC-FIRE-EXT","name": "Fire extinguisher 6kg, with annual inspection",             "category": "facilities", "gl": "6330", "ref_price": 260},
    {"code": "FAC-FIRSTAID","name": "First-aid kit, wall mounted",                               "category": "facilities", "gl": "6330", "ref_price": 180},
    # HR
    {"code": "HR-TRAIN-DAY","name": "Instructor-led training course, per person",                "category": "training", "gl": "6210", "ref_price": 3500},
    {"code": "HR-JOBBOARD", "name": "Job board subscription, annual",                            "category": "training", "gl": "6220", "ref_price": 15000},
    # Marketing
    {"code": "MKT-BIZCARD", "name": "Business cards, box of 500",                                "category": "printing", "gl": "6420", "ref_price": 90},
    {"code": "MKT-ROLLUP",  "name": "Roll-up banner with stand",                                 "category": "printing", "gl": "6420", "ref_price": 350},
    {"code": "MKT-BROCHURE","name": "Brochure printing, per 1,000",                              "category": "printing", "gl": "6420", "ref_price": 1800},
    {"code": "MKT-BOOTH",   "name": "Exhibition booth design and build (3x6m)",                  "category": "events",   "gl": "6410", "ref_price": 45000},
    # Mobile (STC framework agreement FA-STC-2026: no RFQ, call-off orders only)
    {"code": "MOB-IPH-PRO", "name": "iPhone Pro (company device, managers)",                     "category": "telecom", "gl": "6150", "ref_price": 5200, "framework": "FA-STC-2026", "sole_source_vendor": "V-STC"},
    {"code": "MOB-IPH",     "name": "iPhone (company device, staff)",                            "category": "telecom", "gl": "6150", "ref_price": 3700, "framework": "FA-STC-2026", "sole_source_vendor": "V-STC"},
    {"code": "PKG-MGR",     "name": "STC Business Unlimited + unlimited international roaming, per month", "category": "telecom", "gl": "6150", "ref_price": 450, "framework": "FA-STC-2026", "sole_source_vendor": "V-STC", "recurring": "monthly"},
    {"code": "PKG-STAFF",   "name": "STC Business Unlimited (no unlimited roaming), per month",  "category": "telecom", "gl": "6150", "ref_price": 300, "framework": "FA-STC-2026", "sole_source_vendor": "V-STC", "recurring": "monthly"},
    # Market data (Finance)
    {"code": "MD-BBG-TERM", "name": "Bloomberg Terminal subscription, annual, per user",      "category": "market_data", "gl": "6510", "ref_price": 105000, "sole_source_vendor": "V-BBG", "per_user": True},
    {"code": "LIC-SFDC",    "name": "Salesforce Sales Cloud, annual, per user",                  "category": "software", "gl": "6120", "ref_price": 6200, "per_user": True},
    {"code": "SAP-S4-MAINT","name": "SAP S/4HANA annual maintenance & support",                  "category": "software", "gl": "6140", "ref_price": 185000, "sole_source_vendor": "V-SAP"},
]

VENDORS = [
    {"id": "V-ZAW", "name": "Zawaya Tech Solutions", "categories": ["hardware", "network"],  "rating": 4.4},
    {"id": "V-MAD", "name": "Mada'in Systems",       "categories": ["hardware", "software"], "rating": 3.9},
    {"id": "V-BRQ", "name": "Bariq IT Supplies",     "categories": ["hardware"],             "rating": 4.1},
    {"id": "V-NUK", "name": "Nukhba Networks",       "categories": ["network"],              "rating": 4.6},
    {"id": "V-SDM", "name": "Sadeem Digital",        "categories": ["software", "network"],  "rating": 4.2},
    {"id": "V-FNR", "name": "Fanar Office Solutions","categories": ["hardware"],             "rating": 3.7},
    {"id": "V-RKN", "name": "Rukn Office Furniture", "categories": ["furniture"],           "rating": 4.3},
    {"id": "V-DWN", "name": "Diwan Interiors",       "categories": ["furniture"],             "rating": 4.0},
    {"id": "V-MKT", "name": "Maktabi Supplies",      "categories": ["office_supplies", "furniture"], "rating": 3.8},
    {"id": "V-WRQ", "name": "Waraq Stationery",      "categories": ["office_supplies"],       "rating": 4.1},
    {"id": "V-NDM", "name": "Nadeem Facility Services", "categories": ["facilities"],         "rating": 4.2},
    {"id": "V-BRD", "name": "Barid Cooling",         "categories": ["facilities"],            "rating": 4.0},
    {"id": "V-MHR", "name": "Mihrab Training Academy", "categories": ["training"],            "rating": 4.4},
    {"id": "V-ITQ", "name": "Itqan Learning",        "categories": ["training"],              "rating": 3.9},
    {"id": "V-LMS", "name": "Lamsa Printing",        "categories": ["printing", "events"],    "rating": 4.2},
    {"id": "V-MSR", "name": "Masarat Events",        "categories": ["events", "printing"],    "rating": 4.0},
    {"id": "V-STC", "name": "STC (stc business)",    "categories": ["telecom"],               "rating": 4.3,
     "framework_agreement": {"id": "FA-STC-2026", "valid_until": "2027-06-30", "scope": "Corporate mobile lines and devices"}},
    {"id": "V-BBG", "name": "Bloomberg (direct)",    "categories": ["market_data"],           "rating": 4.6},
    {"id": "V-SAP", "name": "SAP (OEM, direct)",     "categories": ["sap"],                  "rating": 4.5},
]

# Renewals the agent watches. days_to_expiry is relative to the demo start.
RENEWALS = [
    {"id": "RN-01", "item_code": "LIC-ADOBE-CC", "description": "Adobe Creative Cloud - design & marketing team",
     "qty": 12, "department": "IT", "current_vendor": "V-SDM", "days_to_expiry": 21, "last_unit_price": 3100, "renewal_quote_unit_price": 3250},
    {"id": "RN-02", "item_code": "SAP-S4-MAINT", "description": "SAP S/4HANA maintenance (ERP)",
     "qty": 1, "department": "IT", "current_vendor": "V-SAP", "days_to_expiry": 75, "last_unit_price": 185000, "renewal_quote_unit_price": 228000},
    {"id": "RN-03", "item_code": "LIC-M365-E3", "description": "Microsoft 365 E3 - all staff",
     "qty": 140, "department": "IT", "current_vendor": "V-MAD", "days_to_expiry": 160, "last_unit_price": 1450, "renewal_quote_unit_price": 1450},
]

# Employee directory (from HR). status: active | joining | left ; days: since joining/leaving (+ = future start)
EMPLOYEES = [
    {"id": "E-1001", "name": "Khalid Al-Zahrani",  "title": "Head of IT",          "department": "IT",        "grade": "manager", "status": "active"},
    {"id": "E-1002", "name": "Omar Al-Qahtani",    "title": "IT Analyst",          "department": "IT",        "grade": "staff",   "status": "active"},
    {"id": "E-1003", "name": "Sara Al-Otaibi",     "title": "Accountant",          "department": "Finance",   "grade": "staff",   "status": "active"},
    {"id": "E-1004", "name": "Nawaf Al-Shehri",    "title": "Head of Finance",     "department": "Finance",   "grade": "manager", "status": "active"},
    {"id": "E-1005", "name": "Faisal Al-Harbi",    "title": "Head of Administration", "department": "Admin",  "grade": "manager", "status": "active"},
    {"id": "E-1006", "name": "Lama Al-Subaie",     "title": "Head of HR",          "department": "HR",        "grade": "manager", "status": "active"},
    {"id": "E-1007", "name": "Yousef Al-Shammari", "title": "Head of Marketing",   "department": "Marketing", "grade": "manager", "status": "active"},
    {"id": "E-1008", "name": "Reem Al-Dosari",     "title": "Chief Financial Officer", "department": "Finance", "grade": "manager", "status": "active"},
    {"id": "E-1009", "name": "Rakan Al-Shahrani",  "title": "Marketing Specialist", "department": "Marketing", "grade": "staff",  "status": "active"},
    {"id": "E-1010", "name": "Abeer Al-Juhani",    "title": "Marketing Manager",   "department": "Marketing", "grade": "manager", "status": "joining", "days": 3},
    {"id": "E-1011", "name": "Saad Al-Malki",      "title": "Software Developer",  "department": "IT",        "grade": "staff",   "status": "joining", "days": 5},
    {"id": "E-1012", "name": "Ali Al-Ghamdi",      "title": "IT Intern",           "department": "IT",        "grade": "intern",  "status": "active"},
    {"id": "E-1013", "name": "Bandar Al-Rashid",   "title": "Sales Executive",     "department": "Marketing", "grade": "staff",   "status": "left", "days": 124},
    {"id": "E-1014", "name": "Hessa Al-Qurashi",   "title": "Finance Manager",     "department": "Finance",   "grade": "manager", "status": "left", "days": 71},
]

# Active STC lines today (numbers are fictional). Two belong to people who already left.
MOBILE_LINES = [
    {"number": "0550 114 201", "employee_id": "E-1001", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
    {"number": "0550 114 202", "employee_id": "E-1003", "package": "PKG-STAFF", "device": "MOB-IPH",     "monthly": 300},
    {"number": "0550 114 203", "employee_id": "E-1004", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
    {"number": "0550 114 204", "employee_id": "E-1005", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
    {"number": "0550 114 205", "employee_id": "E-1006", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
    {"number": "0550 114 206", "employee_id": "E-1007", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
    {"number": "0550 114 207", "employee_id": "E-1008", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
    {"number": "0550 114 208", "employee_id": "E-1009", "package": "PKG-STAFF", "device": "MOB-IPH",     "monthly": 300},
    {"number": "0550 114 209", "employee_id": "E-1013", "package": "PKG-STAFF", "device": "MOB-IPH",     "monthly": 300},
    {"number": "0550 114 210", "employee_id": "E-1014", "package": "PKG-MGR",   "device": "MOB-IPH-PRO", "monthly": 450},
]

# Historical (closed) purchases this year - used by the audit view.
# Some contain deliberate compliance problems for the auditor to find.
HISTORY = [
    # id, days_ago, title, gl, total, method, quotes, approvers(list of roles), docs(list), vendor
    ("PR-2026-0101", 240, "Replacement monitors for finance team",    "6110", 15000,  "Low Value",  1, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "invoice", "delivery_note"], "V-BRQ"),
    ("PR-2026-0114", 210, "Firewall annual subscription",            "6140", 38500,  "RFQ",        3, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "quote", "quote", "tech_eval", "invoice"], "V-NUK"),
    ("PR-2026-0127", 190, "Meeting room AV upgrade",                 "6110", 55200,  "RFQ",        1, ["it_head", "accountant", "cfo"],                  ["pr_form", "quote", "invoice"], "V-ZAW"),            # only 1 quote for RFQ tier
    ("PR-2026-0133", 170, "Core switch replacement",                 "6130", 118000, "RFQ",        3, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "quote", "quote", "tech_eval", "invoice"], "V-NUK"),  # needed CFO
    ("PR-2026-0148", 150, "Microsoft 365 true-up",                   "6120", 29000,  "Low Value",  1, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "invoice"], "V-MAD"),            # method wrong (>20k)
    ("PR-2026-0152", 130, "Laptops for new hires (batch 1)",         "6110", 39000,  "RFQ",        3, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "quote", "quote", "tech_eval", "invoice", "delivery_note"], "V-ZAW"),
    ("PR-2026-0166", 110, "Backup storage expansion",                "6130", 74000,  "RFQ",        3, ["it_head", "accountant", "cfo"],                  ["pr_form", "quote", "quote", "quote", "tech_eval"], "V-SDM"),  # missing invoice
    ("PR-2026-0171",  95, "SAP S/4HANA maintenance 2026",            "6140", 179000, "Sole Source",1, ["it_head", "accountant", "cfo"],                  ["pr_form", "quote", "justification", "invoice"], "V-SAP"),
    ("PR-2026-0185",  70, "Printers for branch office",              "6110", 29000,  "RFQ",        3, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "quote", "quote", "invoice"], "V-FNR"),
    ("PR-2026-0193",  45, "Wi-Fi controller replacement (branch)",   "6130", 17900,  "Low Value",  1, ["it_head", "accountant", "finance_head"],         ["pr_form", "quote", "tech_eval", "invoice"], "V-NUK"),
    ("PR-2026-0108", 225, "Desks and chairs for new HR office",     "6320", 31800,  "RFQ",        3, ["admin_head", "accountant", "finance_head"],      ["pr_form", "quote", "quote", "quote", "invoice", "delivery_note"], "V-RKN", "Admin"),
    ("PR-2026-0139", 160, "AC maintenance contract 2026",            "6330", 18000,  "Low Value",  1, ["admin_head", "accountant", "finance_head"],      ["pr_form", "quote", "invoice"], "V-BRD", "Admin"),
    ("PR-2026-0177",  85, "LEAP exhibition booth",                   "6410", 46500,  "RFQ",        2, ["marketing_head", "accountant", "cfo"],          ["pr_form", "quote", "quote", "invoice"], "V-MSR", "Marketing"),  # 2 quotes only
    ("PR-2026-0204",  25, "Data center UPS batteries",               "6140", 212000, "RFQ",        3, ["it_head", "accountant", "cfo"],                  ["pr_form", "quote", "quote", "quote", "invoice"], "V-ZAW"),  # needed bidding + CEO
]


def write_budget_xlsx(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget 2026"
    headers = ["Department", "G/L Account", "Account Name", "Annual Budget (SAR)", "Spent YTD (SAR)", "Remaining (SAR)"]
    ws.append([f"{COMPANY['name']} - Departmental Budget FY2026"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(headers)
    for c in ws[3]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E46")
        c.alignment = Alignment(horizontal="center")
    for i, (dept, gl, name, budget, spent) in enumerate(GL_ACCOUNTS, start=4):
        ws.append([dept, gl, name, budget, spent, f"=D{i}-E{i}"])
        for col in "DEF":
            ws[f"{col}{i}"].number_format = "#,##0"
    for col, w in zip("ABCDEF", [12, 12, 40, 20, 18, 18]):
        ws.column_dimensions[col].width = w
    wb.save(path)


def main():
    (HERE / "company.json").write_text(json.dumps({
        "company": COMPANY, "people": PEOPLE, "policy": POLICY,
        "catalog": CATALOG, "vendors": VENDORS, "renewals": RENEWALS,
        "employees": EMPLOYEES, "mobile_lines": MOBILE_LINES,
        "history": [dict(zip(["id", "days_ago", "title", "gl", "total", "method", "quotes",
                              "approvers", "docs", "vendor", "department"], h)) for h in HISTORY],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    write_budget_xlsx(HERE / "budget.xlsx")
    print("Wrote data/company.json and data/budget.xlsx")


if __name__ == "__main__":
    main()
