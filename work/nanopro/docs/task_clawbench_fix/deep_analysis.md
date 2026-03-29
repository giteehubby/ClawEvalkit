# clawbench-official 深度分析报告

## 执行摘要

本报告对 clawbench-official 的回答轨迹进行深入分析，识别出以下关键问题：

### 关键发现

| 问题类型 | 数量 | 说明 |
|---------|------|------|
| 评分代码bug | 2个 | python→python3, 权重计算错误 |
| Fallback评分漏洞 | 1个 | 奖励幻觉输出 |
| Benchmark数据缺失 | 192个 | setup.sh中文件路径不存在 |
| 模型能力问题 | ~44个 | 真正任务失败 |

---

## 一、评分系统Bug分析

### Bug 1: Python命令错误 (已修复)
**位置**: `clawbench_official.py` line 263
**问题**: 使用 `"python"` 而非 `"python3"`
**影响**: pytest命令永远失败，所有评分回退到`_grade_by_outputs`

```python
# 修复前
"python", "-m", "pytest"

# 修复后
"python3", "-m", "pytest"
```

### Bug 2: 权重计算错误 (已修复)
**位置**: lines 296-307
**问题**:
1. `re.search()`只找到最后一个权重，而非每个测试的权重
2. 即使计算了total_weight，也没用在分数公式中

```python
# 修复前 - 错误的权重累加
for line in output.split("\n"):
    ...
    weight_match = re.search(r'@pytest\.mark\.weight\((\d+)\)', output)  # 只找到一个
    if weight_match:
        total_weight += int(weight_match.group(1))

# 修复后 - 正确的每测试权重跟踪
test_results = {}  # test_name -> (passed, weight)
for line in output.split("\n"):
    match = re.match(r'\s*(test_\w+)\s+(PASSED|FAILED)', line)
    if match:
        test_results[test_name] = (passed, 1)  # 默认权重1
```

### Bug 3: Fallback评分奖励幻觉内容 (已修复)
**位置**: `_grade_by_outputs` function
**问题**: 只检查.json/.csv/.md文件，代码任务输出.py文件被忽略

```python
# 修复前
output_files = (
    list(workspace.rglob("*.json")) +
    list(workspace.rglob("*.csv")) +
    list(workspace.rglob("*.md"))
)

# 修复后 - 增加.py和其他常见格式
output_files = (
    list(workspace.rglob("*.json")) +
    list(workspace.rglob("*.csv")) +
    list(workspace.rglob("*.md")) +
    list(workspace.rglob("*.py")) +    # 代码任务
    list(workspace.rglob("*.txt")) +
    list(workspace.rglob("*.html"))
)
```

---

## 二、失败轨迹分类

### 2.1 环境初始化失败 (199个任务)

**setup.sh失败原因分布**:

| 失败类型 | 数量 | 说明 |
|---------|------|------|
| cp: cannot stat | 192 | 数据文件缺失 |
| Python语法错误 | 2 | bio-002, bio-005 setup.sh |
| bash变量错误 | 2 | law-002 unbound variable |
| 其他 | 3 | sqlite3不存在等 |

**示例 - comm-001**:
```
setup.sh failed: cp: cannot stat '.../environment/data/message.json': No such file or directory
```
→ Agent幻觉生成内容 → Fallback评分给了100分

### 2.2 真正失败 (44个任务，无setup.sh问题)

这些是模型能力或agent行为问题：

**路径理解问题**:
- `bio-001`: Agent猜错文件名 `species_sequences.fasta` vs `sequences.fasta`
- `bio-002`: Agent陷入循环，反复调用`list_dir("workspace")`

**Agent放弃过早**:
- `code-002`: Agent正确实现`is_palindrome()`但未运行验证测试
- `acad-001`: Agent尝试安装包失败后直接放弃

**任务理解不足**:
- `cont-002`: 主题建模任务理解偏差

---

## 三、详细案例分析

### 案例1: comm-001 (通过但内容错误)

**问题**: setup.sh失败，但Agent幻觉输出获得高分

```
setup.sh: cp: cannot stat '.../message.json' → 失败
Agent: 创建了假的 "Subject", "Body text goes here."
Fallback评分: 发现workspace/outputs/有文件 → 给予高分
```

**根本原因**: setup.sh数据缺失 + Fallback评分只看文件存在

### 案例2: code-002 (失败但代码正确)

**问题**: Agent正确实现了函数，但评分系统给了低分

1. Agent写入 `workspace/palindrome.py`
2. pytest运行但失败(pytest命令用的是`python`而非`python3`)
3. Fallback评分: 只找.json/.csv/.md，找不到 → 30分

**实际验证**:
```bash
# 手动用python3运行pytest
python3 -m pytest test_output.py --workspace /tmp/workspace → 9/10 passed (90%)
```

### 案例3: bio-001 (Agent文件名猜错)

**问题**: Agent误解指令，猜错输入文件名

- 指令说: `workspace/sequences.fasta`
- Agent找: `workspace/species_sequences.fasta`
- `read_file("workspace/species_sequences.fasta")` → Error (路径问题)
- `exec("cat workspace/species_sequences.fasta")` → 成功!

**发现**: exec工具可以正常工作，但read_file/write_file有路径问题

---

## 四、路径解析问题深入分析

### 问题现象
- `exec("cat workspace/species_sequences.fasta")` → 成功
- `read_file("workspace/species_sequences.fasta")` → Error: File not found

### 原因
exec使用bash直接执行，不经过`_resolve_path`处理
而read_file/write_file等工具经过路径解析

### 验证
查看filesystem.py中的`_resolve_path`函数逻辑：
- `workspace/xxx` 被strip成 `xxx`
- 然后与workspace目录拼接

但问题是Agent传递的路径可能已经被解析过或者有其他问题

---

## 五、Docker使用情况

**结论**: clawbench-official 不使用Docker

- 适配器代码中无docker相关代码
- 任务使用`setup.sh`脚本初始化环境
- 所有文件操作在本地文件系统完成

---

## 六、修复验证

### 已应用的修复

1. ✅ `python` → `python3` (pytest命令)
2. ✅ 权重计算逻辑重写
3. ✅ Fallback评分增加.py文件支持
4. ✅ 添加 `-p no:cacheprovider` 避免.pyc文件干扰

### 需要重新运行验证

当前评分结果可能不准确，因为:
- 之前的运行使用了错误的python命令
- 权重计算从未正确工作
- Fallback评分错误地奖励了幻觉内容

---

## 七、建议行动

### 立即行动
1. 使用修复后的代码重新运行benchmark
2. 对比修复前后的分数变化

### 短期优化
1. 修复setup.sh数据缺失问题(192个任务)
2. 改进Agent对文件名的理解能力

### 长期改进
1. 评分系统增加内容正确性验证
2. Fallback评分应该检查文件内容而非只检查存在性
