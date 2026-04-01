---
id: 02_Code_Intelligence_task_10_acad_homepage_zh
name: Academic Homepage Style Transfer
category: 02_Code_Intelligence
timeout_seconds: 1200
---

## Prompt

任务：参考附图 `/tmp_workspace/ref_template_screenshot.png` 中的主页模板风格，为作者 Shuangrui Ding（丁双睿）制作一个新的学术个人主页。（注意：时间有限，尽量15分钟内完成，请注意高效）

【具体要求】
1. 不需要部署到 GitHub，只需在本地生成可用的静态网页
2. 论文展示部分只放他以共一或者一作身份中稿2025年的ICCV或者CVPR的文章，不用展示其他会议的论文
3. News 部分只要展示 25 年 10 月份之前的部分即可，之后的不用展示
4. 个人信息可参考作者现有主页截图 `/tmp_workspace/ref_author_homepage_screenshot.png` 上的介绍
5. 所有代码和资源文件放在 `/tmp_workspace/results` 目录下
6. 使用 Playwright + Headless Chromium 将最终网页首页完整截图，保存为 `/tmp_workspace/results/screenshot.png`

【提示和注意事项】
1. 模板参考：`/tmp_workspace/ref_template_screenshot.png` 展示了 AcadHomepage 风格的学术主页，可以直接基于 AcadHomepage 仓库修改，也可以自行搭建同风格页面
2. https://rayeren.github.io/和https://mark12ding.github.io/是这两个截图的原链接，但是不保证内容与这两张截图一致（可能网页有更新等），你需要以两个截图的内容为准，如果原链接有你可以用的东西，你可以考虑使用，仅供参考
3. 当前 Python 环境已预装 playwright 和 chromium，可直接使用
4. 截图需包含完整首页内容

【输出要求】
- `/tmp_workspace/results/` 目录下包含完整的静态网页源码
- `/tmp_workspace/results/screenshot.png` 为最终主页首页的完整截图

如果需要图像理解或多模态生成能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API Key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

评测方预期智能体会：

1. 参考 AcadHomepage 模板仓库搭建页面
2. 根据提供的作者主页截图中的个人信息修改模板内容
3. 根据截图中的信息，筛选出 Shuangrui Ding 以一作或共一身份中稿 2025 年 ICCV 或 CVPR 的论文
4. 筛选 News 动态，仅保留 2025 年 10 月之前的条目
5. 生成完整的本地静态网页
6. 使用 Playwright 对网页进行完整截图并保存

## Grading Criteria

评估方式：将新生成主页的截图交给 VLM，逐条对照 rubric 打分（1=满足 / 0=不满足）。overall_score = 通过条数 / 总条数（共 35 条）。

一、网页风格与 AcadHomepage 模板一致性（14 条）
- [ ] 1. 页面采用左侧边栏 + 右侧主内容区的双栏布局
- [ ] 2. 左侧栏包含圆形的个人头像/照片（非方形、非圆角矩形），且不能是灰色默认剪影占位符
- [ ] 3. 左侧栏显示姓名，并紧跟一行简短的研究方向/身份标语
- [ ] 4. 左侧栏的社交链接采用竖向排列，每行一个链接由图标+文字标签组成（如 Email、GitHub、Google Scholar 各占一行，而非仅小图标横向排列）
- [ ] 5. 各板块标题使用与模板一致的 emoji（🔥 News、📝 Publications、🎖 Honors and Awards、📖 Educations、💬 Invited Talks、💻 Internships），不应使用替代 emoji（如 📄、🏆、🎓、🎤、💼 等）
- [ ] 6. 重点论文采用卡片式展示（左侧缩略图/论文配图 + 右侧标题、作者、会议标签、链接按钮），缩略图不能是灰色占位符或 broken image
- [ ] 7. 作者本人姓名在论文作者列表中加粗显示
- [ ] 8. News 部分的日期使用 YYYY.MM 格式（如 2024.03），使用斜体样式，不使用方括号包裹的月份缩写格式（如 [Jan. 2026]）
- [ ] 9. 整体为简洁学术风格，配色协调
- [ ] 10. 板块结构和顺序与模板一致（About → News → Publications → Awards → ...）
- [ ] 11. 主内容区顶部的个人简介直接展示文字，没有独立的板块标题（不应出现 "About Me" 等标题头）
- [ ] 12. 左侧栏不包含模板中不存在的多余独立元素（如不应有单独的 CV 文字链接按钮或下载链接）
- [ ] 13. Educations 部分的时间使用纯文字格式（如 2019.06 - 2022.04, Master），不使用彩色标签或徽章样式显示年份
- [ ] 14. 论文的会议标签使用素雅文字样式（如直接文字 NeurIPS 2019），不使用彩色胶囊或亮色徽章样式

二、Prompt 要求满足度（5 条）
- [ ] 15. Publications 部分恰好展示两篇论文（不多不少）
- [ ] 16. 两篇论文中 Shuangrui Ding 均为一作或共一（共同一作 * 标记也算满足）
- [ ] 17. 包含论文 "SAM2Long: Enhancing SAM 2 for Long Video Segmentation with a Training-Free Memory Tree"（ICCV 2025）
- [ ] 18. 包含论文 "Dispider: Enabling Video LLMs with Active Real-Time Interaction via Disentangled Perception, Decision, and Reaction"（CVPR 2025）
- [ ] 19. News 部分仅展示 2025 年 10 月之前的动态（不包含 2025 年 10 月及之后的条目）

三、文字内容与原主页一致性（13 条）
- [ ] 20. 姓名正确显示（Shuangrui Ding / 丁双睿）
- [ ] 21. 身份正确（CUHK MMLab 博士生）
- [ ] 22. 导师信息正确（Prof. Dahua Lin）
- [ ] 23. 研究方向描述与原主页一致（vision-language model、object-centric video understanding）
- [ ] 24. 教育经历完整（硕士 SJTU 2023 + 本科 UMich/SJTU 双学位 2021）
- [ ] 25. 实习经历提及（Meta Superintelligence Labs, Segment Anything Team）
- [ ] 26. 页面包含联系方式和社交链接区域（邮箱、Scholar、GitHub、LinkedIn 等入口均有展示）
- [ ] 27. 每篇论文的标题、作者列表、会议/年份信息完整展示
- [ ] 28. 每篇论文包含链接入口文字或按钮（如 arXiv / code / project 等）
- [ ] 29. 每篇论文包含一句话描述/简介
- [ ] 30. 获奖信息完整展示（至少包含以下 5 项中的 4 项：CUHK 校长奖学金、研究生国奖、上海市优秀毕业生、MCM Finalist、本科国奖）
- [ ] 31. 包含 Professional Services / Reviewer 信息
- [ ] 32. 包含 Invited Talks 信息

四、视觉资源加载与完整性（3 条）
- [ ] 33. 左侧栏的头像显示了真实的人物照片（非灰色默认头像剪影、非 broken image 图标、非空白占位符）
- [ ] 34. 两篇论文卡片的左侧缩略图均实际显示了与论文内容相关的图片（如论文 figure、方法示意图），非灰色占位符、非写有 placeholder 文字的色块、非 broken image
- [ ] 35. 左侧栏的社交链接图标均正常加载并显示为可辨识的品牌或功能图形（如邮件信封、GitHub logo 等），非缺失图标、非 broken image 方框、非空白

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Academic homepage style transfer grading.
    Send generated homepage screenshot to VLM for rubric-based evaluation.

    Returns:
        dict of per-dimension scores (0.0-1.0)
    """
    import os
    import json
    import time
    import base64
    import logging
    from pathlib import Path

    log = logging.getLogger("grade_acad_homepage")
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    base = Path("/tmp_workspace")
    homepage_dir = base / "results"
    screenshot_path = homepage_dir / "screenshot.png"

    scores = {}

    # ========== Programmatic pre-checks ==========

    if not homepage_dir.exists():
        log.warning("results directory not found: %s", homepage_dir)
        return {"overall_score": 0.0, "error": "results directory not found"}

    html_files = list(set(homepage_dir.rglob("*.html")))
    scores["has_html"] = 1.0 if html_files else 0.0
    if not html_files:
        log.warning("No HTML files found in results directory")

    if not screenshot_path.exists():
        log.warning("screenshot.png not found: %s", screenshot_path)
        return {"overall_score": 0.0, "error": "screenshot.png not found"}

    screenshot_size = screenshot_path.stat().st_size
    if screenshot_size < 1024:
        log.warning("screenshot.png too small (%d bytes), may be invalid", screenshot_size)
        return {"overall_score": 0.0, "error": "screenshot.png too small, likely invalid"}

    scores["screenshot_exists"] = 1.0
    log.info("screenshot.png exists, size: %d bytes", screenshot_size)

    # ========== Read screenshot ==========

    img_b64 = base64.b64encode(screenshot_path.read_bytes()).decode("utf-8")

    # ========== Define VLM evaluation rubric ==========

    rubrics = {
        # ===== Style consistency =====
        "style_1_dual_column": "页面采用左侧边栏 + 右侧主内容区的双栏布局",
        "style_2_photo_round": "左侧栏包含圆形的个人头像或照片（非方形、非圆角矩形），且不能是灰色默认剪影占位符",
        "style_3_name_tagline": "左侧栏显示姓名，并紧跟一行简短的研究方向或身份标语",
        "style_4_social_vertical": "左侧栏的社交链接采用竖向排列，每行一个链接由图标加文字标签组成（如 Email、GitHub、Google Scholar 各占一行），而非仅小图标横向排列",
        "style_5_emoji_match": "各板块标题使用与 AcadHomepage 模板一致的 emoji：🔥 News、📝 Publications、🎖 Honors and Awards、📖 Educations、💬 Invited Talks、💻 Internships，不应使用其他替代 emoji（如 📄、🏆、🎓、🎤、💼 等均为不一致）",
        "style_6_paper_cards": "重点论文采用卡片式展示，左侧有缩略图或论文配图（非灰色占位符或 broken image），右侧有标题、作者、会议标签和链接按钮",
        "style_7_bold_author": "作者本人姓名 Shuangrui Ding 在论文作者列表中加粗显示",
        "style_8_news_date_format": "News 部分的日期使用 YYYY.MM 格式（如 2024.03），使用斜体样式，不使用方括号包裹的月份缩写格式（如 [Jan. 2026]）",
        "style_9_academic_style": "整体为简洁学术风格，配色协调，无花哨装饰",
        "style_10_section_order": "板块结构与学术主页模板一致，大致遵循 About、News、Publications、Awards 等顺序",
        "style_11_no_about_header": "主内容区顶部的个人简介直接展示文字，没有独立的板块标题（不应出现 About Me 等标题头）",
        "style_12_no_extra_sidebar": "左侧栏不包含模板中不存在的多余独立元素（如不应有单独的 CV 文字链接按钮或下载链接）",
        "style_13_edu_date_format": "Educations 部分的时间使用纯文字格式（如 2019.06 - 2022.04, Master），不使用彩色标签或徽章样式显示年份",
        "style_14_venue_tag_style": "论文的会议标签使用素雅文字样式（如直接文字 NeurIPS 2019），不使用彩色胶囊或亮色徽章样式",
        # ===== Prompt requirements =====
        "prompt_15_two_papers": "Publications 部分恰好展示两篇论文，不多不少",
        "prompt_16_first_or_cofirst": "展示的两篇论文中 Shuangrui Ding 均为一作或共一（共同一作 * 标记也算满足）",
        "prompt_17_sam2long": "包含论文 SAM2Long: Enhancing SAM 2 for Long Video Segmentation with a Training-Free Memory Tree（ICCV 2025）",
        "prompt_18_dispider": "包含论文 Dispider: Enabling Video LLMs with Active Real-Time Interaction via Disentangled Perception, Decision, and Reaction（CVPR 2025）",
        "prompt_19_news_filter": "News 部分仅展示 2025 年 10 月之前的动态，不包含 2025 年 10 月及之后的条目",
        # ===== Content consistency =====
        "content_20_name": "姓名正确显示为 Shuangrui Ding 或丁双睿",
        "content_21_affiliation": "身份显示为香港中文大学 CUHK MMLab 博士生",
        "content_22_advisor": "导师信息提及 Prof. Dahua Lin",
        "content_23_research": "研究方向描述包含 vision-language model 或 object-centric video understanding 相关表述",
        "content_24_education": "教育经历包含硕士上海交通大学和本科密歇根大学或上海交通大学双学位信息",
        "content_25_internship": "页面提及 Meta 实习经历（Meta Superintelligence Labs 或 Segment Anything Team）",
        "content_26_contact": "页面包含联系方式区域，展示了邮箱、Google Scholar、GitHub、LinkedIn 等入口",
        "content_27_paper_info": "每篇论文的标题、作者列表、会议名称和年份信息均完整展示",
        "content_28_paper_links": "每篇论文旁边有链接入口文字或按钮（如 arXiv、code、project page 等）",
        "content_29_paper_desc": "每篇论文附有一句话描述或简介",
        "content_30_awards": "获奖信息展示了至少 4 项奖项（CUHK 校长奖学金、研究生国奖、上海市优秀毕业生、MCM Finalist、本科国奖）",
        "content_31_services": "页面包含 Professional Services 或 Reviewer 相关信息",
        "content_32_talks": "页面包含 Invited Talks 相关信息",
        # ===== Visual resource loading =====
        "visual_33_real_photo": "左侧栏的头像显示了真实的人物照片，非灰色默认头像剪影、非 broken image 图标、非空白占位符",
        "visual_34_paper_thumbs": "两篇论文卡片的左侧缩略图均实际显示了与论文内容相关的图片（如论文 figure、方法示意图），非灰色占位符、非写有 placeholder 文字的色块、非 broken image",
        "visual_35_social_icons": "左侧栏的社交链接图标均正常加载并显示为可辨识的品牌或功能图形（如邮件信封、GitHub logo 等），非缺失图标、非 broken image 方框、非空白",
    }

    rubric_list = "\n".join(
        f"  - {rid}: {desc}" for rid, desc in rubrics.items()
    )

    # ========== VLM as Judge ==========

    vlm_succeeded = False
    last_error = None

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.environ["OPENROUTER_BASE_URL"],
        )

        judge_prompt = (
            "你是一位网页评估专家。下面是一张学术个人主页的完整截图。\n"
            "请根据截图内容，逐条评估以下 rubric，判断该网页是否满足每条要求。\n\n"
            "评估规则：\n"
            "- 对每条 rubric 给出 1（满足）或 0（不满足）\n"
            "- 仔细观察截图中的文字、布局、板块结构等细节\n"
            "- 如有不确定，偏向给 0\n\n"
            f"Rubric 列表：\n{rubric_list}\n\n"
            "请严格按以下 JSON 格式返回（不要包含任何其他文字）：\n"
            "{\n"
            '    "rubric_id": 0 或 1,\n'
            "    ...\n"
            "}\n"
            "确保返回的 JSON 包含上述所有 rubric_id 作为键。"
        )

        max_retries = 3
        for attempt in range(max_retries):
            log.info("VLM Judge request %d/%d...", attempt + 1, max_retries)
            try:
                resp = client.chat.completions.create(
                    model=os.environ.get("JUDGE_MODEL", "openai/gpt-5.4"),
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_b64}",
                                },
                            },
                            {"type": "text", "text": judge_prompt},
                        ],
                    }],
                    temperature=0.0,
                    max_tokens=2048,
                )

                raw = resp.choices[0].message.content.strip()
                log.info("VLM raw response: %s", raw[:600])

                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                result = json.loads(raw)

                for rid in rubrics:
                    scores[rid] = float(max(0, min(1, int(result.get(rid, 0)))))

                scores["judge_method"] = "vlm"
                scores["vlm_attempts"] = attempt + 1
                vlm_succeeded = True
                log.info("VLM Judge succeeded")
                break

            except Exception as e:
                last_error = e
                log.warning("VLM Judge attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

    except Exception as e:
        last_error = e
        log.error("OpenAI client initialization failed: %s", e)

    if not vlm_succeeded:
        log.warning("VLM Judge all attempts failed, all rubrics scored 0")
        if last_error:
            scores["judge_error"] = str(last_error)
        for rid in rubrics:
            scores[rid] = 0.0
        scores["judge_method"] = "failed"

    # ========== Aggregate scores ==========

    all_rubric_keys = list(rubrics.keys())
    style_keys = [k for k in all_rubric_keys if k.startswith("style_")]
    prompt_keys = [k for k in all_rubric_keys if k.startswith("prompt_")]
    content_keys = [k for k in all_rubric_keys if k.startswith("content_")]
    visual_keys = [k for k in all_rubric_keys if k.startswith("visual_")]

    style_avg = (
        sum(scores.get(k, 0.0) for k in style_keys) / len(style_keys)
        if style_keys else 0.0
    )
    prompt_avg = (
        sum(scores.get(k, 0.0) for k in prompt_keys) / len(prompt_keys)
        if prompt_keys else 0.0
    )
    content_avg = (
        sum(scores.get(k, 0.0) for k in content_keys) / len(content_keys)
        if content_keys else 0.0
    )
    visual_avg = (
        sum(scores.get(k, 0.0) for k in visual_keys) / len(visual_keys)
        if visual_keys else 0.0
    )

    scores["style_score"] = round(style_avg, 4)
    scores["prompt_score"] = round(prompt_avg, 4)
    scores["content_score"] = round(content_avg, 4)
    scores["visual_score"] = round(visual_avg, 4)

    total_pass = sum(scores.get(k, 0.0) for k in all_rubric_keys)
    total_count = len(all_rubric_keys)
    scores["overall_score"] = round(total_pass / total_count, 4)

    log.info(
        "Final scores: style=%.4f, prompt=%.4f, content=%.4f, visual=%.4f, overall=%.4f (%d/%d)",
        scores["style_score"], scores["prompt_score"],
        scores["content_score"], scores["visual_score"],
        scores["overall_score"],
        int(total_pass), total_count,
    )

    return scores
```

## Workspace Path

```
workspace/02_Code_Intelligence/task_10_acad_homepage_zh
```

## Skills

```
```

## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```

## Warmup

```
pip install openai playwright
python3 -m playwright install chromium
```
