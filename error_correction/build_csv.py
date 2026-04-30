import os
import csv

# -----------------------------------
# CONFIG
# -----------------------------------
OUTPUT_DIR = "code_rag/knowledge_base"
CSV_FILE = os.path.join(OUTPUT_DIR, "metadata.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------
# EXTRACT KEYWORD FROM FILE CONTENT
# -----------------------------------
def extract_keyword(text, filename):
    """
    Looks for:
    [Keyword]: something

    Falls back to filename prefix.
    """
    for line in text.splitlines():
        if line.strip().lower().startswith("[keyword]:"):
            keyword = line.split(":", 1)[1].strip()
            if keyword:
                return keyword

    # fallback from filename
    base = os.path.splitext(filename)[0]
    return base.split("_")[0]


# -----------------------------------
# BUILD CSV FROM EXISTING TXT FILES
# -----------------------------------
def build_csv_from_existing_entries():
    rows = []

    files = sorted(
        f for f in os.listdir(OUTPUT_DIR)
        if f.endswith(".txt")
    )

    counter = 0

    for filename in files:
        filepath = os.path.join(OUTPUT_DIR, filename)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            keyword = extract_keyword(content, filename)

            rows.append({
                "keyword": keyword,
                "content": content,
                "filename": filename,
                "filepath": filepath
            })

            counter += 1

        except Exception as e:
            print(f"Skipping {filename}: {e}")

    # -----------------------------------
    # WRITE CSV
    # -----------------------------------
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["keyword", "content", "filename", "filepath"],
            quoting=csv.QUOTE_ALL
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {counter} entries")
    print(f"CSV file -> {CSV_FILE}")


# -----------------------------------
# MAIN
# -----------------------------------
if __name__ == "__main__":
    build_csv_from_existing_entries()