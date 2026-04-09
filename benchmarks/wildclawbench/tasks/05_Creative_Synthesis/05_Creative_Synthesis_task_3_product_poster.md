---
id: 05_Creative_Synthesis_task_3_product_poster
name: Design a Product Poster for a Leather Briefcase
category: 05_Creative_Synthesis
timeout_seconds: 900
---

## Prompt

I have a product photo of a briefcase at `/tmp_workspace/briefcase.png`.

Please design an **informational product display image** (1080×1440 px PNG) for this item. The image should clearly present the product's key features and characteristics in a clean, professional layout.

Basic info:

- **Brand**: Thornfield & Co.
- **Product Name**: The Meridian Briefcase
- **Tagline**: "Carry Your Story"
- **Price**: $279.00 (reference price $379.00)

Look at the product photo carefully, identify its standout features (material, craftsmanship, functionality, etc.), and prominently showcase them in the design. Include a note inviting viewers to learn more.

Save the final image to `/tmp_workspace/results/poster.png`.

If you need image understanding or multimodal generation capabilities, you can call the OpenRouter API (base_url available via the `OPENROUTER_BASE_URL` environment variable, API key available via the `OPENROUTER_API_KEY` environment variable).

## Expected Behavior

The agent should:

1. Examine the product photo to understand the product's visual style and characteristics
2. Identify key selling points from the photo (material, craftsmanship, details, etc.)
3. Design a poster that prominently highlights these features
4. Include basic info (brand, name, tagline, price) and a CTA
5. Save the final PNG image to the specified path

## Grading Criteria

### File & Dimensions

- [ ] `poster.png` file exists and has correct dimensions (1080×1440) — wrong dimensions penalize overall score ×0.5

### LLM-as-Judge (3 dimensions, each 0.0–1.0)

- [ ] **Content Completeness**: Basic info present (brand, name, tagline, price, CTA) and product features identified and displayed
- [ ] **Feature Highlighting**: How well the poster identifies and showcases the product's standout features — does it go beyond the given info and extract real details from the photo?
- [ ] **Design & Impact**: Layout composition, visual hierarchy, premium feel, overall polish and persuasive power

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the product poster task on 3 dimensions:
    content completeness, aesthetic quality, design & impact.
    """
    import os
    import json
    import base64
    from pathlib import Path

    grading_model = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")
    workspace = Path("/tmp_workspace/results")
    scores = {}

    poster_path = workspace / "poster.png"

    scores["poster_exists"] = 1.0 if poster_path.exists() and poster_path.stat().st_size > 0 else 0.0

    zero_scores = {
        "dimensions_correct": 0.0,
        "content_completeness": 0.0,
        "feature_highlighting": 0.0,
        "design_impact": 0.0,
        "overall_score": 0.0,
    }

    if scores["poster_exists"] == 0.0:
        scores.update(zero_scores)
        return scores

    try:
        from PIL import Image
        img = Image.open(poster_path)
        w, h = img.size
        scores["dimensions_correct"] = 1.0 if (w == 1080 and h == 1440) else 0.0
    except Exception:
        scores["dimensions_correct"] = 0.0

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ["OPENROUTER_BASE_URL"])

        with open(poster_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        grading_prompt = (
            "You are a senior art director at a top design agency reviewing a product display image "
            "for a leather briefcase. Be EXTREMELY critical — your standards are high.\n\n"
            "The agent was given a product photo and asked to identify the product's standout features "
            "and present them in a polished, professional poster (1080×1440). Only basic info was provided "
            "(brand, name, tagline, price). The agent had to observe the photo and extract real product "
            "details on its own.\n\n"
            "Score the image on exactly 3 dimensions (each 0.0 to 1.0). BE HARSH — most outputs "
            "should score 0.1-0.4 unless they are genuinely impressive.\n\n"
            "1. **content_completeness**: Are the basic elements present and legible?\n"
            "   Required: brand 'Thornfield & Co.', product name 'The Meridian Briefcase', "
            "tagline 'Carry Your Story', price $279, reference price $379, "
            "and an invitation to learn more.\n"
            "   Also check: does the image display product features and characteristics?\n"
            "   Score = fraction of required elements present + bonus for feature richness.\n"
            "   Deduct if any text overlaps, is cut off, or is hard to read.\n\n"
            "2. **feature_highlighting**: How well does the image identify and showcase "
            "the product's standout features?\n"
            "   Consider: Did it go beyond the basic given info and extract real, specific details "
            "from the product photo (e.g. leather grain texture, stitching pattern, buckle style, "
            "hardware finish, compartment layout, strap attachment mechanism)?\n"
            "   Are the features presented with visual creativity (e.g. callout lines pointing to "
            "the product, close-up crops, icons) — NOT just plain text boxes?\n"
            "   - Generic labels like 'Premium Leather' or 'Brass Hardware' without specificity = 0.0-0.2.\n"
            "   - Simple bordered text boxes listing features = 0.1-0.3 max.\n"
            "   - Specific, photo-informed features with strong visual integration = 0.7+.\n\n"
            "3. **design_impact**: Layout, hierarchy, originality, and visual quality.\n"
            "   This is a POSTER, not a web page. Judge it as a graphic design deliverable.\n"
            "   Red flags that indicate LOW scores (0.0-0.2):\n"
            "   - Looks like basic HTML/CSS rendering rather than graphic design\n"
            "   - Elements simply stacked vertically with no creative composition\n"
            "   - Large areas of dead/empty space with no purpose\n"
            "   - Plain rectangular boxes with thin borders for feature callouts\n"
            "   - No typographic sophistication (basic fonts, no weight/size contrast)\n"
            "   - Text overlapping or poorly aligned (e.g. prices crammed together)\n"
            "   - Product photo just dropped in without creative integration\n"
            "   - No color harmony, gradients, textures, or design elements\n"
            "   - Overall looks like a wireframe or first draft, not a finished design\n"
            "   Good scores (0.6+) require:\n"
            "   - Thoughtful composition with intentional whitespace\n"
            "   - Strong typographic hierarchy with varied weights and sizes\n"
            "   - Product photo creatively integrated into the layout\n"
            "   - Polished, premium visual feel suitable for a luxury brand\n"
            "   - Design elements (shapes, lines, color blocks) used purposefully\n\n"
            "Remember: most code-generated posters look like basic HTML templates. "
            "Do NOT give generous scores to template-quality work. A typical code-rendered "
            "poster with stacked elements and bordered boxes should score 0.1-0.2 on design_impact.\n\n"
            "Respond strictly in JSON:\n"
            '{"content_completeness": 0.0, "feature_highlighting": 0.0, "design_impact": 0.0}'
        )

        resp = client.chat.completions.create(
            model=grading_model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": grading_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]}],
            temperature=0,
        )

        raw = resp.choices[0].message.content.strip()
        raw = raw.strip("`").removeprefix("json").strip()
        llm_scores = json.loads(raw)

        for key in ["content_completeness", "feature_highlighting", "design_impact"]:
            scores[key] = round(min(max(float(llm_scores.get(key, 0.0)), 0.0), 1.0), 4)

    except Exception as e:
        scores.update(zero_scores)
        scores["llm_error"] = str(e)
        return scores

    raw_score = (
        0.20 * scores["content_completeness"]
        + 0.40 * scores["feature_highlighting"]
        + 0.40 * scores["design_impact"]
    )

    dim_penalty = 1.0 if scores.get("dimensions_correct", 0) == 1.0 else 0.5
    scores["overall_score"] = round(raw_score * dim_penalty, 4)

    return scores
```
## Workspace Path

```
workspace/05_Creative_Synthesis/task_3_product_poster
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
```bash
pip install openai
```
