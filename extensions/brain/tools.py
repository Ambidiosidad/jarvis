"""
J.A.R.V.I.S. tools catalog used in prompts.
"""

TOOLS = {
    "move": {
        "desc": "Move the robot",
        "params": "direction: forward|backward|left|right|stop, duration: float, speed: 0-1",
    },
    "remember": {
        "desc": "Store a permanent user fact",
        "params": "fact: text",
    },
    "learn_pattern": {
        "desc": "Store a learned user pattern",
        "params": "type: preference|habit|interest|communication_style, description: str",
    },
    "observe_scene": {
        "desc": "Trigger a visual scan using camera",
        "params": "save_frame: bool (optional)",
    },
    "search_knowledge": {
        "desc": "Search uploaded documents (RAG)",
        "params": "query: text",
    },
}


def tools_prompt() -> str:
    lines = [
        "## Available tools",
        'Use JSON to invoke: {"tool":"name","params":{...}}',
    ]
    for name, tool in TOOLS.items():
        lines.append(f"- {name}: {tool['desc']} -> {{{tool['params']}}}")
    return "\n".join(lines)
