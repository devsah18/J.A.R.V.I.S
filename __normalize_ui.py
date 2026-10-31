import io

path = "voice/ui.py"
with open(path, encoding="utf-8") as f:
    data = f.read()

replacements = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2011": "-",
    "\u2026": "...",
    "\u00a0": " ",
}
for k, v in replacements.items():
    data = data.replace(k, v)

with open(path, "w", encoding="utf-8") as f:
    f.write(data)

non_ascii = sum(1 for c in data if ord(c) > 127)
print("remaining non-ASCII chars:", non_ascii)