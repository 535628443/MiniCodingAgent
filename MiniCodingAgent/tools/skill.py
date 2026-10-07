"""
Skill 技能管理与加载机制：
Layer 1 (启动时目录扫描与注册表构建) & Layer 2 (运行时按需完整注入)
"""
import yaml
from ..config import SKILLS_DIR
from ..state import state


def scan_skills():
    """
    扫描 skills/ 目录，将技能名称、描述以及完整正文存入 state.skill_registry 缓存。
    """
    if not SKILLS_DIR.exists():
        return

    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue

        manifest = d / "SKILL.md"
        if manifest.exists():
            raw = manifest.read_text()
            meta, _ = _parse_frontmatter(raw)

            # 优先使用 frontmatter 中的 name/description，若无则使用目录名及首行文本兜底
            name = meta.get("name", d.name)
            desc = meta.get("description", raw.split("\n")[0].lstrip("#").strip())

            state.skill_registry[name] = {
                "name": name,
                "description": desc,
                "content": raw,
            }


def list_skills() -> str:
    """以 Markdown 列表格式列出所有已注册的技能及其简短说明。"""
    if not state.skill_registry:
        return "(no skills found)"
    return "\n".join(f"- **{s['name']}**: {s['description']}" for s in state.skill_registry.values())


def load_skill(name: str) -> str:
    """
    Layer 2: 按需加载指定技能的完整正文内容。
    直接从内存注册表 state.skill_registry 查询，避免运行时磁盘读取和路径遍历漏洞。
    """
    skill = state.skill_registry.get(name)
    if not skill:
        return f"Skill not found: {name}"
    return skill["content"]


# ====================== Helper Methods ============================

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    解析 SKILL.md 顶部的 YAML Frontmatter 元数据块。
    返回元数据字典和正文内容二元组: (meta, body)。
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}

    return meta, parts[2].strip()