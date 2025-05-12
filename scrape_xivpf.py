import requests
import re
import json
import os
import pandas as pd
from datetime import datetime

EXPORT_DIR = "exports"
os.makedirs(EXPORT_DIR, exist_ok=True)

URL = "https://xivpf.com/"
response = requests.get(URL)
html = response.text

listings = []

listing_pattern = re.compile(
    r'<div\s+class="listing"[^>]*?data-id="(\d+)"[^>]*?data-centre="([^"]+)"[^>]*?data-pf-category="([^"]+)"[\s\S]*?<\/div>\s*<\/div>',
    re.MULTILINE
)

# ⏰ Round time to previous 15-minute block
now = datetime.utcnow()
rounded_time = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
timestamp_str = rounded_time.strftime("%Y-%m-%d %H:%M:%S")

for match in listing_pattern.finditer(html):
    block = match.group(0)
    listing_id = match.group(1)
    data_centre = match.group(2)
    category = match.group(3)

    def decode(text):
        return re.sub(r'&#x27;', "'", text or "").strip()

    duty_match = re.search(r'<div class="duty[^>]*>(.*?)<\/div>', block)
    duty = decode(duty_match.group(1)) if duty_match else ""

    party = []
    for m in re.finditer(r'<div class="slot(.*?)"[^>]*title="([^"]*)"', block):
        classes, title = m.groups()
        role = "unknown"
        if "tank" in classes: role = "tank"
        elif "healer" in classes: role = "healer"
        elif "dps" in classes: role = "dps"

        party.append({
            "filled": "filled" in classes,
            "role": role,
            "job": title
        })

    # Tag detection
    tags = {
        "[Practice]": 0,
        "[Loot]": 0,
        "[Duty Completion]": 0,
        "[One Player per Job]": 0
    }
    for tag in tags:
        if tag in block:
            tags[tag] = 1

    listings.append({
        "Timestamp": timestamp_str,
        "ID": listing_id,
        "Data Centre": data_centre,
        "Category": category,
        "Duty": duty,
        "Party (JSON)": json.dumps(party),
        "[Practice]": tags["[Practice]"],
        "[Loot]": tags["[Loot]"],
        "[Duty Completion]": tags["[Duty Completion]"],
        "[One Player per Job]": tags["[One Player per Job]"]
    })

# Save to CSV
if listings:
    df = pd.DataFrame(listings)
    filename = os.path.join(EXPORT_DIR, f"{rounded_time.strftime('%Y-%m-%d')}.csv")
    if os.path.exists(filename):
        df_existing = pd.read_csv(filename)
        df = pd.concat([df_existing, df], ignore_index=True).drop_duplicates(subset=["Timestamp", "ID"])
    df.to_csv(filename, index=False)
    print(f"✅ Saved {len(df)} listings to {filename}")
else:
    print("⚠️ No listings found.")
