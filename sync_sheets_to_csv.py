import os
import pandas as pd
import gspread
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

EXPORT_DIR = "exports"
SHEET_NAME = "PFTracker"

def round_to_quarter(dt):
    return dt - timedelta(minutes=dt.minute % 15,
                          seconds=dt.second,
                          microseconds=dt.microsecond)

def download_sheet(sheet, title):
    df = pd.DataFrame(sheet.get_all_records())
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df = df.drop_duplicates(subset=["ID", "Timestamp"])
    path = os.path.join(EXPORT_DIR, f"{title}.csv.gz")
    df.to_csv(path, index=False, compression="gzip")
    print(f"✅ Saved {title} to {path}")

def main():
    # Auth
    creds = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ])
    client = gspread.authorize(creds)

    spreadsheet = client.open(SHEET_NAME)
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    os.makedirs(EXPORT_DIR, exist_ok=True)

    for date in [yesterday, today]:
        try:
            sheet = spreadsheet.worksheet(str(date))
            download_sheet(sheet, str(date))
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️ Sheet for {date} not found — skipping.")

if __name__ == "__main__":
    main()
