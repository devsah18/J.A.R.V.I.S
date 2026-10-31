path = "voice/ui.py"
with open(path, encoding="utf-8") as f:
    data = f.read()

emoji_map = {
    "\U0001F5E3": " ",
    "\U0001F3A4": " ",
    "\u2705": "",
    "\u274C": "",
    "\U0001F4DD": "",
    "\U0001F440": "",
}
for k, v in emoji_map.items():
    data = data.replace(k, v)

# Strip any remaining non-ASCII
cleaned = "".join(c if ord(c) < 128 else (" " if ord(c) != 0x2013 else "-") for c in data)

with open(path, "w", encoding="utf-8") as f:
    f.write(cleaned)

non_ascii = sum(1 for c in cleaned if ord(c) > 127)
print("remaining non-ASCII:", non_ascii)