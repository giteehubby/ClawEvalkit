---
id: 01_Productivity_Flow_task_10_pdf_digest
name: PDF Paper Digest - Rename, Classify, and Extract
category: 01_Productivity_Flow
timeout_seconds: 900
---

## Prompt

请处理位于 `/tmp_workspace/papers.tar` 的压缩包。这个压缩包中共有 65 篇论文 PDF。

请完成以下任务，并将所有结果都保存到 `/tmp_workspace/results/paper_digest.md`：

1. 根据论文标题重命名文件

请读取每篇 PDF 标题，然后将文件重命名为标题格式，其中空格替换为下划线 `_`，斜杠 `/` 也替换为 `_`，保留 `.pdf` 后缀。将重命名后的文件放入 `/tmp_workspace/results/papers/` 目录下（保持扁平结构，不要子目录）。

在 `/tmp_workspace/results/paper_digest.md` 中，输出完整的重命名映射表，格式如下：

```markdown
### Rename Mapping
| Original Filename | New Filename |
|---|---|
| abc123.pdf | Paper_Title_Here.pdf |
| ... | ... |
```

2. 论文分类

对所有 65 篇论文进行分类，归入以下 6 个类别之一（不属于前 5 类的必须放入 Others）。在 Classification 部分只需列出论文标题即可，无需解释。

- Multimodal / Vision-Language Models
- Medical Image Analysis
- Image / Video Generation & Editing
- Autonomous Driving / Robotics / Embodied AI
- 3D Vision / Reconstruction / Gaussian Splatting
- Others

在 `/tmp_workspace/results/paper_digest.md` 中，输出分类结果：

```markdown
### Classification
#### Multimodal / Vision-Language Models
- Paper Title 1
- Paper Title 2

#### Medical Image Analysis
- ...

#### Image / Video Generation & Editing
- ...

#### Autonomous Driving / Robotics / Embodied AI
- ...

#### 3D Vision / Reconstruction / Gaussian Splatting
- ...

#### Others
- ...
```

3. Caption 相关论文与表格提取

我对 image captioning 方向很感兴趣。请从这 65 篇论文中找出与 **image caption** 相关的论文。

对于找到的每篇 caption 相关论文，请提取其 **第二个表格**，并以 markdown 表格格式输出。

在 `/tmp_workspace/results/paper_digest.md` 中，输出如下：

```markdown
### Caption-Related Papers

#### Paper Title

**Table 2: 表格标题描述...**

| Column1 | Column2 | ... |
|---|---|---|
| ... | ... | ... |
```

## Expected Behavior

The agent should:

1. Extract the tar archive, read each PDF to determine its title by parsing the first-page text content — **not** by reading PDF metadata fields (e.g. `/Title`, `/Author`, `/DOI`). The metadata in these files is intentionally unreliable and should be ignored entirely.
2. Rename all 65 files using title-based naming (spaces → underscores), place them in `/tmp_workspace/results/papers/`
3. Classify all 65 papers into exactly 6 categories based on titles and abstracts
4. Identify papers related to image captioning
5. For each caption-related paper, extract the second table (Table 2) and render it as markdown
6. Save everything to `/tmp_workspace/results/paper_digest.md`

## Grading Criteria

- [ ] `/tmp_workspace/results/papers/` exists with renamed files
- [ ] Rename accuracy: sampled files match expected title-based names
- [ ] Classification sections exist with correct headings
- [ ] Classification accuracy: sampled papers in correct categories
- [ ] All caption-related papers identified (CapRL, Asymmetric Idiosyncrasies)
- [ ] Table 2 caption text includes correct keywords for each paper
- [ ] Table 2 contains required column names
- [ ] Table 2 data row count matches expected count (±2 tolerance)
- [ ] Table 2 key cell values are correct

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the PDF paper digest task.

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    import json
    import re
    from pathlib import Path

    ALL_CRITERIA = [
        "papers_dir_exists",
        "rename_accuracy",
        "classification_sections_exist",
        "classification_accuracy",
        "caption_papers_found",
        "table_caption_correct",
        "table_columns_correct",
        "table_rows_correct",
        "table_key_cells_correct",
        "overall_score",
    ]

    scores = {k: 0.0 for k in ALL_CRITERIA}

    gt_file = Path("/tmp_workspace") / "gt" / "ground_truth.json"
    if not gt_file.exists():
        return scores

    gt = json.loads(gt_file.read_text(encoding="utf-8"))
    rename_map = gt["rename_mapping"]
    classification_gt = gt["classification"]
    hash_to_title = gt["hash_to_title"]
    caption_papers = gt["caption_papers"]

    # --- Subtask 1: Rename ---
    papers_dir = Path("/tmp_workspace/results/papers")
    if papers_dir.exists() and papers_dir.is_dir():
        scores["papers_dir_exists"] = 1.0

        existing_files_raw = {f.name for f in papers_dir.iterdir() if f.is_file()}
        existing_lower = {f.lower() for f in existing_files_raw}

        matched = 0
        checked = 0
        for hash_name, expected_name in rename_map.items():
            checked += 1
            if expected_name in existing_files_raw or expected_name.lower() in existing_lower:
                matched += 1

        scores["rename_accuracy"] = round(matched / checked, 4) if checked > 0 else 0.0

    # --- Subtask 2: Classification ---
    digest_path = Path("/tmp_workspace/results/paper_digest.md")
    if not digest_path.exists():
        scores["overall_score"] = round(
            sum(scores[k] for k in ALL_CRITERIA if k != "overall_score") / (len(ALL_CRITERIA) - 1), 4
        )
        return scores

    content = digest_path.read_text(encoding="utf-8")

    def extract_section(md_text, heading_pattern):
        h = re.search(heading_pattern, md_text, re.MULTILINE | re.IGNORECASE)
        if not h:
            return ""
        heading_line = h.group(0)
        level_match = re.match(r"^#{1,6}", heading_line)
        if not level_match:
            return ""
        level = len(level_match.group(0))
        rest = md_text[h.end():]
        next_h = re.search(rf"^#{{1,{level}}}\s+", rest, re.MULTILINE)
        return rest[: next_h.start()] if next_h else rest

    category_headings = [
        "Multimodal / Vision-Language Models",
        "Medical Image Analysis",
        "Image / Video Generation & Editing",
        "Autonomous Driving / Robotics / Embodied AI",
        "3D Vision / Reconstruction / Gaussian Splatting",
        "Others",
    ]

    classification_section = extract_section(content, r"^###\s+Classification\s*$")

    sections_found = 0
    for heading in category_headings:
        pattern = rf"^####\s+{re.escape(heading)}\s*$"
        if re.search(pattern, classification_section, re.MULTILINE):
            sections_found += 1

    scores["classification_sections_exist"] = round(sections_found / len(category_headings), 4)

    title_to_gt_category = {}
    for hname, cat in classification_gt.items():
        title = hash_to_title.get(hname, "")
        if title:
            title_to_gt_category[title] = cat

    checkpoint_papers = {
        "Multimodal / Vision-Language Models": [
            r"CapRL",
            r"HulluEdit",
            r"SUPERGLASSES",
            r"Scale Can.*Overcome Pragmatics",
            r"Asymmetric Idiosyncrasies",
        ],
        "Medical Image Analysis": [
            r"SpectralMamba.UNet",
            r"HARU.Net",
            r"IRSDE.Despeckle",
            r"GazeXPErT",
        ],
        "Image / Video Generation & Editing": [
            r"Face Time Traveller",
            r"DyaDiT",
            r"SPATIALALIGN",
            r"DPCache",
            r"PhotoAgent",
        ],
        "Autonomous Driving / Robotics / Embodied AI": [
            r"DrivePTS",
        ],
        "3D Vision / Reconstruction / Gaussian Splatting": [
            r"BetterScene",
            r"QuadSync",
            r"SceneTransporter",
            r"GSTurb",
            r"SeeThrough3D",
        ],
    }

    correct = 0
    total_checks = 0
    for cat, patterns in checkpoint_papers.items():
        escaped_heading = re.escape(cat)
        cat_section = extract_section(
            classification_section,
            rf"^####\s+{escaped_heading}\s*$"
        )
        for p in patterns:
            total_checks += 1
            if re.search(p, cat_section, re.IGNORECASE):
                correct += 1

    scores["classification_accuracy"] = round(correct / total_checks, 4) if total_checks > 0 else 0.0

    # --- Subtask 3: Caption papers & table extraction ---
    caption_section = extract_section(content, r"^###\s+Caption.Related\s+Papers?\s*$")
    if not caption_section.strip():
        caption_section = extract_section(content, r"^###\s+.*[Cc]aption.*$")

    table2_info = gt.get("caption_table2_info", {})
    expected_papers = list(table2_info.values())

    # 3a: Check all caption papers are found
    found_count = 0
    for paper_info in expected_papers:
        title = paper_info["title"]
        short_name = title.split(":")[0].strip()
        if re.search(re.escape(short_name), caption_section, re.IGNORECASE):
            found_count += 1
    scores["caption_papers_found"] = round(found_count / len(expected_papers), 4) if expected_papers else 0.0

    # 3b: Check table caption keywords
    caption_kw_hits = 0
    caption_kw_total = 0
    for paper_info in expected_papers:
        for kw in paper_info.get("table_caption_keywords", []):
            caption_kw_total += 1
            if re.search(re.escape(kw), caption_section, re.IGNORECASE):
                caption_kw_hits += 1
    scores["table_caption_correct"] = round(caption_kw_hits / caption_kw_total, 4) if caption_kw_total > 0 else 0.0

    # 3c: Check required column names
    col_hits = 0
    col_total = 0
    for paper_info in expected_papers:
        for col in paper_info.get("required_columns", []):
            col_total += 1
            col_pat = re.escape(col).replace(r"\ ", r"[\s_-]*")
            if re.search(col_pat, caption_section, re.IGNORECASE):
                col_hits += 1
    scores["table_columns_correct"] = round(col_hits / col_total, 4) if col_total > 0 else 0.0

    # 3d: Check data row count (±2 tolerance)
    row_score_parts = []
    for paper_info in expected_papers:
        expected_rows = paper_info.get("data_row_count", 0)
        if expected_rows == 0:
            continue
        title = paper_info["title"]
        short_name = title.split(":")[0].strip()
        paper_sub = extract_section(caption_section, rf"^####\s+.*{re.escape(short_name)}.*$")
        if not paper_sub.strip():
            paper_sub = caption_section
        table_lines = re.findall(r"^\|[^|]+\|.+\|$", paper_sub, re.MULTILINE)
        data_lines = [l for l in table_lines if not re.match(r"^\|[\s\-:|]+\|$", l) and "Column" not in l]
        header_lines = [l for l in data_lines if any(
            re.search(re.escape(c), l, re.IGNORECASE)
            for c in paper_info.get("required_columns", [])[:2]
        )]
        actual_data = len(data_lines) - len(header_lines)
        diff = abs(actual_data - expected_rows)
        row_score_parts.append(max(0.0, 1.0 - diff / max(expected_rows, 1)) if diff <= expected_rows else 0.0)
    scores["table_rows_correct"] = round(sum(row_score_parts) / len(row_score_parts), 4) if row_score_parts else 0.0

    # 3e: Check key cell values
    cell_hits = 0
    cell_total = 0
    for paper_info in expected_papers:
        for cell in paper_info.get("key_cells", []):
            cell_total += 1
            row_pat = re.escape(cell["row"]).replace(r"\ ", r"[\s_-]*")
            val_pat = re.escape(cell["value"])
            if re.search(
                rf"^\|[^\n]*{row_pat}[^\n]*{val_pat}[^\n]*\|",
                caption_section,
                re.IGNORECASE | re.MULTILINE,
            ):
                cell_hits += 1
    scores["table_key_cells_correct"] = round(cell_hits / cell_total, 4) if cell_total > 0 else 0.0

    if scores["papers_dir_exists"] < 1.0:
        scores["overall_score"] = 0.0
        return scores

    scores["overall_score"] = round(
        0.25 * scores["rename_accuracy"]
        + 0.05 * scores["classification_sections_exist"]
        + 0.20 * scores["classification_accuracy"]
        + 0.10 * scores["caption_papers_found"]
        + 0.05 * scores["table_caption_correct"]
        + 0.05 * scores["table_columns_correct"]
        + 0.05 * scores["table_rows_correct"]
        + 0.25 * scores["table_key_cells_correct"],
        4,
    )

    return scores
```

## Workspace Path

```
workspace/01_Productivity_Flow/task_10_pdf_digest
```

## Skills

```
```

## Env

```
```

## Warmup

```
```
