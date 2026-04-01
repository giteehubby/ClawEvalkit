---
id: 01_Productivity_Flow_task_4_2022_conference_papers
name: Compile Kaiming He 2022 Conference Papers
category: 01_Productivity_Flow
timeout_seconds: 1200
---

## Prompt
Please compile all papers authored or co-authored by **Kaiming He** that were published at **academic conferences in 2022** and save them to:

- `/tmp_workspace/results/2022.tsv`

Your goal is to produce a clean, complete TSV file containing one row per paper.

Use the following fields in this exact order:

1. **Conference**: the conference name, using its standard abbreviation (for example: `CVPR`, `ICCV`, `ICML`, `NeurIPS`)
2. **Title**: the paper title, exactly as listed on the official conference website
3. **Authors**: the full author list in official order, separated by commas, with each name written in default order (`given name` first, `family name` last)
4. **Abstract**: the paper abstract
5. **Author links**: the personal homepage link for each author of the paper, if available, listed in author order using the format `"Author Name: link"`, separated by commas; if no reliable personal homepage can be found for an author, use `"Author Name: not found"`
6. **GitHub commit id**: inspect the latest available paper version and determine whether the paper text includes a GitHub or repository link for the paper's official code release; if so, resolve that repository and record the most recent commit id of the paper project as of 2026-03-19; if not, write `not found`

Scope and inclusion rules:

- Include only papers whose official conference publication year is **2022**
- Use the **official conference website or official conference proceedings page** as the source of truth for `Conference`, `Title`, `Authors`, and `Abstract`
- Include only papers that are part of the main conference proceedings
- Exclude workshops, tutorials, challenge reports, demos, journal-only versions, arXiv-only preprints, theses, and blog posts

For `Author links`:

- Preserve the same author order as the `Authors` field
- Prefer a personal academic homepage or personal website over a general lab page, Google Scholar profile, DBLP page, ORCID page, or LinkedIn page
- If multiple plausible personal homepages exist, choose the most direct stable homepage
- If no reliable personal homepage can be found, write `not found`

For `GitHub commit id`:

- Determine this field using the latest available paper version
- You may output either the full commit hash or an unambiguous short commit hash
- If the latest paper version does not include such a repository link, write `not found`

### Output Requirements

You must create the following outputs under `/tmp_workspace/results/`:

- `2022.tsv`
- one or more paper source `.tex` files

Do not create any other files or directories under `results/`.

#### TSV Format

The TSV file must:

- be UTF-8 encoded
- contain exactly one header row
- use tab (`\t`) as the delimiter
- use exactly the following header:

```text
Conference  Title   Authors Abstract    Author links    GitHub commit id
```

- contain exactly one row per paper
- not contain duplicate papers
- be sorted by `Conference` ascending, then by `Title` ascending
- not contain embedded newlines inside any field
- not contain markdown, comments, explanations, or extra prose

Field formatting rules:

- `Conference` should be a standard conference abbreviation
- `Title` must match the official conference title exactly
- `Authors` must be a single line like `Author A, Author B, Author C`
- `Abstract` must be a single line with internal whitespace normalized if needed
- `Author links` must be a single line like `Author A: https://example.com, Author B: not found`
- Every author listed in `Authors` must appear exactly once in `Author links`, in the same order
- `GitHub commit id` must be either `not found` or a Git commit hash (short or full hexadecimal form)

#### arXiv TeX Source Files

For every paper listed in `2022.tsv`, also download the corresponding arXiv source and save the **main paper `.tex` file** for every available arXiv version.

Rules:

- Save the `.tex` files directly under `/tmp_workspace/results/`
- Keep only the final required `.tex` files; do not leave downloaded archives, extracted folders, figures, `.sty`, `.bib`, or other auxiliary files
- If a paper has exactly one arXiv version, name the file `{title}.tex`
- If a paper has multiple arXiv versions, save only the versions that actually exist on arXiv and name them `{title}_v1.tex`, `{title}_v2.tex` ... 
- `{title}` means the exact paper title from the TSV `Title` field
- If the arXiv source package contains multiple `.tex` files, identify the primary top-level paper `.tex` file and save only that file's content
- Do not add explanations, comments, or extra text to the saved `.tex` files

## Expected Behavior

The agent should:

1. Identify all 2022 conference papers authored or co-authored by Kaiming He
2. Verify each paper on the official conference website or official proceedings page
3. Extract the official conference abbreviation, exact title, official author list, and abstract
4. Find a reliable personal homepage for each author when possible
5. Inspect the latest available paper version to determine whether the paper text explicitly contains a GitHub or repository link, and if so record the latest commit id for that repository
6. Locate the arXiv source package for each paper and recover the main `.tex` source file for every available arXiv version
7. Save a complete, deduplicated, correctly sorted TSV file plus the required `.tex` files under `/tmp_workspace/results/`

## Grading Criteria

- [ ] `results/2022.tsv` exists
- [ ] The TSV header is exactly correct
- [ ] The TSV rows are structurally valid and parseable
- [ ] The predicted paper set has high recall and precision against the hidden ground truth
- [ ] Rows are correctly sorted by conference and title
- [ ] Conference abbreviations are correct
- [ ] Titles match the official conference titles
- [ ] Author lists match the official author order
- [ ] Abstracts match the official conference abstracts after normalization
- [ ] Author-link formatting is valid
- [ ] Author homepage links are correct when compared against the hidden ground-truth TSV
- [ ] GitHub commit ids are structurally valid
- [ ] GitHub commit ids are correct when compared against the hidden ground-truth TSV
- [ ] The expected arXiv `.tex` files are created with the correct filenames
- [ ] The recovered `.tex` contents match the hidden ground-truth source files after normalization
- [ ] No extra files are created under `results/`

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the Kaiming He 2022 conference paper compilation task.

    Notes:
      - Titles are treated as unique paper identifiers in the hidden reference.
      - For homepage matching, http/https differences are ignored after URL normalization.
      - For author name matching, accented characters (e.g. á) and ASCII equivalents (e.g. a) are treated as equivalent.
    """
    from pathlib import Path
    from urllib.parse import urlsplit, urlunsplit
    import csv
    import io
    import re
    import unicodedata

    ALL_CRITERIA = [
        "output_exists",
        "tsv_header_valid",
        "rows_parseable",
        "paper_recall",
        "paper_precision",
        "paper_f1",
        "row_sorting_correct",
        "conference_accuracy",
        "authors_accuracy",
        "abstract_accuracy",
        "author_links_format_valid",
        "author_links_accuracy",
        "github_commit_id_format_valid",
        "github_commit_id_accuracy",
        "tex_files_created",
        "tex_exact_match_ratio",
        "output_dir_clean",
        "hard_constraint_pass",
        "overall_score",
    ]

    ZERO = {k: 0.0 for k in ALL_CRITERIA}
    scores = dict(ZERO)
    
    workspace = Path("/tmp_workspace")
    gt_dir = workspace / "gt"
    pred_path = workspace / "results" / "2022.tsv"
    pred_dir = workspace / "results"
    gt_path = gt_dir / "gt.tsv"
    gt_tex_dir = gt_dir / "gt_tex"
    if not (gt_tex_dir.exists() and gt_tex_dir.is_dir()):
        gt_tex_dir = gt_dir

    if not gt_path.exists():
        return ZERO

    def normalize_text(text: str) -> str:
        text = unicodedata.normalize("NFKC", str(text))
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\n", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def normalize_casefold_text(text: str) -> str:
        return normalize_text(text).casefold()

    def normalize_author_name(name: str) -> str:
        """Treat accented chars (e.g. á) and ASCII equivalents (e.g. a) as equivalent."""
        s = normalize_text(name)
        nfd = unicodedata.normalize("NFD", s)
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

    def normalize_conference(text: str) -> str:
        text = normalize_casefold_text(text)
        text = re.sub(r"[^a-z0-9]+", "", text)
        return text

    def normalize_url(text: str) -> str:
        text = normalize_text(text)
        if normalize_casefold_text(text) == "not found":
            return "not found"
        try:
            parsed = urlsplit(text)
            netloc = parsed.netloc.lower()
            path = re.sub(r"/+", "/", parsed.path or "/")
            if path != "/":
                path = path.rstrip("/")
            else:
                path = "/"
            # Ignore http/https difference when comparing homepages.
            return urlunsplit(("", netloc, path, "", ""))
        except Exception:
            return re.sub(r"^https?://", "", text.rstrip("/"), flags=re.IGNORECASE)

    def normalize_commit_id(text: str) -> str:
        text = normalize_casefold_text(text)
        if text == "not found":
            return "not found"
        text = re.sub(r"\s+", "", text)
        return text

    def is_valid_commit_id(text: str) -> bool:
        value = normalize_commit_id(text)
        return value == "not found" or re.fullmatch(r"[0-9a-f]{7,40}", value) is not None

    def commit_id_matches(pred: str, gt: str) -> bool:
        pred_norm = normalize_commit_id(pred)
        gt_norm = normalize_commit_id(gt)
        if pred_norm == "not found" or gt_norm == "not found":
            return pred_norm == gt_norm
        return pred_norm.startswith(gt_norm) or gt_norm.startswith(pred_norm)

    def parse_author_list(field: str):
        names = [normalize_text(x) for x in str(field).split(",")]
        return [x for x in names if x]

    def parse_author_links(field: str):
        items = []
        chunks = [normalize_text(x) for x in str(field).split(",")]
        chunks = [x for x in chunks if x]
        for chunk in chunks:
            if ": " not in chunk:
                return None
            author, value = chunk.split(": ", 1)
            author = normalize_text(author)
            value = normalize_text(value)
            if not author or not value:
                return None
            items.append((author, value))
        return items

    def parse_tex_filename(filename: str):
        if not filename.endswith(".tex"):
            return None, None
        stem = filename[:-4]
        m = re.match(r"^(.*)_v(\d+)$", stem)
        if m:
            return m.group(1), int(m.group(2))
        return stem, None

    def normalize_tex(text: str) -> str:
        text = str(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        return "\n".join(lines).strip()

    def cleanliness_score(directory: Path, allowed_names: set[str]) -> float:
        """Score agent output directory cleanliness."""
        if not directory.exists() or not directory.is_dir():
            return 0.0
        agent_output = [p.name for p in directory.iterdir()]
        extras = [n for n in agent_output if n not in allowed_names]
        return round(max(0.0, 1.0 - 0.1 * len(extras)), 4)

    scores["output_exists"] = 1.0 if pred_path.exists() and pred_path.is_file() else 0.0

    if not gt_path.exists() or not gt_path.is_file() or not gt_dir.exists():
        return scores

    expected_header = ["Conference", "Title", "Authors", "Abstract", "Author links", "GitHub commit id"]
    try:
        gt_text = gt_path.read_text(encoding="utf-8")
        gt_reader = csv.DictReader(io.StringIO(gt_text), delimiter="\t")
        gt_fieldnames = gt_reader.fieldnames or []
    except Exception:
        return ZERO

    if gt_fieldnames != expected_header:
        return ZERO

    gt_by_title = {}
    total_gt_authors = 0
    try:
        gt_reader = csv.DictReader(io.StringIO(gt_text), delimiter="\t")
        for row in gt_reader:
            if not isinstance(row, dict):
                return ZERO
            if set(row.keys()) != set(expected_header):
                return ZERO

            conference = row.get("Conference", "")
            title = row.get("Title", "")
            authors_field = row.get("Authors", "")
            abstract = row.get("Abstract", "")
            author_links_field = row.get("Author links", "")
            github_commit_id = row.get("GitHub commit id", "")

            if not all(normalize_text(x) for x in [conference, title, authors_field, abstract, author_links_field, github_commit_id]):
                return ZERO

            authors = parse_author_list(authors_field)
            links = parse_author_links(author_links_field)
            if len(authors) == 0 or links is None or len(links) != len(authors):
                return ZERO
            if not is_valid_commit_id(github_commit_id):
                return ZERO

            link_authors = [normalize_author_name(a) for a, _ in links]
            if link_authors != [normalize_author_name(a) for a in authors]:
                return ZERO

            title_key = normalize_casefold_text(title)
            if not title_key or title_key in gt_by_title:
                return ZERO

            gt_by_title[title_key] = {
                "conference": conference,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "author_links": links,
                "github_commit_id": github_commit_id,
            }
            total_gt_authors += len(authors)
    except Exception:
        return ZERO

    if len(gt_by_title) == 0:
        return ZERO

    gt_tex_files = {}
    gt_tex_names = set()
    try:
        for path in gt_tex_dir.iterdir():
            if not path.is_file() or path.suffix.lower() != ".tex":
                continue
            base_title, version = parse_tex_filename(path.name)
            if not base_title:
                return ZERO
            title_key = normalize_casefold_text(base_title)
            if title_key not in gt_by_title:
                return ZERO
            if path.name in gt_tex_files:
                return ZERO
            gt_tex_files[path.name] = {
                "title_key": title_key,
                "version": version,
                "content": normalize_tex(path.read_text(encoding="utf-8", errors="ignore")),
            }
            gt_tex_names.add(path.name)
    except Exception:
        return ZERO

    if len(gt_tex_files) == 0:
        return ZERO

    allowed_output_names = {"2022.tsv"} | gt_tex_names
    scores["output_dir_clean"] = cleanliness_score(pred_dir, allowed_output_names)

    if not pred_path.exists() or not pred_path.is_file():
        return scores

    try:
        raw_text = pred_path.read_text(encoding="utf-8")
    except Exception:
        return scores

    try:
        reader = csv.DictReader(io.StringIO(raw_text), delimiter="\t")
        fieldnames = reader.fieldnames or []
    except Exception:
        return scores

    scores["tsv_header_valid"] = 1.0 if fieldnames == expected_header else 0.0
    if scores["tsv_header_valid"] == 0.0:
        return scores

    pred_rows = []
    rows_parseable = True
    author_links_format_valid = True
    github_commit_id_format_valid = True
    duplicate_titles = False
    pred_by_title = {}

    try:
        reader = csv.DictReader(io.StringIO(raw_text), delimiter="\t")
        for row in reader:
            if not isinstance(row, dict):
                rows_parseable = False
                break

            if set(row.keys()) != set(expected_header):
                rows_parseable = False
                break

            conference = row.get("Conference", "")
            title = row.get("Title", "")
            authors_field = row.get("Authors", "")
            abstract = row.get("Abstract", "")
            author_links_field = row.get("Author links", "")
            github_commit_id = row.get("GitHub commit id", "")

            if not all(normalize_text(x) for x in [conference, title, authors_field, abstract, author_links_field, github_commit_id]):
                rows_parseable = False
                break

            authors = parse_author_list(authors_field)
            links = parse_author_links(author_links_field)
            if len(authors) == 0:
                rows_parseable = False
                break

            if links is None or len(links) != len(authors):
                author_links_format_valid = False
            else:
                link_authors = [normalize_author_name(a) for a, _ in links]
                if link_authors != [normalize_author_name(a) for a in authors]:
                    author_links_format_valid = False

            if not is_valid_commit_id(github_commit_id):
                github_commit_id_format_valid = False

            title_key = normalize_casefold_text(title)
            if title_key in pred_by_title:
                duplicate_titles = True
            pred_by_title[title_key] = {
                "conference": conference,
                "title": title,
                "authors_field": authors_field,
                "authors": authors,
                "abstract": abstract,
                "author_links_field": author_links_field,
                "author_links": links,
                "github_commit_id": github_commit_id,
            }
            pred_rows.append((conference, title))
    except Exception:
        rows_parseable = False

    scores["rows_parseable"] = 1.0 if rows_parseable else 0.0
    scores["author_links_format_valid"] = 1.0 if author_links_format_valid and rows_parseable else 0.0
    scores["github_commit_id_format_valid"] = 1.0 if github_commit_id_format_valid and rows_parseable else 0.0

    if scores["rows_parseable"] == 0.0:
        return scores

    gt_titles = set(gt_by_title.keys())
    pred_titles = set(pred_by_title.keys())
    matched_titles = gt_titles.intersection(pred_titles)

    recall = len(matched_titles) / len(gt_titles) if gt_titles else 0.0
    precision = len(matched_titles) / len(pred_titles) if pred_titles else 0.0
    f1 = (2 * recall * precision / (recall + precision)) if (recall + precision) > 0 else 0.0

    if duplicate_titles:
        precision = 0.0
        f1 = 0.0

    scores["paper_recall"] = round(recall, 4)
    scores["paper_precision"] = round(precision, 4)
    scores["paper_f1"] = round(f1, 4)

    created_tex = 0
    exact_tex = 0
    for tex_name, gt_tex in gt_tex_files.items():
        pred_tex_path = pred_dir / tex_name
        if pred_tex_path.exists() and pred_tex_path.is_file():
            created_tex += 1
            try:
                pred_tex = normalize_tex(pred_tex_path.read_text(encoding="utf-8", errors="ignore"))
                if pred_tex == gt_tex["content"]:
                    exact_tex += 1
            except Exception:
                pass

    total_gt_tex = len(gt_tex_files)
    scores["tex_files_created"] = round(created_tex / total_gt_tex, 4) if total_gt_tex else 0.0
    scores["tex_exact_match_ratio"] = round(exact_tex / total_gt_tex, 4) if total_gt_tex else 0.0

    sorted_rows = sorted(
        pred_rows,
        key=lambda x: (normalize_conference(x[0]), normalize_casefold_text(x[1])),
    )
    scores["row_sorting_correct"] = 1.0 if pred_rows == sorted_rows and not duplicate_titles else 0.0

    conference_correct = 0
    authors_correct = 0
    abstract_correct = 0
    author_links_correct = 0
    github_commit_id_correct = 0

    for title_key, gt in gt_by_title.items():
        pred = pred_by_title.get(title_key)
        if pred is None:
            continue

        if normalize_conference(pred["conference"]) == normalize_conference(gt["conference"]):
            conference_correct += 1

        gt_authors = [normalize_author_name(x) for x in gt["authors"]]
        pred_authors = [normalize_author_name(x) for x in pred["authors"]]
        if pred_authors == gt_authors:
            authors_correct += 1

        if normalize_casefold_text(pred["abstract"]) == normalize_casefold_text(gt["abstract"]):
            abstract_correct += 1

        gt_links = gt["author_links"]
        pred_links = pred["author_links"] or []
        if len(pred_links) == len(gt_links):
            for (pred_author, pred_value), (gt_author, gt_value) in zip(pred_links, gt_links):
                if normalize_author_name(pred_author) != normalize_author_name(gt_author):
                    continue
                if normalize_url(pred_value) == normalize_url(gt_value):
                    author_links_correct += 1

        if commit_id_matches(pred["github_commit_id"], gt["github_commit_id"]):
            github_commit_id_correct += 1

    total_gt = len(gt_by_title)
    scores["conference_accuracy"] = round(conference_correct / total_gt, 4) if total_gt else 0.0
    scores["authors_accuracy"] = round(authors_correct / total_gt, 4) if total_gt else 0.0
    scores["abstract_accuracy"] = round(abstract_correct / total_gt, 4) if total_gt else 0.0
    scores["author_links_accuracy"] = (
        round(author_links_correct / total_gt_authors, 4) if total_gt_authors else 0.0
    )
    scores["github_commit_id_accuracy"] = round(github_commit_id_correct / total_gt, 4) if total_gt else 0.0

    hard_checks = [
        "output_exists",
        "tsv_header_valid",
        "rows_parseable",
    ]
    hard_pass = all(scores[k] == 1.0 for k in hard_checks)
    scores["hard_constraint_pass"] = 1.0 if hard_pass else 0.0

    if not hard_pass:
        scores["overall_score"] = 0.0
        return scores

    base_score = round(
        0.05 * scores["paper_f1"]
        + 0.05 * scores["row_sorting_correct"]
        + 0.05 * scores["conference_accuracy"]
        + 0.05 * scores["authors_accuracy"]
        + 0.10 * scores["abstract_accuracy"]
        + 0.15 * scores["author_links_accuracy"]
        + 0.25 * scores["github_commit_id_accuracy"]
        + 0.10 * scores["tex_files_created"]
        + 0.20 * scores["tex_exact_match_ratio"],
        4,
    )
    scores["overall_score"] = round(base_score * scores["output_dir_clean"], 4)
    return scores
```

## Workspace Path

```
workspace/01_Productivity_Flow/task_4_2022_conference_papers
```

## Skills

```
agent-browser
```

## Env

```
```

## Warmup

```
npm install -g agent-browser
```
