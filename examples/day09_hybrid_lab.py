from research_agent.retrieval import tokenize

samples = [
    "offset",
    "max_steps add set",
    "MODEL_NAME",
    "model-name",
    "最大步骤数",
    "最大步数是多少？",
]

for text in samples:
    print(text, "->", tokenize(text))