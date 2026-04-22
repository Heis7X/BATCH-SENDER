with open("data.json", "rb") as f:
    raw = f.read()

# Decode from UTF-16 (what Windows likely used)
try:
    text = raw.decode("utf-16")
except:
    text = raw.decode("utf-8", errors="ignore")

# Re-save clean UTF-8
with open("clean_data.json", "w", encoding="utf-8") as f:
    f.write(text)

print("Clean file created: clean_data.json")