"""Add a condition-and-boundary focus only to the first optional solve path."""

BOUNDARY_CHECK_SUFFIX = """

本路求解重点：条件、解集与边界。
独立求解此题，优先从题目要求的结论反向检查约束：所得候选是否满足全部条件，是否遗漏其他解，极值是否能够达到。
对关键变形检查必要性与充分性，尤其注意除零、平方增根、定义域和边界情形；证明题检查关键命题的适用前提。
仅进行与题型相关的检查，不机械穷举；未发现具体矛盾时及时收束。给出完整解答，最后单独写一行“最终答案：...”。
"""


def system_prompt_for_path(base_prompt: str, path: int) -> str:
    """Keep paths one/three byte-identical; path two adds no candidate context."""
    return base_prompt + BOUNDARY_CHECK_SUFFIX if path == 2 else base_prompt
