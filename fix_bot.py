with open("backend/bot.py", "r") as f:
    content = f.read()

# Fix the import
if "LLMFullResponseEndFrame" not in content[:1000]:
    content = content.replace(
        "    TextFrame,\n",
        "    TextFrame,\n    LLMFullResponseEndFrame,\n",
        1
    )

# Revert the bad change at 784 if it happened
content = content.replace(
    "isinstance(frame, (LLMMessagesFrame, LLMFullResponseEndFrame, TextFrame)):",
    "isinstance(frame, (LLMTextFrame, TextFrame)):"
)

with open("backend/bot.py", "w") as f:
    f.write(content)
