import os
import io
import sys
import requests
import tempfile
import shutil
import token
from pathlib import Path
from git import Repo
from tqdm import tqdm
import re
import tokenize

CONFIG_DIR = Path(__file__).resolve().parents[1]
if str(CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(CONFIG_DIR))

from config import github_token

# ----------------------------
# CONFIG
# ----------------------------
GITHUB_TOKEN = github_token
SEARCH_QUERY = 'pyrtl'
MAX_REPOS = 100
MAX_FILES_PER_REPO = 50
OUTPUT_DIR = "knowledge_base_pyrtl"

os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "pyrtl-rag-builder"
}

# ----------------------------
# STEP 1: SEARCH REPOS
# ----------------------------
def search_repos(query, max_repos):
    url = "https://api.github.com/search/repositories"
    params = {"q": query, "per_page": max_repos}

    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()

    return [item["clone_url"] for item in data["items"]]



# ----------------------------
# STEP 2: CLONE
# ----------------------------
def clone_repo(repo_url):
    temp_dir = tempfile.mkdtemp()
    try:
        Repo.clone_from(repo_url, temp_dir, depth=1)
        return temp_dir
    except:
        shutil.rmtree(temp_dir)
        return None



# ----------------------------
# STEP 3: FIND PYRTL FILES
# ----------------------------
def find_pyrtl_files(repo_path):
    results = []

    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    content = open(path).read()
                    if "import pyrtl" in content:
                        results.append(path)
                except:
                    continue
    return results



# ----------------------------
# STEP 4: PARSE PYRTL
# ----------------------------
def format_signal_description(width, name, direction):
    width = int(width)
    if direction == "input":
        if width == 1:
            return f"{name}: A single-bit input signal that provides a control value for the circuit logic."
        return f"{name}[{width - 1}:0]: A {width}-bit input vector that provides the data for the circuit logic."

    if width == 1:
        return f"{name}: A single-bit output signal that carries the result of the circuit logic."
    return f"{name}[{width - 1}:0]: A {width}-bit output vector that carries the result of the circuit logic."


def extract_signals(code):
    inputs = re.findall(r'Input\((\d+),\s*[\'"](\w+)[\'"]\)', code)
    outputs = re.findall(r'Output\((\d+),\s*[\'"](\w+)[\'"]\)', code)

    input_desc = "\n".join(
        [format_signal_description(width, name, "input") for width, name in inputs]
    )

    output_desc = "\n".join(
        [format_signal_description(width, name, "output") for width, name in outputs]
    )

    return input_desc, output_desc


def strip_comments(code):
    cleaned_tokens = []
    previous_type = token.INDENT

    for current_token in tokenize.generate_tokens(io.StringIO(code).readline):
        if current_token.type == tokenize.COMMENT:
            continue

        is_block_comment = (
            current_token.type == token.STRING
            and previous_type in {token.INDENT, token.NEWLINE, tokenize.NL}
        )
        if is_block_comment:
            previous_type = current_token.type
            continue

        cleaned_tokens.append(current_token)
        previous_type = current_token.type

    cleaned_code = tokenize.untokenize(cleaned_tokens)
    cleaned_lines = [
        line.rstrip()
        for line in cleaned_code.splitlines()
        if line.strip() != "\\"
    ]
    return "\n".join(cleaned_lines).strip()


def classify_design(code):
    if "Register" in code or "pyrtl.Register" in code:
        return "Sequential Logic"
    return "Combinational Logic"



# ----------------------------
# STEP 5: BUILD STRUCTURED ENTRY
# ----------------------------
def build_structured_text(code, idx):
    inputs, outputs = extract_signals(code)
    category = classify_design(code)
    design_detail = strip_comments(code)

    keyword = f"pyrtl_{idx}"

    return f"""[Keyword]: {keyword}

[Design Category]: {category}

[Design Function Description]:
This PyRTL circuit implements hardware logic extracted from a GitHub repository. The logic describes how inputs are transformed into outputs using PyRTL primitives.

[Input Signal Description]:
{inputs if inputs else "Not explicitly detected"}

[Output Signal Description]:
{outputs if outputs else "Not explicitly detected"}

[Design Detail]:
{design_detail}
"""



# ----------------------------
# STEP 6: SAVE FILE
# ----------------------------
def save_entry(text, idx):
    filename = os.path.join(OUTPUT_DIR, f"entry_{idx}.txt")
    with open(filename, "w") as f:
        f.write(text)



# ----------------------------
# MAIN
# ----------------------------
def build_rag_kb():
    repos = search_repos(SEARCH_QUERY, MAX_REPOS)

    counter = 0

    for repo_url in tqdm(repos, desc="Repos"):
        repo_path = clone_repo(repo_url)
        if not repo_path:
            continue

        try:
            files = find_pyrtl_files(repo_path)[:MAX_FILES_PER_REPO]

            for f in files:
                try:
                    code = open(f).read().strip()

                    structured = build_structured_text(code, counter)

                    save_entry(structured, counter)
                    counter += 1

                except:
                    continue

        finally:
            shutil.rmtree(repo_path)

    print(f"Saved {counter} files to {OUTPUT_DIR}")



if __name__ == "__main__":
    build_rag_kb()
